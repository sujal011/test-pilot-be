from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ReplayCommandRead, TestRunRead
from app.services.execution_service import ExecutionService
from app.utils.ws_manager import ws_manager

router = APIRouter(tags=["test-runs"])


@router.get("/testruns/{run_id}", response_model=TestRunRead)
async def get_test_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TestRunRead:
    service = ExecutionService(db)
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Test run not found")
    return TestRunRead.model_validate(run)


@router.get("/testruns/{run_id}/commands", response_model=list[ReplayCommandRead])
async def get_replay_commands(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ReplayCommandRead]:
    service = ExecutionService(db)
    commands = await service.get_replay_commands(run_id)
    return [ReplayCommandRead.model_validate(c) for c in commands]


@router.post("/testruns/{run_id}/replay")
async def replay_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ExecutionService(db)
    outputs = await service.replay_run(run_id)
    return {"replayed_commands": len(outputs), "outputs": outputs}


# ── WebSocket live log stream ─────────────────────────────────────────────────

@router.websocket("/ws/testruns/{run_id}")
async def websocket_run_logs(websocket: WebSocket, run_id: str) -> None:
    """
    Connect here to receive real-time JSON messages during a test run.

    Message types:
      {"type": "log",     "level": "info|debug|error", "message": "..."}
      {"type": "command", "command": "...", "output": "...", "exit_code": 0}
      {"type": "status",  "status": "running|passed|failed|error"}
      {"type": "summary", "summary": "..."}
    """
    await ws_manager.connect(run_id, websocket)
    try:
        while True:
            # Keep connection alive; messages are pushed by the execution service
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(run_id, websocket)