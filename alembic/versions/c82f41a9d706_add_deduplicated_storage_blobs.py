"""Add ref-counted content blobs for deduplicated storage.

Revision ID: c82f41a9d706
Revises: a31c8d5e7b42
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c82f41a9d706"
down_revision: Union[str, Sequence[str], None] = "a31c8d5e7b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "storage_blobs",
        sa.Column("storage_backend", sa.String(length=20), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("reference_count", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_backend", "content_sha256", name="uq_storage_blob_backend_sha256"),
        sa.UniqueConstraint("object_key"),
    )
    op.add_column("files", sa.Column("blob_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_files_blob_id_storage_blobs",
        "files",
        "storage_blobs",
        ["blob_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_files_blob_id"), "files", ["blob_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_files_blob_id"), table_name="files")
    op.drop_constraint("fk_files_blob_id_storage_blobs", "files", type_="foreignkey")
    op.drop_column("files", "blob_id")
    op.drop_table("storage_blobs")
