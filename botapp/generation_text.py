"""
Утилиты для формирования сообщений о генерации изображений.
"""
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple


def _trim_prompt(prompt: str, limit: int = 400) -> str:
    if not prompt:
        return ""
    value = prompt.strip()
    if len(value) > limit:
        return value[: limit - 1] + "…"
    return value


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
    prompt_value = _trim_prompt(prompt, limit=400)
    lines = [
        "🎨 Генерация началась! Ожидайте ⏳",
        "",
        f"Модель: {model_name}",
        f"Режим: {mode_label}",
        f"Формат: {format_value}",
        f"Качество: {quality_value}",
        f"Промт: {prompt_value}",
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
    prompt_value = _trim_prompt(prompt, limit=500)
    lines = [
        "✅Готово!",
        "",
        f"Модель: {model_name}",
        f"Режим: {mode_label}",
        f"Формат: {format_value}",
        f"Качество: {quality_value}",
        f"Промт: {prompt_value}",
        "",
        f"Списано: ⚡{charged_amount:.2f}",
        f"Баланс: ⚡{balance_after:.2f}",
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
    prompt_value = _trim_prompt(prompt, limit=400) or "—"
    lines = [
        "🎨 Генерация началась! Ожидайте ⏳",
        "",
        f"Модель: {model_name or '—'}",
        f"Режим: {mode_label or '—'}",
        f"Формат: {aspect_ratio or '—'}",
        f"Разрешение: {resolution or '—'}",
        f"Продолжительность: {_format_duration(duration)}",
        f"Промт: {prompt_value}",
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
    prompt_value = _trim_prompt(prompt, limit=500) or "—"
    lines = [
        "✅Готово!",
        "",
        f"Модель: {model_name or '—'}",
        f"Режим: {mode_label or '—'}",
        f"Формат: {aspect_ratio or '—'}",
        f"Разрешение: {resolution or '—'}",
        f"Продолжительность: {_format_duration(duration)}",
        f"Промт: {prompt_value}",
        "",
        f"Списано: ⚡{Decimal(charged_amount):.2f}",
        f"Баланс: ⚡{Decimal(balance_after):.2f}",
    ]
    return "\n".join(lines)
