"""Idempotent upload completion and stale index protection."""
from alembic import op
import sqlalchemy as sa

revision = "1c8b73dfa21e"
down_revision = "0b7a62ce910d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("files", sa.Column("index_lease", sa.UUID()))
    op.add_column("upload_intents", sa.Column("file_id", sa.UUID(), sa.ForeignKey("files.id", ondelete="SET NULL")))


def downgrade():
    op.drop_column("upload_intents", "file_id")
    op.drop_column("files", "index_lease")
