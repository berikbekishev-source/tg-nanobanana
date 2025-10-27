#!/usr/bin/env python3
"""
Тестирование вебхуков с официальным форматом Lava.top
Основано на официальной спецификации API
"""

import requests
import json
import time
from datetime import datetime, timezone

# URL вашего webhook endpoint
WEBHOOK_URL = 'https://web-production-96df.up.railway.app/api/miniapp/lava-webhook'

# Секретный ключ для авторизации
WEBHOOK_SECRET = 'lava_webhook_secret_ABC123xyz789'


def send_webhook(payload, description="Test webhook"):
    """Отправка вебхука на Railway endpoint"""

    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': WEBHOOK_SECRET,
        'User-Agent': 'Lava.top/Webhook/1.0'
    }

    print(f"\n{'='*60}")
    print(f"📤 {description}")
    print(f"{'='*60}")
    print(f"Event Type: {payload.get('eventType', 'N/A')}")
    print(f"Status: {payload.get('status', 'N/A')}")

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers=headers,
            timeout=30
        )

        print(f"Response Code: {response.status_code}")

        if response.status_code == 200:
            print(f"✅ SUCCESS: {response.text}")
        else:
            print(f"❌ ERROR: {response.text}")

        return response

    except Exception as e:
        print(f"❌ Failed: {e}")
        return None


def test_successful_payment():
    """Тест успешной оплаты продукта"""

    payload = {
        "eventType": "payment.success",
        "product": {
            "id": "d31384b8-e412-4be5-a2ec-297ae6666c8f",
            "title": "100 Токенов"
        },
        "buyer": {
            "email": "test@example.com"
        },
        "contractId": "91",  # ID существующей транзакции в БД
        "amount": 5.00,
        "currency": "USD",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "errorMessage": ""
    }

    return send_webhook(payload, "SUCCESSFUL PAYMENT (100 Tokens)")


def test_failed_payment():
    """Тест неудачной оплаты"""

    payload = {
        "eventType": "payment.failed",
        "product": {
            "id": "d31384b8-e412-4be5-a2ec-297ae6666c8f",
            "title": "100 Токенов"
        },
        "buyer": {
            "email": "test@example.com"
        },
        "contractId": "91",  # Новая транзакция
        "amount": 5.00,
        "currency": "USD",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "errorMessage": "Payment window is opened but not completed"
    }

    return send_webhook(payload, "FAILED PAYMENT")


def test_subscription_active():
    """Тест успешной оплаты подписки (первый платеж)"""

    payload = {
        "eventType": "payment.success",
        "product": {
            "id": "72d53efb-3696-469f-b856-f0d815748dd6",
            "title": "Премиум подписка (месяц)"
        },
        "buyer": {
            "email": "subscriber@example.com"
        },
        "contractId": "92",
        "amount": 25.00,
        "currency": "USD",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "subscription-active",
        "errorMessage": ""
    }

    return send_webhook(payload, "SUBSCRIPTION ACTIVATED")


def test_subscription_recurring_success():
    """Тест успешного продления подписки"""

    payload = {
        "eventType": "subscription.recurring.payment.success",
        "product": {
            "id": "72d53efb-3696-469f-b856-f0d815748dd6",
            "title": "Премиум подписка (месяц)"
        },
        "buyer": {
            "email": "subscriber@example.com"
        },
        "contractId": "93",
        "parentContractId": "92",  # Ссылка на оригинальную подписку
        "amount": 25.00,
        "currency": "USD",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "subscription-active",
        "errorMessage": ""
    }

    return send_webhook(payload, "SUBSCRIPTION RENEWED")


def test_subscription_failed():
    """Тест неудачного продления подписки"""

    payload = {
        "eventType": "subscription.recurring.payment.failed",
        "product": {
            "id": "72d53efb-3696-469f-b856-f0d815748dd6",
            "title": "Премиум подписка (месяц)"
        },
        "buyer": {
            "email": "subscriber@example.com"
        },
        "contractId": "94",
        "parentContractId": "92",
        "amount": 25.00,
        "currency": "USD",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "subscription-failed",
        "errorMessage": "Not sufficient funds"
    }

    return send_webhook(payload, "SUBSCRIPTION RENEWAL FAILED")


def test_subscription_cancelled():
    """Тест отмены подписки"""

    payload = {
        "eventType": "subscription.cancelled",
        "contractId": "92",
        "product": {
            "id": "72d53efb-3696-469f-b856-f0d815748dd6",
            "title": "Премиум подписка (месяц)"
        },
        "buyer": {
            "email": "subscriber@example.com"
        },
        "cancelledAt": datetime.now(timezone.utc).isoformat(),
        "willExpireAt": datetime.now(timezone.utc).isoformat()
    }

    return send_webhook(payload, "SUBSCRIPTION CANCELLED")


def test_with_russian_currency():
    """Тест платежа в рублях"""

    payload = {
        "eventType": "payment.success",
        "product": {
            "id": "d31384b8-e412-4be5-a2ec-297ae6666c8f",
            "title": "100 Токенов"
        },
        "buyer": {
            "email": "russian@example.com"
        },
        "contractId": "95",
        "amount": 450.00,
        "currency": "RUB",  # Рубли
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "errorMessage": ""
    }

    return send_webhook(payload, "PAYMENT IN RUB")


def run_all_tests():
    """Запуск всех тестов"""

    print("\n" + "🚀"*30)
    print("LAVA.TOP WEBHOOK TESTING")
    print("Official Format According to API Specification")
    print("🚀"*30)

    print("\nWebhook URL:", WEBHOOK_URL)
    print("Testing all event types...")

    # Тест 1: Успешная оплата
    test_successful_payment()
    time.sleep(1)

    # Тест 2: Неудачная оплата
    test_failed_payment()
    time.sleep(1)

    # Тест 3: Активация подписки
    test_subscription_active()
    time.sleep(1)

    # Тест 4: Продление подписки
    test_subscription_recurring_success()
    time.sleep(1)

    # Тест 5: Неудачное продление
    test_subscription_failed()
    time.sleep(1)

    # Тест 6: Отмена подписки
    test_subscription_cancelled()
    time.sleep(1)

    # Тест 7: Платеж в рублях
    test_with_russian_currency()

    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED")
    print("="*60)

    print("\n📊 EXPECTED BEHAVIOR:")
    print("  ✓ payment.success → Credits added to user balance")
    print("  ✓ payment.failed → Transaction marked as failed")
    print("  ✓ subscription.* → Subscription status updated")
    print("  ✓ All events → Logged in Railway logs")

    print("\n🔍 CHECK LOGS:")
    print("  railway logs --service web | grep 'webhook'")


def test_specific_event(event_type):
    """Тест конкретного типа события"""

    if event_type == "success":
        test_successful_payment()
    elif event_type == "failed":
        test_failed_payment()
    elif event_type == "subscription":
        test_subscription_active()
    elif event_type == "recurring":
        test_subscription_recurring_success()
    elif event_type == "cancelled":
        test_subscription_cancelled()
    else:
        print(f"Unknown event type: {event_type}")
        print("Available: success, failed, subscription, recurring, cancelled")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Тест конкретного события
        test_specific_event(sys.argv[1])
    else:
        # Запуск всех тестов
        run_all_tests()