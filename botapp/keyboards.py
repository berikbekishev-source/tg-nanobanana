"""
Клавиатуры для навигации по боту согласно ТЗ
"""
from typing import List
from decimal import Decimal
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from botapp.models import AIModel


# === ГЛАВНОЕ МЕНЮ ===

def get_main_menu_keyboard(payment_url: str) -> ReplyKeyboardMarkup:
    """
    Главное меню бота (4 кнопки согласно ТЗ)
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
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


def get_back_to_menu_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка возврата в главное меню (должна быть везде)"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )
    return keyboard


# === ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ ===

def get_image_models_keyboard(models: List[AIModel]) -> InlineKeyboardMarkup:
    """Шаг 1: Выбор модели для изображений"""
    builder = InlineKeyboardBuilder()

    for model in models:
        if model.type == 'image' and model.is_active:
            # Показываем только название модели
            builder.button(
                text=model.display_name,
                callback_data=f"img_model:{model.slug}"
            )

    builder.adjust(1)

    # Добавляем кнопку возврата в главное меню
    builder.row(InlineKeyboardButton(
        text="🏠 Главное меню",
        callback_data="main_menu"
    ))

    return builder.as_markup()


# === ГЕНЕРАЦИЯ ВИДЕО ===

def get_video_models_keyboard(models: List[AIModel]) -> InlineKeyboardMarkup:
    """Шаг 1: Выбор модели для видео"""
    builder = InlineKeyboardBuilder()

    for model in models:
        if model.type == 'video' and model.is_active:
            # Показываем только название модели
            builder.button(
                text=model.display_name,
                callback_data=f"vid_model:{model.slug}"
            )

    builder.adjust(1)

    # Добавляем кнопку возврата в главное меню
    builder.row(InlineKeyboardButton(
        text="🏠 Главное меню",
        callback_data="main_menu"
    ))

    return builder.as_markup()


def get_video_format_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора формата видео."""
    builder = InlineKeyboardBuilder()
    builder.button(text="9:16 (Vertical)", callback_data="video_format:9:16")
    builder.button(text="16:9 (Horizontal)", callback_data="video_format:16:9")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    return builder.as_markup()


# === БАЛАНС ===

def get_balance_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для раздела баланса
    Показывается после нажатия "Мой баланс (цены)"
    Выводится вместе с сообщением о текущем балансе пользователя
    """
    builder = InlineKeyboardBuilder()

    # Кнопка пополнить баланс в сообщении о балансе
    builder.button(text="💳 Пополнить баланс", callback_data="deposit")

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


def get_main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline кнопка для возврата в главное меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    return builder.as_markup()


def format_balance(balance: Decimal) -> str:
    """Форматирование баланса для отображения"""
    return f"⚡ {balance:.2f} токенов"


def get_model_info_message(model: AIModel) -> str:
    """
    Формирует сообщение с информацией о модели (Шаг 2)
    Теперь берет данные из модели в БД вместо if-else
    """
    # Базовая информация из модели
    message = (
        f"{model.display_name}\n"
        f"Стоимость: ⚡{model.price} токенов\n\n"
        f"{model.description}\n\n"
    )

    # Формируем инструкцию в зависимости от возможностей модели
    if model.type == 'image':
        if model.supports_image_input and model.max_input_images > 0:
            message += f"Отправьте текстовой запрос или загрузите до {model.max_input_images} изображений "
            message += "чтобы использовать режим Remix 👇"
        else:
            message += "Отправьте текстовой запрос 👇"
    elif model.type == 'video':
        if model.supports_image_input:
            message += "Отправьте ✍️ текстовое задание на удобном языке или "
            message += "🌄 загрузите изображение чтобы генерация началась 👇"
        else:
            message += "Отправьте ✍️ текстовое задание на удобном языке 👇"

    return message


def get_prices_info() -> str:
    """Информация о ценах для раздела баланса"""
    return (
        "💰 **Текущие цены:**\n\n"
        "**Изображения:**\n"
        "🍌 Nano Banana - ⚡1.5 токена\n"
        "🎨 Imagen 3.0 - ⚡3 токена (скоро)\n\n"
        "**Видео:**\n"
        "⚡ Veo 3.1 Fast - ⚡19 токенов\n"
        "🎬 Veo 3.1 Pro - ⚡49 токенов (скоро)\n\n"
        "💎 Чем больше пополнение - тем выгоднее!\n"
        "🎁 Используйте промокод WELCOME2025 для бонуса"
    )


def get_generation_start_message() -> str:
    """Системное сообщение перед началом генерации"""
    return "Приступаю к генерации, ожидайте"


def get_generation_complete_message(prompt: str, generation_type: str, model_name: str, **kwargs) -> str:
    """
    Системное сообщение после завершения генерации

    Args:
        prompt: Промт пользователя
        generation_type: Тип генерации (text2image, image2image, text2video, image2video)
        model_name: Название модели
        **kwargs: Дополнительные параметры (duration, resolution, aspect_ratio и т.д.)
    """
    tool_names = {
        'text2image': 'text2image',
        'image2image': 'image2image',
        'text2video': 'text2video',
        'image2video': 'image2video'
    }

    segments = [f"Ваш запрос: {prompt}"]
    segments.append(f"Инструмент: {tool_names.get(generation_type, generation_type)}")

    if 'video' in generation_type:
        duration = kwargs.get('duration')
        if duration:
            segments.append(f"Продолжительность: {duration} сек.")
        aspect_ratio = kwargs.get('aspect_ratio')
        if aspect_ratio:
            segments.append(f"Соотношение сторон: {aspect_ratio}")
        resolution = kwargs.get('resolution')
        if resolution:
            segments.append(f"Разрешение: {resolution}")
    else:
        quantity = kwargs.get('quantity')
        if quantity and quantity > 1:
            segments.append(f"Количество: {quantity}")
        aspect_ratio = kwargs.get('aspect_ratio')
        if aspect_ratio:
            segments.append(f"Соотношение сторон: {aspect_ratio}")

    hashtag = kwargs.get('model_hashtag')
    if not hashtag:
        safe = ''.join(ch for ch in model_name if ch.isalnum())
        hashtag = f"#{safe.lower()}" if safe else "#model"
    segments.append(f"Модель: {hashtag}")

    charged_amount = kwargs.get('charged_amount')
    if charged_amount is not None:
        segments.append(f"Списано: ⚡{charged_amount:.2f}")

    balance_after = kwargs.get('balance_after')
    if balance_after is not None:
        segments.append(f"Баланс: ⚡{balance_after:.2f}")

    formatted_segments = []
    for seg in segments:
        seg = seg.strip()
        if seg and seg[-1] not in '.!?':
            seg += '.'
        formatted_segments.append(seg)

    return ' '.join(formatted_segments)
