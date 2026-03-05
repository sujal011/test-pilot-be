from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ── Project ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


# ── UserStory ─────────────────────────────────────────────────────────────────

class UserStoryCreate(BaseModel):
    title: str
    description: str | None = None
    base_url: str | None = None  # e.g. "https://myapp.com"


class UserStoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    base_url: str | None


# ── TestStep ──────────────────────────────────────────────────────────────────

class TestStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    test_case_id: uuid.UUID
    step_order: int
    natural_language_step: str


class TestStepUpdate(BaseModel):
    natural_language_step: str


# ── TestCase ──────────────────────────────────────────────────────────────────

class TestCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    user_story_id: uuid.UUID | None
    title: str
    description: str | None
    steps: list[TestStepRead] = []


# ── TestRun ───────────────────────────────────────────────────────────────────

class TestRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    test_case_id: uuid.UUID
    status: str
    summary: str | None
    created_at: datetime


# ── ReplayCommand ─────────────────────────────────────────────────────────────

class ReplayCommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    test_run_id: uuid.UUID
    command: str
    output: str | None
    exit_code: int | None
    timestamp: datetime


# ── AI Generation ─────────────────────────────────────────────────────────────

class GeneratedStep(BaseModel):
    step: str


class GeneratedTestCase(BaseModel):
    title: str
    description: str
    steps: list[str]


class GenerateTestsResponse(BaseModel):
    test_cases: list[TestCaseRead]