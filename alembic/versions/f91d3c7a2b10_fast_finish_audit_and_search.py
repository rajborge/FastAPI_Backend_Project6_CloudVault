"""fast finish: preserve audit history and add content search

Revision ID: f91d3c7a2b10
Revises: e8d2c65a91bf
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f91d3c7a2b10"
down_revision: Union[str, Sequence[str], None] = "e8d2c65a91bf"
branch_labels = None
depends_on = None


def _fk_name(column: str) -> str | None:
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys("audit_logs"):
        if fk.get("constrained_columns") == [column]:
            return fk.get("name")
    return None


def upgrade() -> None:
    # Keep audit history when a file/folder is permanently removed.
    file_fk = _fk_name("file_id")
    folder_fk = _fk_name("folder_id")
    if file_fk:
        op.drop_constraint(file_fk, "audit_logs", type_="foreignkey")
    if folder_fk:
        op.drop_constraint(folder_fk, "audit_logs", type_="foreignkey")

    op.create_foreign_key(
        "audit_logs_file_id_fkey",
        "audit_logs",
        "files",
        ["file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "audit_logs_folder_id_fkey",
        "audit_logs",
        "folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # pgvector foundation for content search.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE file_search_documents (
            file_id UUID PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
            extracted_text TEXT NOT NULL DEFAULT '',
            embedding vector(384),
            indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_file_search_documents_indexed_at "
        "ON file_search_documents (indexed_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS file_search_documents")

    file_fk = _fk_name("file_id")
    folder_fk = _fk_name("folder_id")
    if file_fk:
        op.drop_constraint(file_fk, "audit_logs", type_="foreignkey")
    if folder_fk:
        op.drop_constraint(folder_fk, "audit_logs", type_="foreignkey")

    op.create_foreign_key(
        "audit_logs_file_id_fkey",
        "audit_logs",
        "files",
        ["file_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "audit_logs_folder_id_fkey",
        "audit_logs",
        "folders",
        ["folder_id"],
        ["id"],
        ondelete="CASCADE",
    )
