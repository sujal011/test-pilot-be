from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.test_case import TestCase, TestStep
from app.schemas import GeneratedTestCase


class TestCaseService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_test_cases(self, user_story_id: uuid.UUID) -> list[TestCase]:
        """
        Return all test cases for a user story, eagerly loading steps
        so Pydantic can serialise without triggering lazy I/O.
        """
        result = await self.db.execute(
            select(TestCase)
            .options(selectinload(TestCase.steps))
            .where(TestCase.user_story_id == user_story_id)
        )
        return result.scalars().unique().all()

    async def create_from_generated(
        self,
        project_id: uuid.UUID,
        user_story_id: uuid.UUID,
        generated: GeneratedTestCase,
    ) -> TestCase:
        test_case = TestCase(
            project_id=project_id,
            user_story_id=user_story_id,
            title=generated.title,
            description=generated.description,
        )
        self.db.add(test_case)
        await self.db.flush()

        for order, step_text in enumerate(generated.steps, start=1):
            step = TestStep(
                test_case_id=test_case.id,
                step_order=order,
                natural_language_step=step_text,
            )
            self.db.add(step)

        await self.db.flush()
        await self.db.refresh(test_case)
        return test_case

    async def get_test_case_with_steps(self, test_case_id: uuid.UUID) -> TestCase | None:
        result = await self.db.execute(
            select(TestCase)
            .options(selectinload(TestCase.steps))
            .where(TestCase.id == test_case_id)
        )
        return result.scalar_one_or_none()

    async def update_step(
        self, step_id: uuid.UUID, natural_language_step: str
    ) -> TestStep | None:
        step = await self.db.get(TestStep, step_id)
        if step is None:
            return None
        step.natural_language_step = natural_language_step
        await self.db.flush()
        await self.db.refresh(step)
        return step