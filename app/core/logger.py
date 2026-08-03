import logging
from logging import Logger
from pathlib import Path
from logging.handlers import RotatingFileHandler
from ..core.config import settings

LOG_LEVEL=getattr(logging,settings.LOG_LEVEL.upper(),logging.info)

LOG_DIR=Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE=LOG_DIR / "app.log"

logging.basicConfig(
    level=LOG_LEVEL,
    format=(
        "%(asctime)s | "
        "%(levelname)-8s | "
        "%(name)s | "
        "%(message)s"
    ),
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            filename=LOG_FILE,
            maxBytes=5*1024*1024,
            backupCount=5,
        ),
    ],
)

logger:Logger=logging.getLogger("cloudvault")

def get_logger(name:str)->logging.Logger:
    return logging.getLogger(f"cloudvault.{name}")