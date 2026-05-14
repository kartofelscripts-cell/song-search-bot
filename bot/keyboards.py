"""Inline keyboards used by the bot."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .search import SongInfo

# Telegram inline-button text is rendered as plain text — premium custom emoji
# are NOT supported on inline-keyboard buttons by the Bot API. We use a single
# unicode geometric arrow for "Back", which is not an emoji.
BACK_TEXT = "◁ Назад"


def format_duration(seconds: int) -> str:
    """Format seconds as h:mm:ss or m:ss."""
    if seconds <= 0:
        return "—"
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def search_results_kb(results: list[SongInfo], search_id: str) -> InlineKeyboardMarkup:
    """Return an inline keyboard with one button per search result plus a cancel row."""
    rows: list[list[InlineKeyboardButton]] = []
    # Telegram limits button text to 64 characters. Reserve room for the
    # duration suffix so it never gets cropped.
    max_total = 64
    for idx, song in enumerate(results):
        dur = f" ({format_duration(song.duration)})"
        remaining = max_total - len(dur) - len(" — ")
        title_budget = max(8, remaining * 2 // 3)
        artist_budget = max(4, remaining - title_budget)
        title = _truncate(song.title, title_budget)
        artist = _truncate(song.uploader, artist_budget)
        label = _truncate(f"{title} — {artist}{dur}", max_total)
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"pick:{search_id}:{idx}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=BACK_TEXT, callback_data=f"cancel:{search_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
