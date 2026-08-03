from fastapi import FastAPI

from app.middleware.logging import logging_middleware
from app.core.exception_handlers import register_exception_handlers
from app.schedular.cleanup_schedular import start_schedular

from app.api import auth
from app.api import users
from app.api import folder
from app.api import files
from app.api import shares

app = FastAPI()
start_schedular()
register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(folder.router)
app.include_router(files.router)
app.include_router(shares.router)

app.middleware("http")(logging_middleware)