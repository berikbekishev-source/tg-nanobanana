"""
Клавиатуры для навигации по боту согласно ТЗ
"""
from typing import List, Sequence, Tuple, Optional
from decimal import Decimal
from django.conf import settings
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from botapp.models import AIModel
from botapp.reference_prompt import REFERENCE_PROMPT_PRICING_SLUG
from botapp.business.pricing import (
    get_base_price_tokens,
    get_pricing_settings,
    usd_to_retail_tokens,
)
from botapp.generation_text import (
    format_image_result_message,
    format_video_result_message,
    format_video_start_message,
    resolve_format_and_quality,
    resolve_image_mode_label,
    resolve_video_mode_label,
)


# === ГЛАВНОЕ МЕНЮ ===

def get_main_menu_keyboard(payment_url: str) -> ReplyKeyboardMarkup:
    """
    Главное меню бота
    payment_url - ссылка на Mini App для оплаты
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎨 Создать изображение"),
                KeyboardButton(text="🎬 Создать видео")
            ],
            [
                KeyboardButton(text="💰 Мой баланс (цены)"),
                # Кнопка пополнить баланс сразу открывает Mini App
                KeyboardButton(
                    text="💳 Пополнить баланс",
                    web_app=WebAppInfo(url=payment_url)
                )
            ],
            [
                KeyboardButton(text="📲 Промт по референсу"),
            ],
            [
                KeyboardButton(text="🏠Главное меню"),
            ],
            [
                KeyboardButton(text="🎁 Ввести промокод"),
            ],
            [
                KeyboardButton(text="🧡 Поддержка")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


# === ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ ===

def get_image_models_keyboard(
    models: List[AIModel],
    midjourney_webapps: Optional[dict] = None,
    gpt_image_webapps: Optional[dict] = None,
    nano_banana_webapps: Optional[dict] = None,
) -> InlineKeyboardMarkup:
    """Шаг 1: Выбор модели для изображений"""
    builder = InlineKeyboardBuilder()
    midjourney_webapps = midjourney_webapps or {}
    gpt_image_webapps = gpt_image_webapps or {}
    nano_banana_webapps = nano_banana_webapps or {}

    for model in models:
        if model.type == 'image' and model.is_active:
            if model.slug == "nano-banana":
                continue
            # Для Midjourney и GPT Image сразу открываем WebApp, остальные — через callback
            if model.provider == "midjourney" and midjourney_webapps.get(model.slug):
                builder.button(
                    text=model.display_name,
                    web_app=WebAppInfo(url=midjourney_webapps[model.slug]),
                )
            elif model.provider == "openai_image" and gpt_image_webapps.get(model.slug):
                builder.button(
                    text=model.display_name,
                    web_app=WebAppInfo(url=gpt_image_webapps[model.slug]),
                )
            elif (
                model.provider in {"gemini_vertex", "gemini"}
                and model.slug.startswith("nano-banana")
                and nano_banana_webapps.get(model.slug)
            ):
                builder.button(
                    text=model.display_name,
                    web_app=WebAppInfo(url=nano_banana_webapps[model.slug]),
                )
            else:
                builder.button(
                    text=model.display_name,
                    callback_data=f"img_model:{model.slug}"
                )

    builder.adjust(1)

    return builder.as_markup()


# === ГЕНЕРАЦИЯ ВИДЕО ===

def get_video_models_keyboard(
    models: List[AIModel],
    kling_webapps: Optional[dict] = None,
    veo_webapps: Optional[dict] = None,
    sora_webapps: Optional[dict] = None,
    midjourney_video_webapps: Optional[dict] = None,
    runway_webapps: Optional[dict] = None,
) -> InlineKeyboardMarkup:
    """Шаг 1: Выбор модели для видео"""
    builder = InlineKeyboardBuilder()
    kling_webapps = kling_webapps or {}
    veo_webapps = veo_webapps or {}
    sora_webapps = sora_webapps or {}
    midjourney_video_webapps = midjourney_video_webapps or {}
    runway_webapps = runway_webapps or {}

    for model in models:
        if model.type == 'video' and model.is_active:
            if model.slug == REFERENCE_PROMPT_PRICING_SLUG:
                continue
            if model.provider == "kling" and kling_webapps.get(model.slug):
                builder.button(
                    text=model.display_name,
                    web_app=WebAppInfo(url=kling_webapps[model.slug]),
                )
            elif model.provider == "veo" and veo_webapps.get(model.slug):
                builder.button(
                    text=model.display_name,
                    web_app=WebAppInfo(url=veo_webapps[model.slug]),
                )
            elif model.provider == "openai" and sora_webapps.get(model.slug):
                builder.button(
                    text=model.display_name,
                    web_app=WebAppInfo(url=sora_webapps[model.slug]),
                )
            elif model.provider == "midjourney" and midjourney_video_webapps.get(model.slug):
                builder.button(
                    text=model.display_name,
                    web_app=WebAppInfo(url=midjourney_video_webapps[model.slug]),
                )
            elif model.provider == "useapi" and runway_webapps.get(model.slug):
                button_text = "🎞️ Runway Aleph" if model.slug == "runway_aleph" else model.display_name
                builder.button(
                    text=button_text,
                    web_app=WebAppInfo(url=runway_webapps[model.slug]),
                )
            else:
                builder.button(
                    text=model.display_name,
                    callback_data=f"vid_model:{model.slug}"
                )

    builder.adjust(1)

    return builder.as_markup()

def get_video_format_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора формата видео."""
    builder = InlineKeyboardBuilder()
    builder.button(text="9:16 (Vertical)", callback_data="video_format:9:16")
    builder.button(text="16:9 (Horizontal)", callback_data="video_format:16:9")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def get_video_duration_keyboard(durations: Sequence[int]) -> InlineKeyboardMarkup:
    """Клавиатура выбора длительности ролика."""
    builder = InlineKeyboardBuilder()
    for duration in durations:
        builder.button(
            text=f"{duration} сек",
            callback_data=f"video_duration:{duration}",
        )
    if builder.buttons:
        builder.adjust(len(durations) if len(durations) <= 3 else 3)
    return builder.as_markup()


def get_video_resolution_keyboard(resolutions: Sequence[str]) -> InlineKeyboardMarkup:
    """Клавиатура выбора качества видео."""
    builder = InlineKeyboardBuilder()
    for value in resolutions:
        label = value.upper().replace("P", "p")
    builder.button(text=label, callback_data=f"video_resolution:{value.lower()}")
    if builder.buttons:
        builder.adjust(len(resolutions) if len(resolutions) <= 3 else 3)
    return builder.as_markup()


# === ПРОМТ ПО РЕФФЕРЕНСУ ===

def get_reference_prompt_models_keyboard(models: Sequence[Tuple[str, str]]) -> InlineKeyboardMarkup:
    """Inline клавиатура выбора модели для генерации промта по референсу."""
    builder = InlineKeyboardBuilder()

    for slug, title in models:
        builder.button(
            text=title,
            callback_data=f"ref_prompt_model:{slug}"
        )

    if builder.buttons:
        builder.adjust(1)
    return builder.as_markup()


def get_reference_prompt_mods_keyboard() -> InlineKeyboardMarkup:
    """Inline клавиатура выбора необходимости правок перед сборкой промта."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Внести правки", callback_data="ref_prompt_mods:edit")
    builder.button(text="✅ Без правок", callback_data="ref_prompt_mods:skip")
    builder.adjust(1)
    return builder.as_markup()


# === БАЛАНС ===

def get_balance_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для раздела баланса
    Показывается после нажатия "Мой баланс (цены)"
    Выводится вместе с сообщением о текущем балансе пользователя
    """
    builder = InlineKeyboardBuilder()

    # Кнопка пополнить баланс сразу открывает Mini App
    builder.button(text="💳 Пополнить баланс", web_app=WebAppInfo(url=payment_url))
    builder.button(text="🎁 Ввести промокод", callback_data="enter_promocode")
    builder.adjust(1)

    return builder.as_markup()


# === ОПЛАТА ===

def get_payment_mini_app_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для открытия Mini App оплаты
    Используется в разделе баланса при нажатии на inline кнопку
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="💳 Открыть страницу оплаты",
        web_app=WebAppInfo(url=payment_url)
    )

    builder.adjust(1)
    return builder.as_markup()


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Простая кнопка отмены"""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()


def get_support_keyboard() -> InlineKeyboardMarkup:
    """Кнопка для перехода в чат с админом"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Открыть чат с админом",
        url="https://t.me/berik_smmpro"
    )
    builder.adjust(1)
    return builder.as_markup()


def get_main_menu_inline_keyboard(payment_url: Optional[str] = None) -> ReplyKeyboardMarkup:
    """
    Возврат в главное меню (reply клавиатура).
    Используется там, где ранее была inline-кнопка.
    """
    url = payment_url or getattr(settings, "PAYMENT_MINI_APP_URL", "https://example.com/payment")
    return get_main_menu_keyboard(url)


def format_balance(balance: Decimal) -> str:
    """Форматирование баланса для отображения"""
    return f"⚡ {balance:.2f} токенов"


def get_model_info_message(model: AIModel, base_price: Optional[Decimal] = None) -> str:
    """
    Формирует сообщение с информацией о модели (Шаг 2)
    """
    price_value = base_price if base_price is not None else get_base_price_tokens(model)
    return (
        f"{model.display_name}\n\n"
        f"Стоимость ⚡{price_value:.2f} токенов\n\n"
        "Выберите режим генерации 👇"
    )


def get_image_mode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора режима генерации изображений."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Создать из текста", callback_data="image_mode:text")
    builder.button(text="🪄 Отредактировать", callback_data="image_mode:edit")
    builder.button(text="🎭 Ремикс", callback_data="image_mode:remix")
    builder.adjust(1)
    return builder.as_markup()


MODEL_PRICE_PRESETS: List[Tuple[str, str]] = [
    ("⚡ Veo 3.1 Fast", "veo3-fast"),
    ("🍌 Nano Banana", "nano-banana"),
    ("🍌 Nano Banana Pro", "nano-banana-pro"),
    ("Ⓜ️ Midjourney", "midjourney-v7-fast"),
    ("🎞️ Midjourney Video", "midjourney-video"),
    ("🌀 Kling v2-5-turbo", "kling-v2-5-turbo"),
    ("🖼️ GPT Image 1", "gpt-image-1"),
    ("🎥 Sora 2", "sora2"),
    ("🏁 Runway Gen-4", "runway_gen4"),
    ("🏁 Runway Aleph", "runway_aleph"),
]


def _get_unit_price_tokens(model: AIModel) -> Decimal:
    """
    Возвращает стоимость базовой единицы модели (1 изображение / 1 секунда).
    Для видео игнорируем значение duration в default_params, чтобы выводить
    цену именно за одну секунду, а не за дефолтную длительность модели.
    """
    if model.cost_unit == model.CostUnit.SECOND:
        cost_usd = model.base_cost_usd or model.unit_cost_usd or Decimal('0.0000')
        if cost_usd <= 0:
            return Decimal('0.00')
        return usd_to_retail_tokens(cost_usd)
    return get_base_price_tokens(model)


def get_prices_info(balance: Decimal) -> str:
    """Возвращает текст для раздела баланса по заданному шаблону."""
    settings = get_pricing_settings()
    usd_per_token = (Decimal('1') / settings.usd_to_token_rate).quantize(Decimal('0.01'))

    lines: List[str] = []
    lines.append("💰 Ваш текущий баланс:")
    lines.append(f"⚡ {balance:.2f} токенов")
    lines.append("")
    lines.append(f"1 токен ≈ ${usd_per_token}")
    lines.append("Токены — внутренняя валюта в боте, которой оплачиваете генерации.")
    lines.append("")
    lines.append("💰 Текущие цены:")
    lines.append("")

    unit_labels = {
        AIModel.CostUnit.SECOND: "за 1 сек.",
        AIModel.CostUnit.IMAGE: "за 1 изображение",
        AIModel.CostUnit.GENERATION: "за генерацию",
    }
    available_models = {m.slug: m for m in AIModel.objects.filter(is_active=True)}
    has_midjourney_video_preset = any(slug == "midjourney-video" for _, slug in MODEL_PRICE_PRESETS)
    added_slugs: set[str] = set()
    midjourney_video_added = False
    image_price_lines: List[str] = []
    video_price_lines: List[str] = []

    def _push_price_line(model_obj: AIModel, title_label: str) -> None:
        base_price = _get_unit_price_tokens(model_obj)
        suffix = unit_labels.get(model_obj.cost_unit, "за генерацию")
        line = f"{title_label} — ⚡{base_price:.2f} токенов {suffix}"
        if model_obj.type == "video":
            video_price_lines.append(line)
        else:
            image_price_lines.append(line)

    for title, slug in MODEL_PRICE_PRESETS:
        model = available_models.get(slug)
        if not model:
            continue
        _push_price_line(model, title)
        added_slugs.add(slug)
        if "midjourney" in slug:
            midjourney_video_added = midjourney_video_added or "video" in slug
            if not midjourney_video_added and not has_midjourney_video_preset:
                candidate = available_models.get("midjourney-video") or next(
                    (
                        m for m in available_models.values()
                        if m.provider == "midjourney" and m.type == "video" and m.slug not in added_slugs
                    ),
                    None,
                )
                if candidate:
                    video_title = candidate.display_name or "Midjourney Video"
                    _push_price_line(candidate, f"🎞️ {video_title}")
                    added_slugs.add(candidate.slug)
                    midjourney_video_added = True

    if image_price_lines:
        lines.append("🖼️ Генерация изображений:")
        lines.extend(image_price_lines)
        lines.append("")
    if video_price_lines:
        lines.append("🎬 Генерация видео:")
        lines.extend(video_price_lines)
        lines.append("")

    lines.append("")
    lines.append(
        "Стоимость пакетов токенов на кнопках «Пополнить баланс» / «Купить токены»."
    )

    return "\n".join(lines)


def get_generation_start_message(
    *,
    model: str,
    mode: Optional[str],
    aspect_ratio: Optional[str],
    resolution: Optional[str],
    duration: Optional[int],
    prompt: str,
) -> str:
    """Системное сообщение перед началом генерации видео."""
    return format_video_start_message(
        model_name=model,
        mode_label=resolve_video_mode_label(mode or ""),
        aspect_ratio=aspect_ratio or "—",
        resolution=resolution or "—",
        duration=duration,
        prompt=prompt,
    )


def get_generation_complete_message(
    prompt: str,
    generation_type: str,
    model_name: str,
    *,
    model_display_name: Optional[str] = None,
    model_hashtag: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Системное сообщение после завершения генерации

    Args:
        prompt: Промт пользователя
        generation_type: Тип генерации (text2image, image2image, text2video, image2video)
        model_name: Название модели
        model_display_name: Выводимое имя модели (если нужно отличать от хэштега)
        **kwargs: Дополнительные параметры (duration, resolution, aspect_ratio и т.д.)
    """
    gtype = (generation_type or "").lower()

    if "video" in gtype:
        params = kwargs.get("generation_params") or kwargs.get("params") or {}
        aspect_ratio = kwargs.get("aspect_ratio") or params.get("aspect_ratio") or params.get("aspectRatio")
        resolution = kwargs.get("resolution") or kwargs.get("video_resolution") or params.get("resolution")
        duration = kwargs.get("duration") or params.get("duration") or params.get("seconds")
        charged_amount = kwargs.get("charged_amount")
        balance_after = kwargs.get("balance_after")

        return format_video_result_message(
            model_display_name or model_name,
            resolve_video_mode_label(generation_type),
            aspect_ratio or "—",
            resolution or "—",
            duration,
            prompt,
            Decimal(charged_amount or "0.00"),
            Decimal(balance_after or "0.00"),
        )

    params = kwargs.get("generation_params") or kwargs.get("params") or kwargs
    aspect_ratio = kwargs.get("aspect_ratio")
    if aspect_ratio is None and isinstance(params, dict):
        aspect_ratio = params.get("aspect_ratio") or params.get("aspectRatio")

    format_value, quality_value = resolve_format_and_quality(
        kwargs.get("model_provider") or "",
        params,
        aspect_ratio=aspect_ratio,
    )
    mode_label = resolve_image_mode_label(
        generation_type,
        kwargs.get("image_mode") or (params or {}).get("image_mode"),
    )
    charged_amount = kwargs.get("charged_amount")
    balance_after = kwargs.get("balance_after")
    if charged_amount is None:
        charged_amount = Decimal("0.00")
    if balance_after is None:
        balance_after = Decimal("0.00")

    return format_image_result_message(
        model_display_name or model_name,
        mode_label,
        format_value,
        quality_value,
        prompt,
        Decimal(charged_amount),
        Decimal(balance_after),
    )
