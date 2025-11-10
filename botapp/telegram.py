from django.conf import settings
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message
import redis.asyncio as aioredis

from botapp.chat_logger import ChatLogger


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


_bot = LoggingBot(token=settings.TELEGRAM_BOT_TOKEN)
_storage = RedisStorage(redis=aioredis.from_url(settings.CELERY_BROKER_URL))  # тот же Redis
dp = Dispatcher(storage=_storage)

bot = _bot  # re-export

def setup_telegram():
    """
    Инициализация Telegram-бота при старте Django (asgi.py).
    """
    from .handlers import main_router

    # Проверка, чтобы не подключать повторно
    if main_router not in dp.sub_routers:
        dp.include_router(main_router)
        print("✅ Telegram bot initialized with FSM handlers")
    else:
        print("⚠️ Router already attached, skipping setup_telegram()")
