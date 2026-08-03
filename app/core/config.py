from functools import lru_cache
from pydantic_settings import BaseSettings,SettingsConfigDict

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


    model_config=SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def DATABASE_URL(self)->str:
        return(
            f"postgresql+psycopg://{self.DB_USERNAME}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
    
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