from django.core.management.base import BaseCommand
from django.conf import settings
import asyncio
from botapp.telegram import bot

class Command(BaseCommand):
    help = "Set Telegram webhook to /api/telegram/webhook"

    def handle(self, *args, **opts):
        base = settings.PUBLIC_BASE_URL.rstrip("/")
        url = f"{base}/api/telegram/webhook"
        secret = settings.TG_WEBHOOK_SECRET
        async def _run():
            # Включаем все типы обновлений, необходимые для работы бота
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
            await bot.set_webhook(url=url, secret_token=secret, allowed_updates=allowed_updates)
        asyncio.run(_run())
        self.stdout.write(self.style.SUCCESS(f"Webhook set to {url}"))

