"""
Утилиты для работы с медиафайлами (MIME-типы и т.п.).
"""
from __future__ import annotations

import mimetypes
from typing import Optional

SUPPORTED_REFERENCE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
}


def _detect_image_mime(data: bytes) -> Optional[str]:
    """Определяет тип изображения по сигнатуре."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def detect_reference_mime(data: bytes, file_path: Optional[str], header_value: Optional[str]) -> str:
    """
    Возвращает допустимый MIME-тип для входного файла, понятный OpenAI Sora.
    """
    header_mime = (header_value or "").split(";", 1)[0].strip().lower()
    if header_mime in SUPPORTED_REFERENCE_MIME_TYPES:
        return header_mime

    if file_path:
        guessed = mimetypes.guess_type(file_path)[0]
        if guessed and guessed in SUPPORTED_REFERENCE_MIME_TYPES:
            return guessed

    image_mime = _detect_image_mime(data)
    if image_mime:
        return image_mime

    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"

    return header_mime or "application/octet-stream"
