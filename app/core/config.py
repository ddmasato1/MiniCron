import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "MiniCron"
    APP_VERSION: str = "1.1.0"
    DEBUG: bool = False

    # Server binding
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "minicron-super-secure-secret-key-change-in-prod")
    TOKEN_EXPIRE_DAYS: int = 7

    # Directories
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = DATA_DIR / "logs"
    SCRIPTS_DIR: Path = BASE_DIR / "scripts"
    DB_PATH: Path = DATA_DIR / "minicron.db"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure critical runtime directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
