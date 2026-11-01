"""Record account-email delivery outcomes without storing raw links."""
from alembic import op
import sqlalchemy as sa

revision = "3e0d95fbc430"
down_revision = "2d9c84eab32f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("account_tokens", sa.Column("delivery_status", sa.String(20), server_default="SENT", nullable=False))
    op.add_column("account_tokens", sa.Column("delivery_error", sa.String(240)))


def downgrade():
    op.drop_column("account_tokens", "delivery_error")
    op.drop_column("account_tokens", "delivery_status")
