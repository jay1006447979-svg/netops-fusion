"""全局配置"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    APP_NAME: str = "NetOps Fusion"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.environ.get("DEBUG", "true").lower() == "true"
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", 5000))

    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'netops.db'}"
    )

    DATA_DIR: Path = BASE_DIR / "data"
    MANUAL_DIR: Path = DATA_DIR / "manuals"
    TEMPLATE_DIR: Path = DATA_DIR / "templates"

    SSH_DEFAULT_TIMEOUT: int = 30
    SSH_DEFAULT_PORT: int = 22
    SERIAL_DEFAULT_BAUDRATE: int = 9600

    TASK_LOG_MAX_LINES: int = 1000


settings = Settings()
