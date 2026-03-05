from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, UserStory
from app.schemas import ProjectCreate, UserStoryCreate


class ProjectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_project(self, data: ProjectCreate) -> Project:
        project = Project(name=data.name, description=data.description)
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def list_projects(self) -> list[Project]:
        result = await self.db.execute(select(Project).order_by(Project.created_at.desc()))
        return list(result.scalars().all())

    async def get_project(self, project_id: uuid.UUID) -> Project | None:
        return await self.db.get(Project, project_id)

    async def create_story(
        self, project_id: uuid.UUID, data: UserStoryCreate
    ) -> UserStory:
        story = UserStory(
            project_id=project_id,
            title=data.title,
            description=data.description,
            base_url=data.base_url,
        )
        self.db.add(story)
        await self.db.flush()
        await self.db.refresh(story)
        return story

    async def list_stories(self, project_id: uuid.UUID) -> list[UserStory]:
        result = await self.db.execute(
            select(UserStory).where(UserStory.project_id == project_id)
        )
        return list(result.scalars().all())

    async def get_story(self, story_id: uuid.UUID) -> UserStory | None:
        return await self.db.get(UserStory, story_id)