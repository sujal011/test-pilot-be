from __future__ import annotations

from typing import List
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.schemas import TestCaseRead, TestRunRead, TestStepRead, TestStepUpdate
from app.services.test_case_service import TestCaseService

router = APIRouter(tags=["test-cases"])


@router.get(
    "/user-stories/{user_story_id}/test-cases",
    response_model=List[TestCaseRead],
)
async def list_test_cases(
    user_story_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[TestCaseRead]:
    service = TestCaseService(db)
    test_cases = await service.list_test_cases(user_story_id)
    return [TestCaseRead.model_validate(tc) for tc in test_cases]


@router.get("/testcases/{test_case_id}", response_model=TestCaseRead)
async def get_test_case(
    test_case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TestCaseRead:
    service = TestCaseService(db)
    tc = await service.get_test_case_with_steps(test_case_id)
    if tc is None:
        raise HTTPException(status_code=404, detail="Test case not found")
    return TestCaseRead.model_validate(tc)


@router.put("/test-steps/{step_id}", response_model=TestStepRead)
async def update_test_step(
    step_id: uuid.UUID,
    data: TestStepUpdate,
    db: AsyncSession = Depends(get_db),
) -> TestStepRead:
    service = TestCaseService(db)
    step = await service.update_step(step_id, data.natural_language_step)
    if step is None:
        raise HTTPException(status_code=404, detail="Test step not found")
    return TestStepRead.model_validate(step)


@router.post(
    "/testcases/{test_case_id}/run",
    response_model=TestRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_test_case(
    test_case_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> TestRunRead:
    """
    Kick off a test run asynchronously.
    Returns the run ID immediately; connect to WS /ws/testruns/{run_id} for live logs.
    """
    import logging
    from app.models.test_run import TestRun

    log = logging.getLogger(__name__)

    tc_service = TestCaseService(db)
    tc = await tc_service.get_test_case_with_steps(test_case_id)
    if tc is None:
        raise HTTPException(status_code=404, detail="Test case not found")

    run = TestRun(test_case_id=test_case_id, status="pending")
    db.add(run)
    # flush() assigns the PK but does NOT persist — we must commit so that
    # the background task's fresh session can actually find this row.
    await db.flush()
    await db.refresh(run)
    run_id = run.id
    run_read = TestRunRead.model_validate(run)

    # Commit NOW so the TestRun row is visible to the background session.
    await db.commit()
    log.info("[run=%s] TestRun committed, scheduling background execution.", run_id)

    background_tasks.add_task(_execute_in_background, run_id, test_case_id)
    return run_read


async def _execute_in_background(run_id: uuid.UUID, test_case_id: uuid.UUID) -> None:
    import logging
    from sqlalchemy import select
    from app.models.test_run import TestRun
    from app.services.execution_service import ExecutionService
    from app.utils.ws_manager import ws_manager

    log = logging.getLogger(__name__)
    log.info("[run=%s] Background execution task started.", run_id)

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(TestRun).where(TestRun.id == run_id))
            run = result.scalar_one_or_none()
            if run is None:
                log.error(
                    "[run=%s] TestRun not found in background task — "
                    "did the HTTP handler commit before scheduling?",
                    run_id,
                )
                return

            log.info("[run=%s] Found TestRun, handing off to ExecutionService.", run_id)
            service = ExecutionService(session)
            await service._run_existing(run, test_case_id)
            await session.commit()
            log.info("[run=%s] Background execution finished and committed.", run_id)
        except Exception as exc:
            log.exception("[run=%s] Background execution crashed: %s", run_id, exc)
            await session.rollback()
            await ws_manager.send_log(str(run_id), "error", f"Run crashed: {exc}")
            await ws_manager.send_status(str(run_id), "error")