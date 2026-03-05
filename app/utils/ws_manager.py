import asyncio
import json
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class ConnectionManager:
    """Manages WebSocket connections grouped by test-run ID."""

    def __init__(self) -> None:
        # run_id -> list of active WebSockets
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[run_id].append(ws)

    def disconnect(self, run_id: str, ws: WebSocket) -> None:
        self._connections[run_id].remove(ws)
        if not self._connections[run_id]:
            del self._connections[run_id]

    async def broadcast(self, run_id: str, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(run_id, [])):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._connections[run_id].remove(ws)
            except ValueError:
                pass

    async def send_log(self, run_id: str, level: str, message: str) -> None:
        await self.broadcast(run_id, {"type": "log", "level": level, "message": message})

    async def send_command(
        self,
        run_id: str,
        command: str,
        output: str,
        exit_code: int,
    ) -> None:
        await self.broadcast(
            run_id,
            {
                "type": "command",
                "command": command,
                "output": output,
                "exit_code": exit_code,
            },
        )

    async def send_status(self, run_id: str, status: str) -> None:
        await self.broadcast(run_id, {"type": "status", "status": status})

    async def send_summary(self, run_id: str, summary: str) -> None:
        await self.broadcast(run_id, {"type": "summary", "summary": summary})


ws_manager = ConnectionManager()