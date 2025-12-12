"""
Утилиты для формирования сообщений о генерации изображений.
"""
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple


def _trim_prompt(prompt: str, limit: int = 3500) -> str:
    """Обрезает промпт только если он длиннее limit символов."""
    if not prompt:
        return ""
    value = prompt.strip()
    if len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def _format_prompt_for_copy(prompt: str) -> str:
    """Форматирует промпт для копирования (моноширинный блок)."""
    if not prompt:
        return ""
    # Экранируем HTML-спецсимволы
    escaped = (
        prompt
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"<code>{escaped}</code>"


def resolve_image_mode_label(generation_type: str, image_mode: Optional[str] = None) -> str:
    mode = (image_mode or "").lower()
    if mode == "remix":
        return "Ремикс"
    if generation_type == "image2image":
        return "Изображение → Изображение"
    return "Текст → Изображение"


def resolve_format_and_quality(
    provider: str,
    params: Optional[Dict[str, Any]] = None,
    aspect_ratio: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Достаёт человекочитаемые значения «Формат» и «Качество» из параметров запроса.
    """
    params = params or {}
    format_value = (
        params.get("size")
        or params.get("resolution")
        or params.get("aspect_ratio")
        or params.get("aspectRatio")
        or params.get("format")
        or aspect_ratio
        or "—"
    )

    quality_value = (
        params.get("quality")
        or params.get("image_size")
        or params.get("imageSize")
        or params.get("image_quality")
        or None
    )

    if provider not in {"gemini_vertex", "gemini", "openai_image"}:
        quality_value = quality_value or "—"

    if not format_value:
        format_value = "—"
    return str(format_value), str(quality_value or "—")


def format_image_start_message(
    model_name: str,
    mode_label: str,
    format_value: str,
    quality_value: str,
    prompt: str,
) -> str:
    """Формирует HTML-сообщение о старте генерации изображения."""
    prompt_trimmed = _trim_prompt(prompt, limit=3500)
    prompt_formatted = _format_prompt_for_copy(prompt_trimmed)
    lines = [
        "🎨 Генерация началась! Ожидайте ⏳",
        "",
        f"<b>Модель:</b> {model_name}",
        f"<b>Режим:</b> {mode_label}",
        f"<b>Формат:</b> {format_value}",
        f"<b>Качество:</b> {quality_value}",
        f"<b>Промпт:</b> {prompt_formatted}",
        "",
        "Я отправлю вам результат, как только он будет готов!",
    ]
    return "\n".join(lines)


def format_image_result_message(
    model_name: str,
    mode_label: str,
    format_value: str,
    quality_value: str,
    prompt: str,
    charged_amount: Decimal,
    balance_after: Decimal,
) -> str:
    """Формирует HTML-сообщение с результатом генерации изображения."""
    prompt_trimmed = _trim_prompt(prompt, limit=3500)
    prompt_formatted = _format_prompt_for_copy(prompt_trimmed)
    lines = [
        "✅Готово!",
        "",
        f"<b>Модель:</b> {model_name}",
        f"<b>Режим:</b> {mode_label}",
        f"<b>Формат:</b> {format_value}",
        f"<b>Качество:</b> {quality_value}",
        f"<b>Промпт:</b> {prompt_formatted}",
        "",
        f"<b>Списано:</b> ⚡{charged_amount:.2f}",
        f"<b>Баланс:</b> ⚡{balance_after:.2f}",
    ]
    return "\n".join(lines)


def resolve_video_mode_label(generation_type: str) -> str:
    mode = (generation_type or "").lower()
    if mode == "image2video":
        return "Изображение → Видео"
    if mode == "video2video":
        return "Видео → Видео"
    return "Текст → Видео"


def _format_duration(value: Optional[Any]) -> str:
    if value is None:
        return "—"
    try:
        numeric = float(value)
        if numeric.is_integer():
            numeric = int(numeric)
        return f"{numeric} сек."
    except (TypeError, ValueError):
        return str(value)


def format_video_start_message(
    model_name: str,
    mode_label: str,
    aspect_ratio: Optional[str],
    resolution: Optional[str],
    duration: Optional[Any],
    prompt: str,
) -> str:
    """Формирует HTML-сообщение о старте генерации видео."""
    prompt_trimmed = _trim_prompt(prompt, limit=3500) or "—"
    prompt_formatted = _format_prompt_for_copy(prompt_trimmed) if prompt_trimmed != "—" else "—"
    lines = [
        "🎨 Генерация началась! Ожидайте ⏳",
        "",
        f"<b>Модель:</b> {model_name or '—'}",
        f"<b>Режим:</b> {mode_label or '—'}",
        f"<b>Формат:</b> {aspect_ratio or '—'}",
        f"<b>Разрешение:</b> {resolution or '—'}",
        f"<b>Продолжительность:</b> {_format_duration(duration)}",
        f"<b>Промпт:</b> {prompt_formatted}",
        "",
        "Я отправлю вам результат, как только он будет готов!",
    ]
    return "\n".join(lines)


def format_video_result_message(
    model_name: str,
    mode_label: str,
    aspect_ratio: Optional[str],
    resolution: Optional[str],
    duration: Optional[Any],
    prompt: str,
    charged_amount: Decimal,
    balance_after: Decimal,
) -> str:
    """Формирует HTML-сообщение с результатом генерации видео."""
    prompt_trimmed = _trim_prompt(prompt, limit=3500) or "—"
    prompt_formatted = _format_prompt_for_copy(prompt_trimmed) if prompt_trimmed != "—" else "—"
    lines = [
        "✅Готово!",
        "",
        f"<b>Модель:</b> {model_name or '—'}",
        f"<b>Режим:</b> {mode_label or '—'}",
        f"<b>Формат:</b> {aspect_ratio or '—'}",
        f"<b>Разрешение:</b> {resolution or '—'}",
        f"<b>Продолжительность:</b> {_format_duration(duration)}",
        f"<b>Промпт:</b> {prompt_formatted}",
        "",
        f"<b>Списано:</b> ⚡{Decimal(charged_amount):.2f}",
        f"<b>Баланс:</b> ⚡{Decimal(balance_after):.2f}",
    ]
    return "\n".join(lines)
