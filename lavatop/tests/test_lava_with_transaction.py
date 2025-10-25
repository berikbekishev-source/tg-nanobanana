#!/usr/bin/env python3
"""
Тестирование webhook с реальной транзакцией в базе данных
"""

import os
import sys
import django
import requests
import json
from decimal import Decimal
from datetime import datetime

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/Users/berik/Desktop/tg-nanobanana')
django.setup()

from botapp.models import TgUser, UserBalance, Transaction

def create_test_transaction():
    """
    Создает тестовую транзакцию в базе данных
    """
    print("Создание тестовой транзакции...")

    # Попробуем найти существующего пользователя или создать тестового
    try:
        # Ищем первого пользователя в базе
        user = TgUser.objects.first()

        if not user:
            # Создаем тестового пользователя
            user = TgUser.objects.create(
                chat_id=123456789,  # Тестовый ID
                first_name="Test",
                last_name="User",
                username="testuser",
                language="ru"
            )
            print(f"✅ Создан тестовый пользователь: {user.username}")
        else:
            print(f"✅ Используем существующего пользователя: {user.username or user.first_name}")

        # Создаем или получаем баланс
        user_balance, _ = UserBalance.objects.get_or_create(user=user)
        print(f"   Текущий баланс: {user_balance.balance} токенов")

        # Создаем транзакцию
        transaction = Transaction.objects.create(
            user=user,
            type='deposit',
            amount=Decimal('5.00'),  # $5 за 100 токенов
            balance_after=user_balance.balance,  # Баланс до начисления
            description="Тестовый платеж 100 токенов через Lava.top",
            payment_method='card',
            is_pending=True,  # Ожидает подтверждения
            is_completed=False
        )

        print(f"✅ Создана транзакция ID: {transaction.id}")
        print(f"   Сумма: ${transaction.amount}")
        print(f"   Статус: pending")

        return transaction.id, user.chat_id

    except Exception as e:
        print(f"❌ Ошибка создания транзакции: {e}")
        return None, None

def send_webhook(transaction_id, status="success"):
    """
    Отправляет webhook имитирующий успешный платеж от Lava.top
    """
    webhook_url = "https://web-production-96df.up.railway.app/api/miniapp/lava-webhook"
    webhook_secret = "lava_webhook_secret_ABC123xyz789"

    webhook_data = {
        "order_id": str(transaction_id),  # ID реальной транзакции
        "payment_id": f"lava_payment_{datetime.now().timestamp()}",
        "amount": 5.00,
        "currency": "USD",
        "status": status,  # success для успешного платежа
        "email": "test@example.com",
        "timestamp": datetime.now().isoformat(),
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {webhook_secret}",
        "X-API-Key": webhook_secret
    }

    print(f"\n{'=' * 50}")
    print("ОТПРАВКА WEBHOOK")
    print('=' * 50)
    print(f"Transaction ID: {transaction_id}")
    print(f"Status: {status}")

    try:
        response = requests.post(
            webhook_url,
            json=webhook_data,
            headers=headers,
            timeout=10
        )

        print(f"HTTP Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print("\n✅ Webhook успешно обработан!")
            return True
        else:
            print(f"\n❌ Ошибка webhook: {response.status_code}")
            return False

    except Exception as e:
        print(f"\n❌ Ошибка отправки: {e}")
        return False

def check_transaction_status(transaction_id):
    """
    Проверяет статус транзакции после webhook
    """
    try:
        transaction = Transaction.objects.get(id=transaction_id)
        user_balance = UserBalance.objects.get(user=transaction.user)

        print(f"\n{'=' * 50}")
        print("РЕЗУЛЬТАТ ТЕСТА")
        print('=' * 50)
        print(f"Транзакция ID: {transaction.id}")
        print(f"Статус: {'✅ Завершена' if transaction.is_completed else '⏳ Ожидает'}")
        print(f"Баланс после: {transaction.balance_after} токенов")
        print(f"Текущий баланс пользователя: {user_balance.balance} токенов")

        if transaction.is_completed:
            print("\n🎉 ТЕСТ УСПЕШЕН! Webhook правильно обработал платеж.")
            print(f"   Токены зачислены: {transaction.amount * 20} токенов")  # $5 = 100 токенов
        else:
            print("\n⚠️  Транзакция не была подтверждена. Проверьте логи.")

    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("ПОЛНЫЙ ТЕСТ WEBHOOK С РЕАЛЬНОЙ ТРАНЗАКЦИЕЙ")
    print("=" * 50)

    # 1. Создаем транзакцию
    transaction_id, user_id = create_test_transaction()

    if not transaction_id:
        print("\nТест не может быть выполнен без транзакции")
        sys.exit(1)

    # 2. Отправляем webhook
    success = send_webhook(transaction_id)

    # 3. Проверяем результат
    if success:
        import time
        time.sleep(1)  # Даем время на обработку
        check_transaction_status(transaction_id)

    print("\n" + "=" * 50)
    print("\n📝 ПРИМЕЧАНИЯ:")
    print("1. Это тестовый webhook для проверки интеграции")
    print("2. В продакшене webhook будет приходить от Lava.top")
    print("3. Проверьте Railway логи для подробностей")
    print(f"4. ID транзакции для проверки: {transaction_id}")
    print(f"5. ID пользователя: {user_id}")