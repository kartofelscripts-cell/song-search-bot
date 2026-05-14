"""Download tracks from YouTube via yt-dlp, producing an .mp4 file."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_dlp import DownloadError, YoutubeDL

logger = logging.getLogger(__name__)


class DownloaderError(Exception):
    """Base downloader error."""


class TrackTooLongError(DownloaderError):
    """Track duration exceeds the configured limit."""


class FileTooLargeError(DownloaderError):
    """Resulting file exceeds the configured size limit."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            f"Downloaded file is {size_bytes / 1024 / 1024:.1f} MB, "
            f"exceeds limit of {max_bytes / 1024 / 1024:.0f} MB"
        )
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    title: str
    uploader: str
    duration: int


def _ydl_download_opts(downloads_dir: Path) -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "outtmpl": str(downloads_dir / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        # Prefer a pre-merged mp4 capped at 480p (small files, fits in Telegram's
        # 50 MB upload limit for typical 3-5 minute tracks). Fall back to any
        # mp4 video, then to audio-only m4a (which is the mp4 container too).
        "format": (
            "best[ext=mp4][height<=480]/best[ext=mp4]/"
            "bestaudio[ext=m4a]/best"
        ),
        "postprocessors": [
            {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
        ],
        "retries": 3,
        "fragment_retries": 3,
    }


def _resolve_output(downloads_dir: Path, video_id: str) -> Path | None:
    candidate = downloads_dir / f"{video_id}.mp4"
    if candidate.exists():
        return candidate
    # Fallback if the remuxer left a different extension.
    for ext in ("mkv", "webm", "m4a", "mp3"):
        alt = downloads_dir / f"{video_id}.{ext}"
        if alt.exists():
            return alt
    return None


def _metadata_only(video_id: str) -> dict[str, Any]:
    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        return ydl.extract_info(url, download=False) or {}


def _run_download(
    video_id: str,
    downloads_dir: Path,
    max_duration_s: int,
    max_size_bytes: int,
) -> DownloadResult:
    url = f"https://www.youtube.com/watch?v={video_id}"
    cached = downloads_dir / f"{video_id}.mp4"
    if cached.exists() and cached.stat().st_size > 0:
        size = cached.stat().st_size
        if size > max_size_bytes:
            raise FileTooLargeError(size_bytes=size, max_bytes=max_size_bytes)
        logger.info("Reusing cached file %s (%d bytes)", cached, size)
        info = _metadata_only(video_id)
        return DownloadResult(
            path=cached,
            title=info.get("title") or video_id,
            uploader=info.get("uploader") or info.get("channel") or "",
            duration=int(info.get("duration") or 0),
        )

    opts = _ydl_download_opts(downloads_dir)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
        duration = int(info.get("duration") or 0)
        if max_duration_s > 0 and duration > max_duration_s:
            raise TrackTooLongError(
                f"Track duration {duration}s exceeds limit of {max_duration_s}s"
            )
        try:
            ydl.download([url])
        except DownloadError as exc:
            raise DownloaderError(str(exc)) from exc

    out_path = _resolve_output(downloads_dir, video_id)
    if out_path is None:
        raise DownloaderError(
            f"yt-dlp did not produce an output file for video_id={video_id}"
        )
    if out_path.suffix.lower() != ".mp4":
        renamed = out_path.with_suffix(".mp4")
        out_path.rename(renamed)
        out_path = renamed

    size = out_path.stat().st_size
    if size > max_size_bytes:
        try:
            out_path.unlink()
        except OSError:
            logger.debug("Failed to remove oversize file %s", out_path, exc_info=True)
        raise FileTooLargeError(size_bytes=size, max_bytes=max_size_bytes)

    return DownloadResult(
        path=out_path,
        title=info.get("title") or video_id,
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=duration,
    )


async def download_song(
    video_id: str,
    downloads_dir: Path,
    max_duration_s: int,
    max_size_bytes: int,
) -> DownloadResult:
    """Download a YouTube video to an .mp4 file in a worker thread."""
    logger.info("Downloading video_id=%s", video_id)
    return await asyncio.to_thread(
        _run_download,
        video_id,
        downloads_dir,
        max_duration_s,
        max_size_bytes,
    )
