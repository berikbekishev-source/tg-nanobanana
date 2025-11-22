#!/usr/bin/env python
"""Скрипт для ручной установки webhook с правильными параметрами"""

import asyncio
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from botapp.telegram import bot

async def set_webhook():
    """Установка webhook с всеми необходимыми параметрами"""
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    url = f"{base}/api/telegram/webhook"
    secret = settings.TG_WEBHOOK_SECRET

    # Включаем ВСЕ типы обновлений
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

    print(f"Устанавливаю webhook на: {url}")
    print(f"Secret token: {'***' + secret[-5:] if secret else 'None'}")
    print(f"Allowed updates: {allowed_updates}")

    try:
        # Сначала удаляем старый webhook
        await bot.delete_webhook()
        print("Старый webhook удален")

        # Устанавливаем новый
        result = await bot.set_webhook(
            url=url,
            secret_token=secret,
            allowed_updates=allowed_updates
        )
        print(f"Результат установки: {result}")

        # Проверяем информацию о webhook
        webhook_info = await bot.get_webhook_info()
        print(f"\nИнформация о webhook:")
        print(f"- URL: {webhook_info.url}")
        print(f"- Allowed updates: {webhook_info.allowed_updates}")
        print(f"- Pending count: {webhook_info.pending_update_count}")
        print(f"- Last error: {webhook_info.last_error_message}")

        return True

    except Exception as e:
        print(f"Ошибка: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(set_webhook())
    sys.exit(0 if success else 1)