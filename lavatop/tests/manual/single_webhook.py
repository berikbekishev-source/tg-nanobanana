#!/usr/bin/env python3
"""
Отправка тестового вебхука на боевой Railway endpoint (ручной smoke‑тест).
Скрипт полезен, когда нужно быстро убедиться, что обработчик Lava.top жив.
"""

from __future__ import annotations

import base64
import os
import time
from datetime import datetime
from typing import Optional

import requests

BASE_URL = os.environ.get(
    "LAVATOP_RAILWAY_BASE_URL",
    "https://web-production-96df.up.railway.app",
)
WEBHOOK_URL = f"{BASE_URL}/api/miniapp/lava-webhook"

WEBHOOK_SECRET = os.environ.get("LAVA_WEBHOOK_SECRET", "lava_webhook_secret_ABC123xyz789")
API_KEY = os.environ.get("LAVA_API_KEY", "HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb")

AUTH_HEADER = base64.b64encode(f":{WEBHOOK_SECRET}".encode("utf-8")).decode("utf-8")


def build_payload(order_id: str) -> dict:
    """Возвращает тестовый payload в «старом» формате (наш парсер поддерживает оба)."""
    now = datetime.now()
    return {
        "id": f"pay_test_{int(time.time())}",
        "order_id": order_id,
        "amount": 5.00,
        "currency": "USD",
        "status": "success",
        "payment_id": f"pay_test_{int(time.time())}",
        "email": "test@example.com",
        "type": "payment",
        "event": "payment.success",
        "test_mode": True,
        "payment_method": "card",
        "custom_fields": {
            "user_id": os.environ.get("LAVA_FALLBACK_CHAT_ID", "283738604"),
            "credits": 100,
            "description": "Test payment for 100 tokens",
        },
        "created_at": now.isoformat(),
    }


def send_test_webhook(order_id: str = "90") -> Optional[requests.Response]:
    """Отправляет тестовый webhook на Railway."""
    payload = build_payload(order_id)
    headers = {
        "Content-Type": "application/json",
        "X-Test-Mode": "true",
        "User-Agent": "Lava.top/Webhook/ManualSmoke/1.0",
        "Authorization": f"Basic {AUTH_HEADER}",
        "X-API-Key": API_KEY,
    }

    print("🚀 Отправка тестового вебхука на Railway...")
    print(f"URL: {WEBHOOK_URL}")
    print(f"Order ID: {payload['order_id']}")
    print("-" * 50)

    try:
        response = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=30)
        print(f"📬 Статус ответа: {response.status_code}")

        if response.status_code == 200:
            print("✅ Webhook успешно доставлен!")
            print(f"Ответ сервера: {response.text}")
        else:
            print(f"⚠️ Ответ {response.status_code}: {response.text}")

        return response

    except requests.exceptions.Timeout:
        print("❌ Таймаут запроса (сервер не отвечает)")
    except requests.exceptions.ConnectionError:
        print("❌ Ошибка соединения — Railway недоступен?")
    except Exception as exc:
        print(f"❌ Неожиданная ошибка: {exc}")

    return None


def print_log_hints() -> None:
    """Подсказки, что посмотреть в Railway после отправки."""
    print("\n" + "=" * 50)
    print("📊 ПРОВЕРКА РЕЗУЛЬТАТА")
    print("=" * 50)
    print("1. railway logs --service web | grep 'Lava webhook'")
    print("2. railway logs --service worker | grep 'Payment' ")
    print("3. Убедитесь, что токены начислены и отправлено уведомление")


if __name__ == "__main__":
    print("=" * 50)
    print("ТЕСТ WEBHOOK LAVA.TOP → RAILWAY")
    print("=" * 50)
    resp = send_test_webhook()
    if resp is not None:
        print_log_hints()
    print("\n✨ Тест завершен!")
