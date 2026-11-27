from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    APP_NAME: str = "MiniCron"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False

    # Server binding
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    ADMIN_PASSWORD: SecretStr = Field(min_length=12)
    SECRET_KEY: SecretStr = Field(min_length=32)
    TOKEN_EXPIRE_DAYS: int = 7

    # Directories
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = DATA_DIR / "logs"
    SCRIPTS_DIR: Path = BASE_DIR / "scripts"
    DB_PATH: Path = DATA_DIR / "minicron.db"

settings = Settings()

# Ensure critical runtime directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
