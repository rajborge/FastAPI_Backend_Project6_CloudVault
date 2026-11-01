"""Add owner and commenter permission roles.

Revision ID: e8d2c65a91bf
Revises: d45e8a19c2b7
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e8d2c65a91bf"
down_revision: Union[str, Sequence[str], None] = "d45e8a19c2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE permissionrole ADD VALUE IF NOT EXISTS 'OWNER'")
    op.execute("ALTER TYPE permissionrole ADD VALUE IF NOT EXISTS 'COMMENTER'")


def downgrade() -> None:
    # Explicitly reduce newer roles to the nearest supported capability.
    op.execute("UPDATE permissions SET role = 'EDITOR' WHERE role::text = 'OWNER'")
    op.execute("UPDATE permissions SET role = 'VIEWER' WHERE role::text = 'COMMENTER'")
    op.execute("ALTER TABLE permissions ALTER COLUMN role TYPE text USING role::text")
    op.execute("ALTER TYPE permissionrole RENAME TO permissionrole_old")
    op.execute("CREATE TYPE permissionrole AS ENUM ('VIEWER', 'EDITOR')")
    op.execute(
        "ALTER TABLE permissions ALTER COLUMN role TYPE permissionrole "
        "USING role::permissionrole"
    )
    op.execute("DROP TYPE permissionrole_old")
