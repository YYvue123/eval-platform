from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SECRET_KEY: str = "eval-platform-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    DATABASE_URL: str = "sqlite+aiosqlite:///./eval_platform.db"
    UPLOAD_DIR: str = "./uploads"
    LOG_DIR: str = "./logs"
    LOG_LEVEL: str = "DEBUG"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5
    APP_ENV: str = "dev"
    MTLS_CERT_FILE: str = ""
    MTLS_KEY_FILE: str = ""
    MTLS_CA_FILE: str = ""
    AUDIT_RETENTION_DAYS: int = 180
    AUDIT_RETENTION_RESTRICTED_DAYS: int = 365
    BACKUP_DIR: str = "./backups"
    # L3 / 预发真实模型（仅环境变量注入，勿写入默认密钥）
    L3_MODEL_API_URL: str = ""
    L3_MODEL_API_KEY: str = ""
    L3_MODEL_PRIMARY: str = ""
    L3_MODEL_SECONDARY: str = ""
    L3_MODEL_CHANNEL: str = "https"
    L3_MCP_ENDPOINT: str = "http://127.0.0.1:8765/mcp"


settings = Settings()
