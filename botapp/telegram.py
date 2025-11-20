import logging

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
