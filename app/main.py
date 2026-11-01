from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.privacy import install_privacy_filters

from app.middleware.logging import logging_middleware
from app.core.exception_handlers import register_exception_handlers
from app.schedular.cleanup_schedular import start_schedular
from app.schedular.cleanup_schedular import stop_schedular

from app.api import auth
from app.api import users
from app.api import folder
from app.api import files
from app.api import shares
from app.api import health
from app.api import permissions
from app.api import audit
from app.api import search, account, collaboration, operations
from app.middleware.rate_limit import rate_limit_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    install_privacy_filters()
    if settings.SCHEDULER_ENABLED:
        start_schedular()
    try:
        yield
    finally:
        if settings.SCHEDULER_ENABLED:
            stop_schedular()


app = FastAPI(lifespan=lifespan)


@app.get("/", include_in_schema=False)
def account_link_redirect(account_action: str = "", token: str = ""):
    """Support already-sent account links which pointed at the local API."""
    from fastapi import HTTPException
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode

    if account_action not in {"verify", "reset", "forgot", "request-verification"}:
        raise HTTPException(404, "Not found")
    return RedirectResponse(
        settings.account_frontend_url + "/?" + urlencode({"account_action": account_action, "token": token}),
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(folder.router)
app.include_router(files.router)
app.include_router(shares.router)
app.include_router(health.router)
app.include_router(permissions.router)
app.include_router(audit.router)
app.include_router(search.router)

app.middleware("http")(logging_middleware)

app.include_router(account.router)
app.middleware("http")(rate_limit_middleware)

app.include_router(collaboration.router)
app.include_router(operations.router)

# Keep CORS outermost so rate-limit errors remain readable by the frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-CloudVault-Download-Link"],
)
