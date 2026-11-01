"""Exercise migrations only against an explicitly configured disposable DB."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

url = os.environ.get("TEST_DATABASE_URL")
if not url or not (make_url(url).database or "").endswith("_test"):
    raise SystemExit("Set TEST_DATABASE_URL to a disposable database ending in _test.")
target = make_url(url)
for key, value in dotenv_values(ROOT / ".env.example").items():
    if value is not None:
        os.environ.setdefault(key, value)
os.environ.update(
    DB_HOST=target.host,
    DB_PORT=str(target.port or 5432),
    DB_NAME=target.database,
    DB_USERNAME=target.username,
    DB_PASSWORD=target.password,
)

from alembic import command
from alembic.config import Config

config = Config(str(ROOT / "alembic.ini"))
config.set_main_option("script_location", str(ROOT / "alembic"))
command.upgrade(config, "head")
# The source project had several broken downgrade paths. Check the full chain,
# including re-upgrade after PostgreSQL enums have been removed.
command.downgrade(config, "base")
command.upgrade(config, "head")
print("Upgrade, full downgrade, and re-upgrade passed.")
