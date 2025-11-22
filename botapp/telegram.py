import logging
import asyncio
import os

from django.conf import settings
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message
import redis.asyncio as aioredis

from botapp.chat_logger import ChatLogger
from botapp.aiogram_errors import aiogram_error_handler


class LoggingBot(Bot):
    """Бот, автоматически логирующий исходящие сообщения."""

    async def send_message(self, *args, **kwargs) -> Message:
        response = await super().send_message(*args, **kwargs)
        await ChatLogger.log_outgoing(response)
        return response

    async def send_photo(self, *args, **kwargs) -> Message:
        response = await super().send_photo(*args, **kwargs)
        await ChatLogger.log_outgoing(response)
        return response

    async def send_video(self, *args, **kwargs) -> Message:
        response = await super().send_video(*args, **kwargs)
        await ChatLogger.log_outgoing(response)
        return response

    async def send_document(self, *args, **kwargs) -> Message:
        response = await super().send_document(*args, **kwargs)
        await ChatLogger.log_outgoing(response)
        return response

    async def send_audio(self, *args, **kwargs) -> Message:
        response = await super().send_audio(*args, **kwargs)
        await ChatLogger.log_outgoing(response)
        return response

    async def send_voice(self, *args, **kwargs) -> Message:
        response = await super().send_voice(*args, **kwargs)
        await ChatLogger.log_outgoing(response)
        return response

    async def send_animation(self, *args, **kwargs) -> Message:
        response = await super().send_animation(*args, **kwargs)
        await ChatLogger.log_outgoing(response)
        return response


_original_message_answer = Message.answer


async def _answer_with_logging(self: Message, *args, **kwargs) -> Message:
    response = await _original_message_answer(self, *args, **kwargs)
    try:
        await ChatLogger.log_outgoing(response)
    except Exception:
        pass
    return response


Message.answer = _answer_with_logging


_bot = LoggingBot(token=settings.TELEGRAM_BOT_TOKEN)
_storage = RedisStorage(redis=aioredis.from_url(settings.CELERY_BROKER_URL))  # тот же Redis
dp = Dispatcher(storage=_storage)
dp.errors.register(aiogram_error_handler)

bot = _bot  # re-export
logger = logging.getLogger(__name__)


def setup_webhook_on_start() -> None:
    """Автоматическая установка вебхука при старте веб-сервиса."""
    flag = os.getenv("AUTO_SET_WEBHOOK_ON_START", "true").lower()
    if flag not in {"1", "true", "yes"}:
        logger.info("Пропускаем установку вебхука: AUTO_SET_WEBHOOK_ON_START=%s", flag)
        return

    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    secret = settings.TG_WEBHOOK_SECRET

    if not base or not secret:
        logger.warning("Пропускаем установку вебхука: нет PUBLIC_BASE_URL или TG_WEBHOOK_SECRET")
        return

    url = f"{base}/api/telegram/webhook"
    allowed_updates = [
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "inline_query",
        "chosen_inline_result",
        "callback_query",
        "shipping_query",
        "pre_checkout_query",
        "poll",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    ]

    async def _run():
        await bot.set_webhook(url=url, secret_token=secret, allowed_updates=allowed_updates)

    try:
        asyncio.run(_run())
        logger.info("Вебхук установлен при старте: %s", url)
    except Exception:
        logger.exception("Не удалось установить вебхук при старте")


def setup_telegram():
    """
    Инициализация Telegram-бота при старте Django (asgi.py).
    """
    from .handlers import main_router

    # Проверка, чтобы не подключать повторно
    if main_router not in dp.sub_routers:
        dp.include_router(main_router)
        logger.info("Telegram bot initialized with FSM handlers")
    else:
        logger.info("Router already attached, skipping setup_telegram()")
