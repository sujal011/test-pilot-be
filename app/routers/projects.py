from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ProjectCreate, ProjectRead, UserStoryCreate, UserStoryRead
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    service = ProjectService(db)
    project = await service.create_project(data)
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[ProjectRead]:
    service = ProjectService(db)
    projects = await service.list_projects()
    return [ProjectRead.model_validate(p) for p in projects]


@router.post(
    "/{project_id}/stories",
    response_model=UserStoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_story(
    project_id: uuid.UUID,
    data: UserStoryCreate,
    db: AsyncSession = Depends(get_db),
) -> UserStoryRead:
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    story = await service.create_story(project_id, data)
    return UserStoryRead.model_validate(story)


@router.get("/{project_id}/stories", response_model=list[UserStoryRead])
async def list_stories(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[UserStoryRead]:
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    stories = await service.list_stories(project_id)
    return [UserStoryRead.model_validate(s) for s in stories]