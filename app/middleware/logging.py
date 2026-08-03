import time

from fastapi import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("request")


async def logging_middleware(
    request: Request,
    call_next,
) -> Response:
    """
    Logs every incoming HTTP request along with:
    - Method
    - Path
    - Status Code
    - Execution Time
    """

    start_time = time.perf_counter()

    try:
        response = await call_next(request)

        duration = (time.perf_counter() - start_time) * 1000

        message = (
            "%s %s -> %s (%.2f ms)"
        )

        if response.status_code >= 500:
            logger.error(
                message,
                request.method,
                request.url.path,
                response.status_code,
                duration,
            )

        elif duration >= settings.SLOW_REQUEST_THRESHOLD:
            logger.warning(
                message,
                request.method,
                request.url.path,
                response.status_code,
                duration,
            )

        else:
            logger.info(
                message,
                request.method,
                request.url.path,
                response.status_code,
                duration,
            )

        return response

    except Exception:
        duration = (time.perf_counter() - start_time) * 1000

        logger.exception(
            "%s %s -> Unhandled Exception (%.2f ms)",
            request.method,
            request.url.path,
            duration,
        )

        raise