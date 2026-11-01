import os


TEST_SETTINGS = {
    "APP_NAME": "CloudVault Tests",
    "APP_VERSION": "0.0.0",
    "DEBUG": "false",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "cloudvault_test",
    "DB_USERNAME": "cloudvault_test",
    "DB_PASSWORD": "test-only",
    "SECRET_KEY": "test-only-secret-for-unit-tests-at-least-32-bytes",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "REFRESH_TOKEN_EXPIRE_DAYS": "30",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    "REDIS_DB": "0",
    "MAIL_HOST": "localhost",
    "MAIL_PORT": "1025",
    "MAIL_USERNAME": "test",
    "MAIL_PASSWORD": "test-only",
    "MAIL_FROM": "test@example.test",
    "MAX_FILE_SIZE_MB": "100",
    "ALLOWED_IMAGE_TYPES": "image/png,image/jpeg",
    "ALLOWED_DOCUMENT_TYPES": "application/pdf,text/plain",
    "WS_HEARTBEAT_INTERVAL": "30",
    "FILE_SHARE_URL": "http://localhost:8000",
    "RATE_LIMIT_ENABLED": "false",
}

for key, value in TEST_SETTINGS.items():
    os.environ.setdefault(key, value)

import app.db.base
