from functools import lru_cache
from pydantic_settings import BaseSettings,SettingsConfigDict
from pydantic import model_validator
from typing import Literal

class Settings(BaseSettings):
    #===================
    #Application
    #===================
    APP_NAME:str
    APP_VERSION:str
    DEBUG:bool

    #===================
    #Database
    #===================
    DB_HOST:str
    DB_PORT:int
    DB_NAME:str
    DB_USERNAME:str
    DB_PASSWORD:str

    #===================
    #JWT
    #===================
    SECRET_KEY: str
    ALGORITHM: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

    # ===========================
    # Redis
    # ===========================
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int

    # ===========================
    # Email
    # ===========================
    MAIL_HOST: str
    MAIL_PORT: int
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str

    # ===========================
    # AWS
    # ===========================
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = ""
    AWS_BUCKET_NAME: str = ""

    # ===========================
    # Cloudflare R2
    # ===========================
    R2_ENDPOINT_URL: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_PRESIGNED_URL_TTL_SECONDS: int = 600
    R2_UPLOAD_MULTIPART_THRESHOLD_MB: int = 100
    R2_MULTIPART_PART_SIZE_MB: int = 16
    UPLOAD_INTENT_TTL_MINUTES: int = 60

    # ===========================
    # Malware scanning
    # ===========================
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    CLAMAV_TIMEOUT_SECONDS: int = 300

    # ===========================
    # Uploads
    # ===========================
    MAX_FILE_SIZE_MB: int

    ALLOWED_IMAGE_TYPES: str
    ALLOWED_DOCUMENT_TYPES: str

    # ===========================
    # WebSocket
    # ===========================
    WS_HEARTBEAT_INTERVAL: int

    LOG_LEVEL:str="INFO"
    SLOW_REQUEST_THRESHOLD: float = 1000

    FILE_SHARE_URL:str
    ACCOUNT_FRONTEND_URL: str = ""
    ENVIRONMENT: Literal["development", "production", "test"] = "development"

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    SCHEDULER_ENABLED: bool = False
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 20
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    REFRESH_COOKIE_SECURE: bool = False
    MFA_ENCRYPTION_KEY: str = ""
    REQUIRE_VERIFIED_EMAIL: bool = False
    MAIL_STARTTLS: bool = True
    MAIL_SSL: bool = False
    MAIL_AUTH_ENABLED: bool = True
    EMBEDDING_MODEL: str = ""
    OCR_MAX_PAGES: int = 40
    OCR_MAX_PIXELS: int = 20_000_000

    @model_validator(mode="after")
    def validate_deployment(self):
        origins = [value.strip() for value in self.CORS_ORIGINS.split(',') if value.strip()]
        if not origins or '*' in origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins.")
        if self.ENVIRONMENT == "production":
            if self.DEBUG or len(self.SECRET_KEY.encode()) < 32 or self.SECRET_KEY.startswith('replace-'):
                raise ValueError("Production requires DEBUG=false and a random JWT secret of at least 32 bytes.")
            if not self.FILE_SHARE_URL.startswith('https://') or any(not origin.startswith('https://') for origin in origins):
                raise ValueError("Production frontend URLs and CORS origins must use HTTPS.")
            if not self.RATE_LIMIT_ENABLED:
                raise ValueError("Production requires authentication rate limiting.")
        return self


    model_config=SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def account_frontend_url(self) -> str:
        from urllib.parse import urlsplit

        if self.ACCOUNT_FRONTEND_URL:
            return self.ACCOUNT_FRONTEND_URL.rstrip("/")
        url = urlsplit(self.FILE_SHARE_URL)
        if self.ENVIRONMENT != "production" and url.hostname in {"localhost", "127.0.0.1", "api"} and url.port == 8000:
            return next((origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()), "http://localhost:5173")
        return self.FILE_SHARE_URL.rstrip("/")

    @property
    def DATABASE_URL(self)->str:
        from sqlalchemy.engine import URL
        return URL.create(
            "postgresql+psycopg", username=self.DB_USERNAME,
            password=self.DB_PASSWORD, host=self.DB_HOST,
            port=self.DB_PORT, database=self.DB_NAME,
        ).render_as_string(hide_password=False)
    
    @property
    def REDIS_URL(self)->str:
        return(
            f"redis://{self.REDIS_HOST}:"
            f"{self.REDIS_PORT}/{self.REDIS_DB}"
        )
    
@lru_cache
def get_settings()-> Settings:
    return Settings()
    
settings=get_settings()
