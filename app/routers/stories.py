from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import GenerateTestsResponse, TestCaseRead
from app.services.ai_service import generate_test_cases
from app.services.project_service import ProjectService
from app.services.test_case_service import TestCaseService

router = APIRouter(prefix="/stories", tags=["stories"])


@router.post(
    "/{story_id}/generate-tests",
    response_model=GenerateTestsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_tests_for_story(
    story_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> GenerateTestsResponse:
    project_service = ProjectService(db)
    story = await project_service.get_story(story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="User story not found")

    # base_url is passed to the LLM so steps reference the real URL,
    # and the first step of every generated test case will be "Open <base_url>"
    generated = await generate_test_cases(
        title=story.title,
        description=story.description or "",
        base_url=story.base_url,
    )

    tc_service = TestCaseService(db)
    saved: list[TestCaseRead] = []
    for g in generated:
        tc = await tc_service.create_from_generated(
            project_id=story.project_id,
            user_story_id=story.id,
            generated=g,
        )
        tc_full = await tc_service.get_test_case_with_steps(tc.id)
        saved.append(TestCaseRead.model_validate(tc_full))

    return GenerateTestsResponse(test_cases=saved)