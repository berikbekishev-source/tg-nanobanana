from django.conf import settings
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
import redis.asyncio as aioredis

_bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
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
