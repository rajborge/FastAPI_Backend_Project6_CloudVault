from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker

from ..core.config import settings

engine=create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)

SessionLocal=sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

def get_db():
    db=SessionLocal()

    try:
        yield db
    
    finally:
        db.close()