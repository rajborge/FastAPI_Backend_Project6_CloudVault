"""Add SHA-256 digest metadata to files.

Revision ID: 6a7e3c91bd20
Revises: dba74ac90149
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a7e3c91bd20"
down_revision: Union[str, Sequence[str], None] = "dba74ac90149"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_files_content_sha256"),
        "files",
        ["content_sha256"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_files_content_sha256"), table_name="files")
    op.drop_column("files", "content_sha256")
