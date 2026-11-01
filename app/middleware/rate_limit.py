import hashlib
import hmac

from fastapi import Request
from redis import Redis, RedisError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.core.config import settings

_redis = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
_increment = "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n"


async def rate_limit_middleware(request: Request, call_next):
    protected = request.url.path.startswith(("/auth/", "/shares/"))
    if settings.RATE_LIMIT_ENABLED and protected and request.method != "OPTIONS":
        address = request.client.host if request.client else "unknown"
        # Store no cleartext client IPs in Redis. The proxy must have an explicit
        # trusted address; never consume a user-supplied X-Forwarded-For here.
        digest = hmac.new(
            settings.SECRET_KEY.encode(), address.encode(), hashlib.sha256
        ).hexdigest()
        scope = "auth" if request.url.path.startswith("/auth/") else "share"
        try:
            count = await run_in_threadpool(
                _redis.eval,
                _increment,
                1,
                f"cloudvault:ratelimit:{scope}:{digest}",
                settings.RATE_LIMIT_WINDOW_SECONDS,
            )
        except RedisError:
            return JSONResponse(
                {"detail": "Authentication temporarily unavailable."}, status_code=503
            )
        if count > settings.RATE_LIMIT_REQUESTS:
            return JSONResponse(
                {"detail": "Too many requests. Try again shortly."},
                status_code=429,
                headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if protected:
        response.headers["Cache-Control"] = "no-store"
    return response
