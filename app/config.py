"""Application configuration from environment variables."""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Messenger bots
    bot_token: str = ""
    max_bot_token: str = ""
    max_api_base_url: str = "https://platform-api.max.ru"
    max_polling_timeout_sec: int = 30
    webapp_url: str = ""  # Public HTTPS URL for Mini App, e.g. https://bot.example.com/app

    # Database
    database_url: str = "postgresql+asyncpg://masterbot:masterbot@db:5432/masterbot"
    database_url_sync: str = "postgresql://masterbot:masterbot@db:5432/masterbot"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # App
    app_env: str = "production"
    app_debug: bool = False
    app_secret_key: str = "change-me"
    webapp_session_ttl_sec: int = 86400
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Platform
    platform_name: str = "ПриДел"
    platform_fee_pct: Decimal = Decimal("20.0")
    senior_master_share_pct: Decimal = Decimal("5.0")
    admin_share_pct: Decimal = Decimal("5.0")
    default_currency: str = "RUB"
    default_city: str = "Стерлитамак"
    default_region: str = "Башкортостан"

    # AI
    ai_provider: str = "disabled"
    ai_api_key: str = ""
    ai_api_url: str = ""
    ai_model: str = ""
    ai_timeout_sec: int = 30

    # Payment
    payment_phone: str = ""
    payment_bank_name: str = ""
    payment_recipient_name: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Admin
    owner_telegram_id: int = 0
    admin_telegram_ids: str = ""

    @property
    def is_dev(self) -> bool:
        return self.app_env in ("development", "dev", "test")

    @property
    def admin_ids(self) -> list[int]:
        if not self.admin_telegram_ids:
            return []
        return [int(x.strip()) for x in self.admin_telegram_ids.split(",") if x.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
