import os
import re
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and environment configurations."""

    APP_NAME: str = "SmartPrint Backend"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False

    # MySQL Database Configuration
    DATABASE_URL: str = ""

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50

    # Pricing Configuration
    BW_PRICE_PER_PAGE: float = 2.0
    COLOR_PRICE_PER_PAGE: float = 5.0
    CURRENCY: str = "INR"

    # Payment Configuration
    PAYMENT_ENABLED: bool = False
    UPI_ID: str = ""
    UPI_NAME: str = "SmartPrint"

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(
        cls, v: Union[str, List[str]]
    ) -> List[str]:
        if isinstance(v, str):
            return [
                origin.strip()
                for origin in v.split(",")
                if origin.strip()
            ]
        return v

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def sanitized_database_url(self) -> str:
        """Return database URL with password hidden for safe logging."""
        return re.sub(
            r"://([^:]+):([^@]+)@",
            r"://\1:***@",
            self.DATABASE_URL,
        )

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Railway may provide MYSQL_URL using mysql://.
# SQLAlchemy should use PyMySQL explicitly.
if settings.DATABASE_URL.startswith("mysql://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace(
        "mysql://",
        "mysql+pymysql://",
        1,
    )

# Ensure uploads directory exists on disk.
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
