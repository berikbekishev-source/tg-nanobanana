#!/usr/bin/env python3
"""
Отправка тестового вебхука на Railway endpoint
Симулирует webhook от Lava.top
"""

import requests
import json
import hashlib
import hmac
import time
from datetime import datetime

def send_test_webhook():
    """Отправляет тестовый webhook на Railway"""

    # URL вашего webhook endpoint на Railway
    WEBHOOK_URL = 'https://web-production-96df.up.railway.app/api/miniapp/lava-webhook'

    # Тестовые данные, имитирующие webhook от Lava.top
    # Структура должна соответствовать ожиданиям parse_webhook_data
    webhook_payload = {
        "id": f"pay_test_{int(time.time())}",
        "order_id": "90",  # ID существующей тестовой транзакции в БД
        "amount": 5.00,
        "currency": "USD",
        "status": "success",  # success для успешного платежа
        "payment_id": f"pay_test_{int(time.time())}",
        "email": "test@example.com",
        "type": "payment",
        "event": "payment.success",
        "test_mode": True,
        "payment_method": "card",
        "custom_fields": {
            "user_id": "123456789",
            "credits": 100,
            "description": "Test payment for 100 tokens"
        },
        "created_at": datetime.now().isoformat()
    }

    # Заголовки, как от Lava.top
    headers = {
        'Content-Type': 'application/json',
        'X-Lava-Signature': 'test_signature_12345',
        'X-Webhook-Id': f"webhook_{int(time.time())}",
        'X-Test-Mode': 'true',
        'X-API-Key': 'lava_webhook_secret_ABC123xyz789',  # Секретный ключ из Railway
        'User-Agent': 'Lava.top/Webhook/1.0'
    }

    print("🚀 Отправка тестового вебхука на Railway...")
    print(f"URL: {WEBHOOK_URL}")
    print(f"Order ID: {webhook_payload['order_id']}")
    print("-" * 50)

    try:
        # Отправляем POST запрос
        response = requests.post(
            WEBHOOK_URL,
            json=webhook_payload,
            headers=headers,
            timeout=30
        )

        print(f"📬 Статус ответа: {response.status_code}")

        if response.status_code == 200:
            print("✅ Webhook успешно доставлен!")
            print(f"Ответ сервера: {response.text}")

            print("\n📋 Что должно произойти:")
            print("1. Webhook обработчик получил данные")
            print("2. Проверил подпись (в тестовом режиме пропускается)")
            print("3. Нашел/создал транзакцию")
            print("4. Начислил 100 токенов")
            print("5. Отправил уведомление в Telegram")

        elif response.status_code == 404:
            print("❌ Endpoint не найден (404)")
            print("Проверьте URL: /api/miniapp/lava-webhook")

        elif response.status_code == 401:
            print("⚠️ Ошибка авторизации (401)")
            print("Webhook получен, но подпись не прошла проверку")

        elif response.status_code == 500:
            print("❌ Внутренняя ошибка сервера (500)")
            print(f"Детали: {response.text}")

        else:
            print(f"⚠️ Неожиданный ответ: {response.status_code}")
            print(f"Тело ответа: {response.text}")

        return response

    except requests.exceptions.Timeout:
        print("❌ Таймаут запроса (сервер не отвечает)")

    except requests.exceptions.ConnectionError:
        print("❌ Ошибка соединения")
        print("Проверьте, что Railway приложение запущено")

    except Exception as e:
        print(f"❌ Ошибка: {e}")

    return None


def check_railway_logs():
    """Инструкция по проверке логов"""

    print("\n" + "="*50)
    print("📊 ПРОВЕРКА РЕЗУЛЬТАТА")
    print("="*50)
    print("\n1. Проверьте логи Railway:")
    print("   railway logs --service web | grep 'webhook'")
    print("\n2. Или откройте Railway Dashboard:")
    print("   railway open")
    print("\n3. Ищите в логах:")
    print("   - 'Lava webhook received'")
    print("   - 'Payment xxx completed'")
    print("   - 'Credited xxx tokens'")


if __name__ == "__main__":
    print("="*50)
    print("ТЕСТ WEBHOOK LAVA.TOP → RAILWAY")
    print("="*50)

    # Отправляем тестовый webhook
    response = send_test_webhook()

    # Показываем инструкции по проверке
    if response:
        check_railway_logs()

    print("\n✨ Тест завершен!")