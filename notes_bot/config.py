from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    database_url: str
    mini_app_url: str | None = None
    ai_provider: str | None = None
    ai_provider_url: str | None = None
    ai_provider_api_key: str | None = None
    ai_provider_model: str | None = None


def load_config() -> Config:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    mini_app_url = os.getenv("MINI_APP_URL", "").strip() or None
    raw_admin_ids = os.getenv("ADMIN_IDS", "")
    ai_provider = os.getenv("AI_PROVIDER", "").strip().lower() or None
    ai_provider_url = os.getenv("AI_PROVIDER_URL", "").strip() or None
    ai_provider_api_key = os.getenv("AI_PROVIDER_API_KEY", "").strip() or None
    ai_provider_model = os.getenv("AI_PROVIDER_MODEL", "").strip() or None

    if not bot_token:
        raise ValueError("BOT_TOKEN is required; set it in the local .env file.")
    if not database_url:
        raise ValueError("DATABASE_URL is required; set it in the local .env file.")
    if urlparse(database_url).scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must be a PostgreSQL connection URL.")
    if mini_app_url and urlparse(mini_app_url).scheme != "https":
        raise ValueError("MINI_APP_URL must use HTTPS.")

    try:
        admin_ids = frozenset(int(value.strip()) for value in raw_admin_ids.split(",") if value.strip())
    except ValueError as exc:
        raise ValueError("ADMIN_IDS must be comma-separated numeric Telegram user IDs.") from exc

    if not admin_ids or any(admin_id <= 0 for admin_id in admin_ids):
        raise ValueError("ADMIN_IDS must contain at least one positive Telegram user ID.")

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        database_url=database_url,
        mini_app_url=mini_app_url,
        ai_provider=ai_provider,
        ai_provider_url=ai_provider_url,
        ai_provider_api_key=ai_provider_api_key,
        ai_provider_model=ai_provider_model,
    )
