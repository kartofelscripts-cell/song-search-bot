"""Search songs on YouTube via yt-dlp's ytsearch."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SongInfo:
    """A single search hit."""

    video_id: str
    title: str
    uploader: str
    duration: int  # seconds; 0 if unknown


def _ydl_search_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # extract_flat=in_playlist keeps the search fast: only metadata, no per-video probe.
        "extract_flat": "in_playlist",
        "noplaylist": True,
        "default_search": "ytsearch",
    }


def _run_search(query: str, limit: int) -> list[SongInfo]:
    limit = max(1, min(limit, 25))
    search_query = f"ytsearch{limit}:{query}"
    with YoutubeDL(_ydl_search_opts()) as ydl:
        data = ydl.extract_info(search_query, download=False)

    entries = (data or {}).get("entries") or []
    songs: list[SongInfo] = []
    for entry in entries:
        if not entry:
            continue
        video_id = entry.get("id") or ""
        if not video_id:
            continue
        title = entry.get("title") or "Unknown title"
        uploader = (
            entry.get("uploader")
            or entry.get("channel")
            or entry.get("uploader_id")
            or "Unknown artist"
        )
        duration = int(entry.get("duration") or 0)
        songs.append(
            SongInfo(
                video_id=video_id,
                title=title,
                uploader=uploader,
                duration=duration,
            )
        )
    return songs


async def search_songs(query: str, limit: int = 8) -> list[SongInfo]:
    """Run a ytsearch query in a worker thread and return parsed results."""
    query = query.strip()
    if not query:
        return []
    logger.info("Searching for query=%r limit=%d", query, limit)
    return await asyncio.to_thread(_run_search, query, limit)
