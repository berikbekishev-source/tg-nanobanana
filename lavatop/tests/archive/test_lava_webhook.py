#!/usr/bin/env python3
"""
Скрипт для тестирования webhook интеграции с Lava.top
Имитирует webhook от Lava.top без реальной оплаты
"""

import requests
import sys
from datetime import datetime

# URL вашего webhook endpoint
WEBHOOK_URL = "https://web-production-96df.up.railway.app/api/miniapp/lava-webhook"

# API ключ из Railway переменных
WEBHOOK_SECRET = "lava_webhook_secret_ABC123xyz789"

def test_webhook(order_id, status="success", amount=5.00):
    """
    Тестирует webhook с указанными параметрами

    Args:
        order_id: ID транзакции (должен существовать в базе)
        status: Статус платежа (success, failed, pending)
        amount: Сумма платежа
    """

    # Данные, имитирующие webhook от Lava.top
    webhook_data = {
        "order_id": order_id,  # ID транзакции из нашей базы
        "payment_id": f"lava_test_{datetime.now().timestamp()}",
        "amount": amount,
        "currency": "USD",
        "status": status,  # success, paid, completed - для успешного платежа
        "email": "test@example.com",
        "timestamp": datetime.now().isoformat(),
        "test_mode": True
    }

    # Заголовки с API ключом
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {WEBHOOK_SECRET}",
        "X-API-Key": WEBHOOK_SECRET
    }

    print(f"Отправка тестового webhook...")
    print(f"Order ID: {order_id}")
    print(f"Status: {status}")
    print(f"Amount: ${amount}")
    print("-" * 50)

    try:
        # Отправка запроса
        response = requests.post(
            WEBHOOK_URL,
            json=webhook_data,
            headers=headers,
            timeout=10
        )

        print(f"HTTP Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print("\n✅ Webhook успешно обработан!")
            print("Проверьте баланс пользователя и транзакцию в базе данных.")
        else:
            print(f"\n❌ Ошибка обработки webhook: {response.status_code}")

    except Exception as e:
        print(f"\n❌ Ошибка отправки webhook: {e}")

def create_test_payment():
    """
    Создает тестовый платеж через API для получения order_id
    """

    payment_url = "https://web-production-96df.up.railway.app/api/miniapp/create-payment"

    payment_data = {
        "email": "test@example.com",
        "credits": 100,
        "amount": 5,
        "currency": "USD",
        "payment_method": "card"
    }

    print("Создание тестового платежа...")

    try:
        response = requests.post(
            payment_url,
            json=payment_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                payment_id = data.get("payment_id")
                print(f"✅ Тестовый платеж создан. Order ID: {payment_id}")
                return payment_id
            else:
                print(f"❌ Ошибка создания платежа: {data.get('error')}")
        else:
            print(f"❌ HTTP ошибка: {response.status_code}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")

    return None

if __name__ == "__main__":
    print("=" * 50)
    print("ТЕСТИРОВАНИЕ WEBHOOK ИНТЕГРАЦИИ С LAVA.TOP")
    print("=" * 50)

    if len(sys.argv) > 1:
        # Использовать указанный order_id
        order_id = sys.argv[1]
        print(f"Использование существующего order_id: {order_id}")
    else:
        # Создать тестовый платеж
        order_id = create_test_payment()
        if not order_id:
            print("\nНе удалось создать тестовый платеж")
            sys.exit(1)

    print("\n" + "=" * 50)
    print("ИМИТАЦИЯ WEBHOOK ОТ LAVA.TOP")
    print("=" * 50)

    # Тестирование успешного платежа
    test_webhook(order_id, status="success", amount=5.00)

    print("\n" + "=" * 50)
    print("\n⚠️  ВАЖНО:")
    print("1. Этот webhook работает только для тестовых транзакций")
    print("2. Для реальных платежей webhook должен приходить от Lava.top")
    print("3. Проверьте логи Railway для деталей обработки")
    print(f"4. Order ID для проверки: {order_id}")
