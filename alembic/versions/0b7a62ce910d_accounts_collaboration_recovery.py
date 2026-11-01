"""Account security, file revisions, comments, notifications, and job recovery."""
from alembic import op
import sqlalchemy as sa

revision = "0b7a62ce910d"
down_revision = "f91d3c7a2b10"
branch_labels = None
depends_on = None


def common():
    return [sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.add_column("users", sa.Column("auth_version", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("mfa_secret", sa.String(512)))
    op.add_column("users", sa.Column("mfa_pending_secret", sa.String(512)))
    op.add_column("users", sa.Column("mfa_last_step", sa.BigInteger(), server_default="-1", nullable=False))
    op.add_column("files", sa.Column("version_of", sa.UUID(), sa.ForeignKey("files.id", ondelete="CASCADE")))
    op.create_index("ix_files_version_of", "files", ["version_of"])
    op.add_column("files", sa.Column("scan_started_at", sa.DateTime(timezone=True)))
    op.add_column("files", sa.Column("scan_lease", sa.UUID()))
    op.add_column("files", sa.Column("index_status", sa.String(20), server_default="PENDING", nullable=False))
    op.add_column("files", sa.Column("index_error", sa.String(300)))
    op.create_index("ix_files_recovery", "files", ["scan_status", "updated_at"])
    op.create_table("comments", *common(),
        sa.Column("file_id", sa.UUID(), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False))
    op.create_index("ix_comments_file_id", "comments", ["file_id"])
    op.create_index("ix_comments_user_id", "comments", ["user_id"])
    op.create_table("account_tokens", *common(),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("digest", sa.String(64), unique=True, nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])
    op.create_table("notifications", *common(),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(), unique=True, nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.UUID(), sa.ForeignKey("files.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("message", sa.String(500), nullable=False))
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.execute("ALTER TABLE file_search_documents ADD COLUMN embedding_model TEXT NOT NULL DEFAULT 'lexical-v1'")
    op.execute("CREATE INDEX ix_search_embedding ON file_search_documents USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX ix_search_text ON file_search_documents USING gin (to_tsvector('english', extracted_text))")


def downgrade():
    op.execute("DROP INDEX ix_search_text")
    op.execute("DROP INDEX ix_search_embedding")
    op.drop_column("file_search_documents", "embedding_model")
    for table in ("notifications", "account_tokens", "comments"):
        op.drop_table(table)
    op.drop_index("ix_files_recovery", table_name="files")
    op.drop_index("ix_files_version_of", table_name="files")
    for column in ("version_of", "scan_started_at", "scan_lease", "index_status", "index_error"):
        op.drop_column("files", column)
    for column in ("auth_version", "mfa_secret", "mfa_pending_secret", "mfa_last_step"):
        op.drop_column("users", column)
