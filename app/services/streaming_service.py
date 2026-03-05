"""
Viewport streaming service.

agent-browser exposes a WebSocket server on AGENT_BROWSER_STREAM_PORT when
that env-var is set. This service:

  1. Connects to agent-browser's WS as a client
  2. Forwards every frame/status message to all subscribed frontend clients
  3. Forwards input events (mouse, keyboard, touch) from frontend clients back
     to agent-browser so humans can interact alongside the AI agent

Architecture:

  frontend WS client(s)
        ↕  (FastAPI WebSocket endpoint)
  ViewportProxy  (this module)
        ↕  (websockets client)
  agent-browser WS server (localhost:AGENT_BROWSER_STREAM_PORT)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.config import settings

log = logging.getLogger(__name__)

# Input event types that a frontend client may send to control the browser
_INPUT_TYPES = {"input_mouse", "input_keyboard", "input_touch"}


class ViewportProxy:
    """
    One proxy instance per test run.

    Lifecycle:
      start()  – connect to agent-browser, begin forwarding frames
      stop()   – disconnect everything
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._clients: list[WebSocket] = []
        self._ab_ws: websockets.WebSocketClientProtocol | None = None
        self._pump_task: asyncio.Task | None = None
        self._connected = False

    # ── public API ────────────────────────────────────────────────────────────

    async def start(self) -> bool:
        """
        Connect to agent-browser's stream WS.
        Returns True if successful, False if agent-browser isn't streaming yet.
        """
        url = f"ws://localhost:{settings.AGENT_BROWSER_STREAM_PORT}"
        try:
            self._ab_ws = await websockets.connect(url, open_timeout=5)
            self._connected = True
            self._pump_task = asyncio.create_task(self._pump_frames())
            log.info("[run=%s] Connected to agent-browser stream at %s", self.run_id, url)
            return True
        except Exception as exc:
            log.warning("[run=%s] Could not connect to agent-browser stream: %s", self.run_id, exc)
            return False

    async def stop(self) -> None:
        self._connected = False
        if self._pump_task:
            self._pump_task.cancel()
        if self._ab_ws:
            await self._ab_ws.close()
        self._ab_ws = None
        log.info("[run=%s] Viewport proxy stopped", self.run_id)

    async def add_client(self, ws: WebSocket) -> None:
        """Register a new frontend WebSocket client."""
        self._clients.append(ws)
        log.debug("[run=%s] Viewport client added (%d total)", self.run_id, len(self._clients))

    def remove_client(self, ws: WebSocket) -> None:
        try:
            self._clients.remove(ws)
        except ValueError:
            pass
        log.debug("[run=%s] Viewport client removed (%d remaining)", self.run_id, len(self._clients))

    async def forward_input(self, payload: dict[str, Any]) -> None:
        """
        Send an input event from a frontend client to agent-browser.
        Only valid input_* types are forwarded to prevent abuse.
        """
        if payload.get("type") not in _INPUT_TYPES:
            return
        if self._ab_ws and self._connected:
            try:
                await self._ab_ws.send(json.dumps(payload))
            except Exception as exc:
                log.warning("[run=%s] Failed to forward input to agent-browser: %s", self.run_id, exc)

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── internal frame pump ───────────────────────────────────────────────────

    async def _pump_frames(self) -> None:
        """Read frames from agent-browser and broadcast to all frontend clients."""
        try:
            async for raw in self._ab_ws:  # type: ignore[union-attr]
                if not self._clients:
                    continue  # nobody watching yet, skip
                dead: list[WebSocket] = []
                for client in list(self._clients):
                    try:
                        await client.send_text(raw)
                    except Exception:
                        dead.append(client)
                for d in dead:
                    self.remove_client(d)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.warning("[run=%s] Frame pump error: %s", self.run_id, exc)
        finally:
            self._connected = False


# ── Global registry: run_id → ViewportProxy ──────────────────────────────────

class _ProxyRegistry:
    def __init__(self) -> None:
        self._proxies: dict[str, ViewportProxy] = {}

    async def get_or_create(self, run_id: str) -> ViewportProxy:
        if run_id not in self._proxies:
            self._proxies[run_id] = ViewportProxy(run_id)
        return self._proxies[run_id]

    async def start(self, run_id: str) -> bool:
        proxy = await self.get_or_create(run_id)
        if proxy.is_connected:
            return True
        return await proxy.start()

    async def stop(self, run_id: str) -> None:
        proxy = self._proxies.pop(run_id, None)
        if proxy:
            await proxy.stop()

    def get(self, run_id: str) -> ViewportProxy | None:
        return self._proxies.get(run_id)


viewport_registry = _ProxyRegistry()