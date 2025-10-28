"""Загрузка референсных видео по внешним ссылкам."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from dataclasses import dataclass
from typing import Dict, Optional

import yt_dlp
import httpx


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
    # Попытка обхода Instagram без авторизации через ddinstagram
    if "instagram.com" in url:
        dd_result = _download_instagram_via_ddinstagram(url)
        if dd_result:
            return dd_result

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


_INSTAGRAM_SHORTCODE_RE = re.compile(
    r"instagram\.com/(?:reel|p|shorts)/([A-Za-z0-9_\-]+)/?"
)


def _download_instagram_via_ddinstagram(insta_url: str) -> Optional[DownloadedMedia]:
    """Пытаемся скачать видео Instagram через ddinstagram без авторизации.

    Возвращает DownloadedMedia или None, если получить не удалось.
    """

    match = _INSTAGRAM_SHORTCODE_RE.search(insta_url)
    if not match:
        return None

    shortcode = match.group(1)
    dd_url = f"https://ddinstagram.com/reel/{shortcode}"

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/129.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=True) as client:
            page = client.get(dd_url, headers=headers)
            page.raise_for_status()
            html = page.text

            video_url = (
                _extract_meta_content(html, "og:video")
                or _extract_meta_content(html, "og:video:secure_url")
            )
            if not video_url:
                # Некоторые зеркала ddinstagram отдают JSON с downloadUrl
                json_candidate = _extract_json_download(html)
                if json_candidate:
                    video_url = json_candidate
                else:
                    return None

            if video_url.startswith("//"):
                video_url = "https:" + video_url

            if not video_url.startswith("http"):
                return None

            video_resp = client.get(video_url, headers=headers)
            video_resp.raise_for_status()

            mime_type = video_resp.headers.get("Content-Type", "video/mp4")
            title = _extract_meta_content(html, "og:title")
            description = _extract_meta_content(html, "og:description")
            width = _parse_int(_extract_meta_content(html, "og:video:width"))
            height = _parse_int(_extract_meta_content(html, "og:video:height"))

            return DownloadedMedia(
                content=video_resp.content,
                mime_type=mime_type,
                duration=None,
                title=title,
                description=description,
                width=width,
                height=height,
            )
    except Exception:
        return None

    return None


def _extract_meta_content(html: str, property_name: str) -> Optional[str]:
    pattern = re.compile(
        rf'<meta[^>]+property=["\']{re.escape(property_name)}["\'][^>]+content=["\']([^"\']+)["\']',
        flags=re.IGNORECASE,
    )
    match = pattern.search(html)
    if match:
        return match.group(1)
    return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


_JSON_DOWNLOAD_RE = re.compile(
    r'"download_urls?"\s*:\s*\[\s*"([^"\s]+)"\s*\]', re.IGNORECASE
)


def _extract_json_download(html: str) -> Optional[str]:
    match = _JSON_DOWNLOAD_RE.search(html)
    if match:
        return match.group(1)
    return None
