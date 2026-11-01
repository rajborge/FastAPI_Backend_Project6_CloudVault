"""Add upload sessions, quota reservations, and file storage states.

Revision ID: a31c8d5e7b42
Revises: 6a7e3c91bd20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a31c8d5e7b42"
down_revision: Union[str, Sequence[str], None] = "6a7e3c91bd20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "storage_reserved",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "storage_backend",
            sa.String(length=20),
            server_default="local",
            nullable=False,
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "scan_status",
            sa.String(length=20),
            server_default="PENDING_SCAN",
            nullable=False,
        ),
    )
    op.create_table(
        "upload_intents",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("folder_id", sa.UUID(), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("expected_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("multipart_upload_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        op.f("ix_upload_intents_folder_id"),
        "upload_intents",
        ["folder_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_intents_status"),
        "upload_intents",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_intents_user_id"),
        "upload_intents",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_upload_intents_folder_id"), table_name="upload_intents")
    op.drop_index(op.f("ix_upload_intents_user_id"), table_name="upload_intents")
    op.drop_index(op.f("ix_upload_intents_status"), table_name="upload_intents")
    op.drop_table("upload_intents")
    op.drop_column("files", "scan_status")
    op.drop_column("files", "storage_backend")
    op.drop_column("users", "storage_reserved")
