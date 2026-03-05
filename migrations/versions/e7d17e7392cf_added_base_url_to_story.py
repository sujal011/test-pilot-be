"""added base_url to story

Revision ID: e7d17e7392cf
Revises: 
Create Date: 2026-03-05 23:33:14.265438

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e7d17e7392cf'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add the new base_url column to user_stories without dropping any tables
    op.add_column(
        "user_stories",
        sa.Column("base_url", sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove the base_url column from user_stories
    op.drop_column("user_stories", "base_url")
