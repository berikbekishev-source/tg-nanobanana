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
            await bot.set_webhook(url=url, secret_token=secret, allowed_updates=["message"])
        asyncio.run(_run())
        self.stdout.write(self.style.SUCCESS(f"Webhook set to {url}"))

