from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from app.api import search


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_schedular()
    try:
        yield
    finally:
        stop_schedular()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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