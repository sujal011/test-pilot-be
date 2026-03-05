import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stories: Mapped[list["UserStory"]] = relationship(
        "UserStory", back_populates="project", cascade="all, delete-orphan"
    )
    test_cases: Mapped[list["TestCase"]] = relationship(  # noqa: F821
        "TestCase", back_populates="project", cascade="all, delete-orphan"
    )


class UserStory(Base):
    __tablename__ = "user_stories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The URL that should be loaded before any test steps run.
    # The LLM uses this to generate correct navigation steps and the execution
    # engine always opens it first before handing control to the agent.
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    project: Mapped[Project] = relationship("Project", back_populates="stories")
    test_cases: Mapped[list["TestCase"]] = relationship(  # noqa: F821
        "TestCase", back_populates="user_story", cascade="all, delete-orphan"
    )