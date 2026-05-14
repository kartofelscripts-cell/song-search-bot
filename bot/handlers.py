"""Aiogram routers: command, message and callback handlers."""
from __future__ import annotations

import asyncio
import html
import logging
import secrets
import time
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message

from .config import Config
from .downloader import (
    DownloaderError,
    FileTooLargeError,
    TrackTooLongError,
    download_song,
)
from .keyboards import format_duration, search_results_kb
from .search import SongInfo, search_songs

logger = logging.getLogger(__name__)

router = Router(name="song-search")


class E:
    """Premium custom emoji used in HTML-formatted messages.

    Each `<tg-emoji>` carries a unicode fallback shown to non-Premium users.
    """

    BOT = '<tg-emoji emoji-id="6030400221232501136">🤖</tg-emoji>'
    INFO = '<tg-emoji emoji-id="6028435952299413210">ℹ️</tg-emoji>'
    LOAD = '<tg-emoji emoji-id="5345906554510012647">🔄</tg-emoji>'
    DOWN = '<tg-emoji emoji-id="6039802767931871481">⬇️</tg-emoji>'
    OK = '<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji>'
    ERR = '<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji>'
    PARTY = '<tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji>'
    CLOCK = '<tg-emoji emoji-id="5775896410780079073">🕓</tg-emoji>'
    FILE = '<tg-emoji emoji-id="5870528606328852614">📁</tg-emoji>'
    PEN = '<tg-emoji emoji-id="5870676941614354370">🖋</tg-emoji>'
    LINK = '<tg-emoji emoji-id="5769289093221454192">🔗</tg-emoji>'


@dataclass
class _SearchState:
    results: list[SongInfo]
    created_at: float


# In-memory store: search_id -> SearchState. TTL handled lazily on access.
_searches: dict[str, _SearchState] = {}
# Per-user lock to serialize heavy operations.
_user_locks: dict[int, asyncio.Lock] = {}


def _gc_searches(ttl_s: int) -> None:
    if ttl_s <= 0:
        return
    now = time.time()
    expired = [sid for sid, st in _searches.items() if now - st.created_at > ttl_s]
    for sid in expired:
        _searches.pop(sid, None)


def _user_lock(user_id: int) -> asyncio.Lock:
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock


async def _safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        logger.debug("Failed to edit message", exc_info=True)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    text = (
        f"{E.BOT} <b>Привет!</b> Я ищу песни по названию, исполнителю или строчке из текста "
        f"и присылаю трек в формате <code>.mp4</code>.\n\n"
        f"{E.PEN} Просто отправь мне сообщение — например:\n"
        f"  • <i>Imagine Dragons Believer</i>\n"
        f"  • <i>do you remember the 21st night of september</i>\n\n"
        f"{E.INFO} Команды: /help"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        f"{E.INFO} <b>Как пользоваться</b>\n\n"
        f"{E.PEN} Отправь любой текстовый запрос — название, исполнителя или фрагмент текста.\n"
        f"{E.LOAD} Я найду несколько вариантов и покажу их кнопками.\n"
        f"{E.DOWN} Нажми на нужную песню — скачаю и пришлю <code>.mp4</code>.\n\n"
        f"{E.CLOCK} Стандартный лимит размера файла Telegram Bot API — 50 МБ. "
        f"С локальным Bot API сервером — до 2 ГБ.\n"
        f"{E.ERR} Если ничего не нашлось или произошла ошибка — попробуй уточнить запрос."
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_search_text(message: Message, config: Config) -> None:
    query = (message.text or "").strip()
    if not query:
        return
    if len(query) < 2:
        await message.answer(
            f"{E.ERR} Слишком короткий запрос. Напиши хотя бы пару слов.",
            parse_mode=ParseMode.HTML,
        )
        return

    status = await message.answer(
        f"{E.LOAD} <b>Ищу:</b> <i>{html.escape(query)}</i>…",
        parse_mode=ParseMode.HTML,
    )

    try:
        results = await search_songs(query, limit=config.search_limit)
    except Exception:
        logger.exception("Search failed for query %r", query)
        await _safe_edit(
            status,
            f"{E.ERR} Не удалось выполнить поиск. Попробуй ещё раз.",
        )
        return

    if not results:
        await _safe_edit(
            status,
            f"{E.ERR} Ничего не нашёл по запросу <i>{html.escape(query)}</i>.",
        )
        return

    _gc_searches(config.cache_ttl_s)
    search_id = secrets.token_urlsafe(6)
    _searches[search_id] = _SearchState(results=results, created_at=time.time())

    lines = [
        f"{E.PARTY} <b>Нашёл варианты по запросу</b> <i>{html.escape(query)}</i>:",
        "",
    ]
    for idx, song in enumerate(results, 1):
        lines.append(
            f"<b>{idx}.</b> {html.escape(song.title)} — "
            f"<i>{html.escape(song.uploader)}</i>  "
            f"<code>{format_duration(song.duration)}</code>"
        )
    lines.append("")
    lines.append(f"{E.DOWN} Выбери трек кнопкой ниже:")

    try:
        await status.edit_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=search_results_kb(results, search_id),
        )
    except Exception:
        logger.exception("Failed to render search results")
        await _safe_edit(status, f"{E.ERR} Не удалось показать результаты.")


@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) >= 2:
        _searches.pop(parts[1], None)
    if callback.message is not None:
        await _safe_edit(
            callback.message,
            f"{E.OK} Поиск отменён. Напиши новый запрос, чтобы найти другую песню.",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick(callback: CallbackQuery, bot: Bot, config: Config) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer("Ошибка: нет сообщения", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные кнопки", show_alert=True)
        return
    _, search_id, idx_s = parts
    try:
        idx = int(idx_s)
    except ValueError:
        await callback.answer("Некорректные данные кнопки", show_alert=True)
        return

    _gc_searches(config.cache_ttl_s)
    state = _searches.get(search_id)
    if state is None or idx < 0 or idx >= len(state.results):
        await callback.answer("Истёк срок выбора. Отправь запрос ещё раз.", show_alert=True)
        await _safe_edit(
            callback.message,
            f"{E.ERR} Истёк срок выбора. Отправь запрос ещё раз.",
        )
        return

    song = state.results[idx]
    chat_id = callback.message.chat.id

    await callback.answer("Скачиваю…")

    safe_title = html.escape(song.title)
    safe_artist = html.escape(song.uploader)
    await _safe_edit(
        callback.message,
        f"{E.DOWN} <b>Скачиваю:</b>\n<b>{safe_title}</b> — <i>{safe_artist}</i>",
    )

    async with _user_lock(callback.from_user.id):
        try:
            result = await download_song(
                video_id=song.video_id,
                downloads_dir=config.downloads_dir,
                max_duration_s=config.max_duration_s,
                max_size_bytes=config.max_file_size_bytes,
            )
        except TrackTooLongError as exc:
            logger.info("Track too long: %s", exc)
            await _safe_edit(
                callback.message,
                f"{E.ERR} <b>Трек слишком длинный.</b> Лимит: "
                f"{max(1, config.max_duration_s // 60)} мин.",
            )
            return
        except FileTooLargeError as exc:
            logger.info("File too large: %s", exc)
            await _safe_edit(
                callback.message,
                f"{E.ERR} <b>Файл превышает лимит Telegram</b> "
                f"({exc.size_bytes / 1024 / 1024:.1f} МБ &gt; "
                f"{config.max_file_size_mb} МБ).\n"
                f"Попробуй другой трек или подними лимит локальным Bot API сервером.",
            )
            return
        except DownloaderError as exc:
            logger.warning("Download failed: %s", exc)
            await _safe_edit(
                callback.message,
                f"{E.ERR} <b>Не удалось скачать трек.</b> Попробуй другой вариант.",
            )
            return
        except Exception:
            logger.exception("Unexpected download error")
            await _safe_edit(
                callback.message,
                f"{E.ERR} Неожиданная ошибка при скачивании. Попробуй ещё раз.",
            )
            return

        caption = (
            f"{E.PARTY} <b>{html.escape(result.title)}</b>\n"
            f"<i>{html.escape(result.uploader)}</i>  "
            f"<code>{format_duration(result.duration)}</code>"
        )
        try:
            await bot.send_video(
                chat_id=chat_id,
                video=FSInputFile(result.path, filename=f"{song.video_id}.mp4"),
                caption=caption,
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
            )
        except Exception:
            logger.exception("Failed to send video")
            await _safe_edit(
                callback.message,
                f"{E.ERR} Не удалось отправить файл в чат.",
            )
            return

    try:
        await callback.message.delete()
    except Exception:
        logger.debug("Failed to delete status message", exc_info=True)
