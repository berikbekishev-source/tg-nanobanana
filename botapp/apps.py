import logging
import os
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class BotappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "botapp"

    def ready(self):
        from . import signals  # noqa: F401
        try:
            from .telegram import dp  # noqa
            from .handlers import main_router  # noqa
            dp.include_router(main_router)

            # Устанавливаем webhook при запуске приложения только в production
            from django.conf import settings
            if os.environ.get('RAILWAY_ENVIRONMENT') and settings.PUBLIC_BASE_URL:
                self._setup_webhook()

        except ImportError:
            # aiogram not installed yet
            pass

    def _setup_webhook(self):
        """Установка webhook при запуске приложения"""
        try:
            from django.conf import settings
            from .telegram import bot
            import asyncio

            logger.info("[STARTUP] Инициализация webhook при запуске приложения...")

            async def setup_webhook():
                base = settings.PUBLIC_BASE_URL.rstrip("/")
                url = f"{base}/api/telegram/webhook"
                secret = settings.TG_WEBHOOK_SECRET

                # Включаем все типы обновлений
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
                    "chat_join_request"
                ]

                await bot.set_webhook(
                    url=url,
                    secret_token=secret,
                    allowed_updates=allowed_updates
                )
                logger.info(f"[STARTUP] Webhook успешно установлен на {url}")

            # Создаем новый event loop для установки webhook
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(setup_webhook())
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"[STARTUP] Ошибка установки webhook: {e}")
