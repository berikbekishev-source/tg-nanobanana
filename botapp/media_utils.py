"""
Утилиты для работы с медиафайлами (MIME-типы и т.п.).
"""
from __future__ import annotations

from io import BytesIO
import mimetypes
from typing import Optional, Tuple

from PIL import Image, UnidentifiedImageError

SUPPORTED_REFERENCE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
}

_PIL_FORMAT_BY_MIME = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}

_MIME_BY_PIL_FORMAT = {value: key for key, value in _PIL_FORMAT_BY_MIME.items()}


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


def prepare_image_for_dimensions(
    data: bytes,
    target_width: int,
    target_height: int,
    *,
    preferred_mime: Optional[str] = None,
) -> Tuple[bytes, str, bool]:
    """
    Подгоняет изображение под нужные размеры:
    - центрирует и обрезает под требуемое соотношение
    - ресайзит до точных ширины/высоты
    Возвращает (байты, mime, изменялось ли изображение).
    """
    if target_width <= 0 or target_height <= 0:
        return data, preferred_mime or "image/png", False

    mime_hint = (preferred_mime or "").lower()
    try:
        with Image.open(BytesIO(data)) as img:
            img_format = img.format or _PIL_FORMAT_BY_MIME.get(mime_hint)
            width, height = img.size
            if width <= 0 or height <= 0:
                return data, preferred_mime or "image/png", False

            target_ratio = target_width / target_height
            current_ratio = width / height
            changed = False

            if abs(current_ratio - target_ratio) > 1e-3:
                if current_ratio > target_ratio:
                    new_width = int(height * target_ratio)
                    offset = (width - new_width) // 2
                    box = (offset, 0, offset + new_width, height)
                else:
                    new_height = int(width / target_ratio)
                    offset = (height - new_height) // 2
                    box = (0, offset, width, offset + new_height)
                img = img.crop(box)
                width, height = img.size
                changed = True

            if width != target_width or height != target_height:
                img = img.resize((target_width, target_height), Image.LANCZOS)
                changed = True

            if not changed:
                resulting_mime = mime_hint or _MIME_BY_PIL_FORMAT.get(img_format, "image/png")
                return data, resulting_mime, False

            if mime_hint == "image/jpeg":
                img = img.convert("RGB")

            save_format = _PIL_FORMAT_BY_MIME.get(mime_hint) or img_format or "PNG"
            buffer = BytesIO()
            img.save(buffer, format=save_format)
            resulting_mime = _MIME_BY_PIL_FORMAT.get(save_format, "image/png")
            return buffer.getvalue(), resulting_mime, True
    except (UnidentifiedImageError, OSError, ValueError):
        return data, preferred_mime or "application/octet-stream", False
