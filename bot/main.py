"""Bot entry point: configure logging, build the Dispatcher, run polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import configure_logging, load_config
from .handlers import router

logger = logging.getLogger(__name__)


async def _run() -> None:
    config = load_config()
    configure_logging(config.log_level)
    logger.info(
        "Starting bot (downloads_dir=%s, max_file_size_mb=%d, max_duration_s=%d)",
        config.downloads_dir,
        config.max_file_size_mb,
        config.max_duration_s,
    )

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    try:
        # `config=config` is auto-injected into handler kwargs by aiogram DI.
        await dp.start_polling(bot, config=config)
    finally:
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")


if __name__ == "__main__":
    main()
