"""
Утилиты для отправки сообщений в Telegram без aiogram dispatcher.
Используется в Celery задачах где aiogram dispatcher недоступен.
"""
import logging
from typing import Any, Dict, List, Optional, Union

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# Таймаут для HTTP запросов к Telegram API
TELEGRAM_API_TIMEOUT = 30.0


def _get_bot_token() -> str:
    """Получить токен бота из настроек."""
    return settings.TELEGRAM_BOT_TOKEN


def _build_api_url(method: str) -> str:
    """Построить URL для метода Telegram Bot API."""
    return f"https://api.telegram.org/bot{_get_bot_token()}/{method}"


def _make_request(method: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполнить синхронный HTTP запрос к Telegram Bot API.
    Возвращает ответ API или выбрасывает исключение.
    """
    url = _build_api_url(method)
    try:
        with httpx.Client(timeout=TELEGRAM_API_TIMEOUT) as client:
            response = client.post(url, json=data)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                logger.error(
                    "Telegram API вернул ошибку: %s",
                    result.get("description", "Unknown error")
                )
            return result
    except httpx.TimeoutException as exc:
        logger.error("Таймаут при запросе к Telegram API: %s", exc)
        raise
    except httpx.HTTPStatusError as exc:
        logger.error("HTTP ошибка при запросе к Telegram API: %s", exc)
        raise
    except Exception as exc:
        logger.exception("Неожиданная ошибка при запросе к Telegram API: %s", exc)
        raise


def send_message(
    chat_id: int,
    text: str,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
    disable_web_page_preview: bool = True,
) -> Dict[str, Any]:
    """
    Отправить текстовое сообщение в Telegram.

    Args:
        chat_id: ID чата (пользователя)
        text: Текст сообщения
        parse_mode: Режим парсинга (HTML, Markdown, MarkdownV2)
        reply_markup: Клавиатура в формате dict (InlineKeyboardMarkup)
        disable_web_page_preview: Отключить превью ссылок

    Returns:
        Ответ Telegram API
    """
    data: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = reply_markup
    if disable_web_page_preview:
        data["disable_web_page_preview"] = True

    return _make_request("sendMessage", data)


def send_video(
    chat_id: int,
    video: str,
    caption: Optional[str] = None,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Отправить видео в Telegram по URL.

    Args:
        chat_id: ID чата
        video: URL видео
        caption: Подпись к видео
        parse_mode: Режим парсинга
        reply_markup: Клавиатура

    Returns:
        Ответ Telegram API
    """
    data: Dict[str, Any] = {
        "chat_id": chat_id,
        "video": video,
    }
    if caption:
        data["caption"] = caption
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = reply_markup

    return _make_request("sendVideo", data)


def send_photo(
    chat_id: int,
    photo: str,
    caption: Optional[str] = None,
    parse_mode: Optional[str] = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Отправить фото в Telegram по URL.

    Args:
        chat_id: ID чата
        photo: URL фото
        caption: Подпись к фото
        parse_mode: Режим парсинга
        reply_markup: Клавиатура

    Returns:
        Ответ Telegram API
    """
    data: Dict[str, Any] = {
        "chat_id": chat_id,
        "photo": photo,
    }
    if caption:
        data["caption"] = caption
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = reply_markup

    return _make_request("sendPhoto", data)


def build_inline_keyboard(
    buttons: List[List[Dict[str, str]]]
) -> Dict[str, Any]:
    """
    Построить InlineKeyboardMarkup из списка кнопок.

    Args:
        buttons: Двумерный список кнопок. Каждая кнопка — dict с ключами:
            - text: текст кнопки
            - callback_data: данные для callback (опционально)
            - url: URL для открытия (опционально)

    Example:
        build_inline_keyboard([
            [{"text": "Кнопка 1", "callback_data": "btn1"}],
            [{"text": "Ссылка", "url": "https://example.com"}]
        ])

    Returns:
        Dict для reply_markup
    """
    return {
        "inline_keyboard": buttons
    }


def get_main_menu_keyboard_dict() -> Dict[str, Any]:
    """
    Возвращает inline-клавиатуру главного меню в формате dict.
    Используется в Celery задачах.
    """
    return build_inline_keyboard([
        [{"text": "🏠 Главное меню", "callback_data": "main_menu"}]
    ])


def get_cancel_keyboard_dict() -> Dict[str, Any]:
    """
    Возвращает inline-клавиатуру с кнопкой отмены в формате dict.
    """
    return build_inline_keyboard([
        [{"text": "❌ Отмена", "callback_data": "cancel"}]
    ])
