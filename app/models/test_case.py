import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_stories.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="test_cases")  # noqa: F821
    user_story: Mapped["UserStory | None"] = relationship(  # noqa: F821
        "UserStory", back_populates="test_cases"
    )
    steps: Mapped[list["TestStep"]] = relationship(
        "TestStep", back_populates="test_case", cascade="all, delete-orphan",
        order_by="TestStep.step_order"
    )
    runs: Mapped[list["TestRun"]] = relationship(  # noqa: F821
        "TestRun", back_populates="test_case", cascade="all, delete-orphan"
    )


class TestStep(Base):
    __tablename__ = "test_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    natural_language_step: Mapped[str] = mapped_column(Text, nullable=False)

    test_case: Mapped[TestCase] = relationship("TestCase", back_populates="steps")