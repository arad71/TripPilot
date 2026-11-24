"""App settings, read from environment variables (or a .env file)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class Settings:
    # LLM
    anthropic_api_key: str
    llm_model: str

    # App
    database_url: str
    public_base_url: str
    cors_origins: list[str]
    admin_token: str
    default_currency: str

    # Affiliate partners
    travelpayouts_token: str
    travelpayouts_marker: str
    booking_aid: str
    extra_links: dict[str, str]

    # Notifications / channels
    alert_webhook_url: str
    telegram_bot_token: str
    telegram_webhook_secret: str


def load_settings() -> Settings:
    return Settings(
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        llm_model=_env("LLM_MODEL", "claude-sonnet-5-5"),
        database_url=_env("DATABASE_URL", "sqlite:///./trippilot.db"),
        public_base_url=_env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
        cors_origins=[o.strip() for o in _env("CORS_ORIGINS").split(",") if o.strip()],
        admin_token=_env("ADMIN_TOKEN"),
        default_currency=_env("DEFAULT_CURRENCY", "aud").lower(),
        travelpayouts_token=_env("TRAVELPAYOUTS_TOKEN"),
        travelpayouts_marker=_env("TRAVELPAYOUTS_MARKER"),
        booking_aid=_env("BOOKING_AID"),
        extra_links={
            "car_rental": _env("CAR_RENTAL_AFFILIATE_URL"),
            "transfer": _env("TRANSFER_AFFILIATE_URL"),
            "esim": _env("ESIM_AFFILIATE_URL"),
            "insurance": _env("INSURANCE_AFFILIATE_URL"),
            "tours": _env("TOURS_AFFILIATE_URL"),
        },
        alert_webhook_url=_env("ALERT_WEBHOOK_URL"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_webhook_secret=_env("TELEGRAM_WEBHOOK_SECRET"),
    )


settings = load_settings()
