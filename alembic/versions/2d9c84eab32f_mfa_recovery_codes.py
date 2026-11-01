"""Hashed, single-use MFA recovery codes."""
from alembic import op
import sqlalchemy as sa

revision = "2d9c84eab32f"
down_revision = "1c8b73dfa21e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("mfa_recovery_hashes", sa.JSON(), server_default="[]", nullable=False))


def downgrade():
    op.drop_column("users", "mfa_recovery_hashes")
