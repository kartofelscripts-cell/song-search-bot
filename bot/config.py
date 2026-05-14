"""Configuration loader: reads environment variables from .env / process env."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the bot."""

    bot_token: str
    log_level: str
    downloads_dir: Path
    max_file_size_mb: int
    max_duration_s: int
    search_limit: int
    cache_ttl_s: int

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"Environment variable {name} must be an integer, got: {raw!r}"
        ) from exc


def load_config() -> Config:
    """Load configuration from environment (with optional .env file)."""
    load_dotenv()

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and add your bot "
            "token (obtain one from @BotFather in Telegram)."
        )

    downloads_dir = Path(
        os.getenv("DOWNLOADS_DIR", "./downloads")
    ).expanduser().resolve()
    downloads_dir.mkdir(parents=True, exist_ok=True)

    search_limit = _get_int("SEARCH_LIMIT", 8)
    if search_limit < 1:
        search_limit = 1
    if search_limit > 25:
        search_limit = 25

    return Config(
        bot_token=token,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        downloads_dir=downloads_dir,
        max_file_size_mb=_get_int("MAX_FILE_SIZE_MB", 50),
        max_duration_s=_get_int("MAX_DURATION_S", 1800),
        search_limit=search_limit,
        cache_ttl_s=_get_int("CACHE_TTL_S", 1800),
    )


def configure_logging(level: str) -> None:
    """Configure root logging with a consistent format."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
