"""
Viewport streaming endpoints.

POST /testruns/{run_id}/stream/start
    Connects the server-side proxy to the agent-browser stream WS.
    Call this after kicking off a test run (the browser must already be open).

POST /testruns/{run_id}/stream/stop
    Disconnects the proxy.

GET  /testruns/{run_id}/stream/status
    Returns whether the proxy is currently connected.

WS   /ws/testruns/{run_id}/viewport
    Frontend connects here to receive live viewport frames (base64 JPEG) and
    to send input events (mouse / keyboard / touch) back to the browser.

Frame message (from agent-browser, forwarded as-is):
    {
      "type": "frame",
      "data": "<base64-jpeg>",
      "metadata": { "deviceWidth": 1280, "deviceHeight": 720, ... }
    }

Status message (from agent-browser):
    { "type": "status", "connected": true, "screencasting": true, ... }

Input event (frontend → browser):
    { "type": "input_mouse",    "eventType": "mousePressed", "x": 100, "y": 200, ... }
    { "type": "input_keyboard", "eventType": "keyDown",      "key": "Enter", ... }
    { "type": "input_touch",    "eventType": "touchStart",   "touchPoints": [...] }
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.services.streaming_service import viewport_registry

log = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])


# ── REST control endpoints ────────────────────────────────────────────────────

@router.post("/testruns/{run_id}/stream/start")
async def start_stream(run_id: str) -> dict:
    """
    Connect the server-side proxy to agent-browser's viewport WebSocket.

    agent-browser exposes ws://localhost:AGENT_BROWSER_STREAM_PORT automatically
    when AGENT_BROWSER_STREAM_PORT is set in the environment (which cli_runner.py
    injects for every subprocess). Call this endpoint once the browser is open.
    """
    ok = await viewport_registry.start(run_id)
    if not ok:
        raise HTTPException(
            status_code=503,
            detail=(
                "Could not connect to agent-browser stream. "
                "Make sure a browser session is running and "
                "AGENT_BROWSER_STREAM_PORT is set correctly."
            ),
        )
    return {"status": "connected", "run_id": run_id}


@router.post("/testruns/{run_id}/stream/stop")
async def stop_stream(run_id: str) -> dict:
    """Disconnect the proxy and free resources."""
    await viewport_registry.stop(run_id)
    return {"status": "stopped", "run_id": run_id}


@router.get("/testruns/{run_id}/stream/status")
async def stream_status(run_id: str) -> dict:
    proxy = viewport_registry.get(run_id)
    return {
        "run_id": run_id,
        "connected": proxy.is_connected if proxy else False,
    }


# ── WebSocket viewport proxy ──────────────────────────────────────────────────

@router.websocket("/ws/testruns/{run_id}/viewport")
async def viewport_ws(websocket: WebSocket, run_id: str) -> None:
    """
    Bidirectional viewport proxy.

    Outbound (server → client):  frame and status messages from agent-browser.
    Inbound  (client → server):  input events forwarded to agent-browser so a
                                  human can interact alongside the AI agent.

    The proxy is started automatically if it isn't connected yet, which allows
    a frontend to open this socket and then call /stream/start in any order.
    """
    await websocket.accept()

    # Auto-start proxy if not already running
    proxy = viewport_registry.get(run_id)
    if proxy is None or not proxy.is_connected:
        ok = await viewport_registry.start(run_id)
        if not ok:
            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": (
                        "agent-browser stream not available. "
                        "Open a browser session first."
                    ),
                })
            )
            await websocket.close()
            return

    proxy = viewport_registry.get(run_id)
    assert proxy is not None
    await proxy.add_client(websocket)

    try:
        while True:
            # Listen for input events from the frontend client
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                await proxy.forward_input(payload)
            except json.JSONDecodeError:
                pass  # ignore malformed messages
    except WebSocketDisconnect:
        proxy.remove_client(websocket)
    except Exception as exc:
        log.warning("[run=%s] Viewport WS error: %s", run_id, exc)
        proxy.remove_client(websocket)