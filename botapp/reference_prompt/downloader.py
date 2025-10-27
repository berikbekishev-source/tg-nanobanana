"""Загрузка референсных видео по внешним ссылкам."""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from typing import Dict, Optional

import yt_dlp


SUPPORTED_DOMAINS = (
    "instagram.com",
    "youtu.be",
    "youtube.com",
    "m.youtube.com",
    "tiktok.com",
    "vm.tiktok.com",
)


@dataclass
class DownloadedMedia:
    """Результат скачивания видео."""

    content: bytes
    mime_type: str
    duration: Optional[float]
    title: Optional[str]
    description: Optional[str]
    width: Optional[int]
    height: Optional[int]


def _select_mime(ext: Optional[str]) -> str:
    if not ext:
        return "video/mp4"
    ext = ext.lower()
    if ext in {"mp4", "m4v"}:
        return "video/mp4"
    if ext in {"webm"}:
        return "video/webm"
    if ext in {"mov"}:
        return "video/quicktime"
    return f"video/{ext}"


def _download_sync(url: str) -> DownloadedMedia:
    with tempfile.TemporaryDirectory(prefix="ref_prompt_") as tmpdir:
        ydl_opts: Dict[str, object] = {
            "format": "mp4/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": False,
            "retries": 2,
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

        if not os.path.exists(filepath):
            raise FileNotFoundError("Не удалось скачать видео по ссылке")

        with open(filepath, "rb") as fh:
            data = fh.read()

    duration = info.get("duration")
    title = info.get("title")
    description = info.get("description")

    width = info.get("width") or info.get("video_width")
    height = info.get("height") or info.get("video_height")

    if isinstance(width, str) and width.isdigit():
        width = int(width)
    if isinstance(height, str) and height.isdigit():
        height = int(height)

    if not width or not height:
        resolution = info.get("resolution") or info.get("format_note")
        if isinstance(resolution, str) and "x" in resolution:
            parts = resolution.lower().split("x", 1)
            try:
                width = int(parts[0])
                height = int(parts[1])
            except (ValueError, IndexError):
                width = None
                height = None

    return DownloadedMedia(
        content=data,
        mime_type=_select_mime(info.get("ext")),
        duration=float(duration) if duration is not None else None,
        title=title,
        description=description,
        width=int(width) if isinstance(width, (int, float)) else None,
        height=int(height) if isinstance(height, (int, float)) else None,
    )


async def download_video(url: str) -> DownloadedMedia:
    """Асинхронная оболочка для скачивания видео."""

    return await asyncio.to_thread(_download_sync, url)


def is_supported_url(url: str) -> bool:
    lowered = url.lower()
    return any(domain in lowered for domain in SUPPORTED_DOMAINS)
