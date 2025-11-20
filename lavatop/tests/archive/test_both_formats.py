#!/usr/bin/env python3
"""
Тестирование обоих форматов вебхуков: старого и официального
"""

import requests
import time
from datetime import datetime, timezone

WEBHOOK_URL = 'https://web-production-96df.up.railway.app/api/miniapp/lava-webhook'
WEBHOOK_SECRET = 'lava_webhook_secret_ABC123xyz789'


def send_webhook(payload, description):
    """Отправка вебхука на Railway"""

    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': WEBHOOK_SECRET,
        'User-Agent': 'Lava.top/Webhook/1.0'
    }

    print(f"\n{'='*60}")
    print(f"📤 {description}")
    print(f"{'='*60}")

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers=headers,
            timeout=30
        )

        print(f"Response: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ SUCCESS: {response.text}")
        else:
            print(f"❌ ERROR: {response.text}")

        return response

    except Exception as e:
        print(f"❌ Failed: {e}")
        return None


# Тест 1: Старый формат (работал ранее)
print("\n" + "🚀"*20)
print("TEST 1: OLD FORMAT (with numeric transaction ID)")
print("🚀"*20)

old_format_payload = {
    "id": f"pay_test_{int(time.time())}",
    "order_id": "91",  # Числовой ID существующей транзакции
    "amount": 5.00,
    "currency": "USD",
    "status": "success",
    "payment_id": f"pay_test_{int(time.time())}",
    "email": "test@example.com",
    "created_at": datetime.now(timezone.utc).isoformat()
}

send_webhook(old_format_payload, "OLD FORMAT - Numeric Transaction ID")
time.sleep(2)


# Тест 2: Официальный формат Lava.top с UUID
print("\n" + "🚀"*20)
print("TEST 2: OFFICIAL LAVA.TOP FORMAT (with UUID contractId)")
print("🚀"*20)

official_format_payload = {
    "eventType": "payment.success",
    "product": {
        "id": "d31384b8-e412-4be5-a2ec-297ae6666c8f",
        "title": "100 Токенов"
    },
    "buyer": {
        "email": "test@example.com"
    },
    "contractId": "7ea82675-4ded-4133-95a7-a6efbaf165cc",  # UUID от Lava.top
    "amount": 5.00,
    "currency": "USD",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "completed",
    "errorMessage": ""
}

send_webhook(official_format_payload, "OFFICIAL FORMAT - UUID contractId")
time.sleep(2)


# Тест 3: Официальный формат с числовым contractId (для теста)
print("\n" + "🚀"*20)
print("TEST 3: OFFICIAL FORMAT with numeric contractId")
print("🚀"*20)

official_with_numeric = {
    "eventType": "payment.success",
    "product": {
        "id": "test-product-id",
        "title": "Test Product"
    },
    "buyer": {
        "email": "test@example.com"
    },
    "contractId": "91",  # Числовой ID для теста
    "amount": 5.00,
    "currency": "USD",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "completed",
    "errorMessage": ""
}

send_webhook(official_with_numeric, "OFFICIAL FORMAT - Numeric contractId")


print("\n" + "="*60)
print("✅ ALL TESTS COMPLETED")
print("="*60)

print("\n📊 EXPECTED RESULTS:")
print("  Test 1: Should work (old format with numeric ID)")
print("  Test 2: Should create new transaction (UUID from Lava.top)")
print("  Test 3: Should find existing transaction (numeric contractId)")

print("\n🔍 CHECK LOGS:")
print("  railway logs --service web | tail -50")
