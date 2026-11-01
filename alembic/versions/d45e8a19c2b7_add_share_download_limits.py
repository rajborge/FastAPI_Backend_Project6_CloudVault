"""Add per-share download limits.

Revision ID: d45e8a19c2b7
Revises: c82f41a9d706
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d45e8a19c2b7"
down_revision: Union[str, Sequence[str], None] = "c82f41a9d706"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shared_files",
        sa.Column("max_downloads", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shared_files", "max_downloads")
