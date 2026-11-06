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

    # Database Configuration (MySQL or SQLite fallback)
    DATABASE_URL: str = "sqlite:///./smartprint.db"

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50

    # Pricing Configuration
    BW_PRICE_PER_PAGE: float = 3.0
    COLOR_PRICE_PER_PAGE: float = 10.0
    CURRENCY: str = "INR"

    # Dynamic UPI Configuration
    PAYMENT_ENABLED: bool = True
    UPI_ID: str = ""
    UPI_NAME: str = "SmartPrint Kiosk"

    # PayU Payment Gateway (Hosted Checkout)
    PAYU_MODE: str = "test"
    PAYU_MERCHANT_KEY: str = ""
    PAYU_MERCHANT_SALT: str = ""
    PAYU_PAYMENT_URL: str = ""
    PAYU_VERIFY_URL: str = ""
    PAYU_SUCCESS_URL: str = ""
    PAYU_FAILURE_URL: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"

    # Automatic payment verification
    # auto     -> use Razorpay when credentials exist, then Cashfree, otherwise demo mode
    # razorpay -> always use Razorpay (errors if credentials are missing)
    # cashfree -> always use Cashfree (errors if credentials are missing)
    # demo     -> never contact a gateway (useful for local demos/tests)
    PAYMENT_PROVIDER: str = "auto"
    DEMO_AUTO_VERIFY_SECONDS: int = 10

    # YouPI-PG Gateway (Local / Self-Hosted UPI Observation Engine)
    YOUPI_API_BASE_URL: str = "http://localhost:6100"
    YOUPI_CHECKOUT_BASE_URL: str = "http://localhost:7000"
    YOUPI_MERCHANT_ID: str = "00000000-0000-0000-0000-000000000001"
    YOUPI_ADMIN_API_TOKEN: str = "9f250f27538f134047993c63dca65cddf8d39e351fa2bff10be236ee2c2ca25c"
    YOUPI_WEBHOOK_SECRET: str = "youpi_test_webhook_secret_key_32bytes_long!"
    YOUPI_AUTO_ACTIVATE: bool = True

    # Razorpay Payment Gateway
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Cashfree Payment Gateway (sandbox by default)
    CASHFREE_ENV: str = "sandbox"  # sandbox | production
    CASHFREE_CLIENT_ID: str = ""
    CASHFREE_CLIENT_SECRET: str = ""
    CASHFREE_WEBHOOK_SECRET: str = ""
    CASHFREE_API_VERSION: str = "2023-08-01"
    CASHFREE_CUSTOMER_PHONE: str = "9999999999"
    CASHFREE_CUSTOMER_EMAIL: str = "customer@smartprint.local"
    CASHFREE_RETURN_URL: str = "http://localhost:5173/"

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
    def payu_configured(self) -> bool:
        """True when both PayU Key and Salt are present and not placeholders."""
        key = (self.PAYU_MERCHANT_KEY or "").strip()
        salt = (self.PAYU_MERCHANT_SALT or "").strip()
        if not key or not salt:
            return False
        if key in ("YOUR_PAYU_MERCHANT_KEY", "CHANGE_ME") or salt in ("YOUR_PAYU_MERCHANT_SALT", "CHANGE_ME"):
            return False
        return True

    @property
    def is_payu_live(self) -> bool:
        """True when PayU is configured to run in production LIVE mode."""
        return (self.PAYU_MODE or "").strip().upper() in ("LIVE", "PRODUCTION")

    @property
    def youpi_configured(self) -> bool:
        """True when YouPI-PG API URL and merchant ID are present."""
        return bool(
            (self.YOUPI_API_BASE_URL or "").strip()
            and (self.YOUPI_MERCHANT_ID or "").strip()
        )

    @property
    def razorpay_configured(self) -> bool:
        """True when both Razorpay API credentials are present."""
        return bool(
            (self.RAZORPAY_KEY_ID or "").strip()
            and (self.RAZORPAY_KEY_SECRET or "").strip()
        )

    @property
    def cashfree_configured(self) -> bool:
        """True when both Cashfree API credentials are present."""
        return bool(
            (self.CASHFREE_CLIENT_ID or "").strip()
            and (self.CASHFREE_CLIENT_SECRET or "").strip()
        )

    @property
    def effective_payment_provider(self) -> str:
        """Resolve which payment provider should be used."""
        provider = (self.PAYMENT_PROVIDER or "auto").strip().lower()

        if provider in ("payu", "youpi", "razorpay", "cashfree", "demo"):
            return provider

        if self.payu_configured:
            return "payu"

        if self.razorpay_configured:
            return "razorpay"

        if self.youpi_configured:
            return "youpi"

        return "cashfree" if self.cashfree_configured else "demo"

    @property
    def cashfree_base_url(self) -> str:
        if (self.CASHFREE_ENV or "").strip().lower() == "production":
            return "https://api.cashfree.com/pg"

        return "https://sandbox.cashfree.com/pg"

    @property
    def sanitized_database_url(self) -> str:
        """Return database URL with password hidden for safe logging."""
        return re.sub(
            r"://([^:]+):([^@]+)@",
            r"://\1:***@",
            self.DATABASE_URL,
        )

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "backend/.env", "../backend/.env"),
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
