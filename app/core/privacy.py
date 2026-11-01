"""Keep bearer capabilities out of application and server access logs."""

import logging
import re


def redact_path(path: str) -> str:
    path = re.sub(r"([?&]token=)[^&\s]+", r"\1[redacted]", path)
    return re.sub(
        r"(/shares/)(?!share_file(?:[/?\s]|$))[^/?\s]+", r"\1[redacted]", path
    )


class CapabilityFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's AccessFormatter needs its original five-argument tuple.
        # Redact string values in place rather than flattening the record.
        record.msg = redact_path(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_path(value) if isinstance(value, str) else value
                for value in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: redact_path(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        return True


def install_privacy_filters() -> None:
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, CapabilityFilter) for item in logger.filters):
            logger.addFilter(CapabilityFilter())
