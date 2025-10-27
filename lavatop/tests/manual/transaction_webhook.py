#!/usr/bin/env python3
"""
Полный цикл тестирования вебхука Lava.top с реальной записью в БД.

Скрипт:
  1. Создаёт тестовую транзакцию (deposit) для fallback‑пользователя.
  2. Отправляет webhook на Railway.
  3. Проверяет, что транзакция закрыта и токены начислены.
"""

from __future__ import annotations

import base64
import os
import sys
import time
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import django
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings

from botapp.models import TgUser, Transaction, UserBalance

WEBHOOK_SECRET = os.environ.get("LAVA_WEBHOOK_SECRET", "lava_webhook_secret_ABC123xyz789")
API_KEY = os.environ.get("LAVA_API_KEY", "HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb")
WEBHOOK_URL = os.environ.get(
    "LAVATOP_RAILWAY_WEBHOOK_URL",
    "https://web-production-96df.up.railway.app/api/miniapp/lava-webhook",
)


def get_fallback_user() -> TgUser:
    """Возвращает пользователя, которому будут начисляться токены."""
    fallback_chat = int(getattr(settings, "LAVA_FALLBACK_CHAT_ID", "283738604"))
    user = TgUser.objects.filter(chat_id=fallback_chat).first()
    if user is None:
        user = TgUser.objects.create(
            chat_id=fallback_chat,
            first_name="Test",
            last_name="User",
            username="testuser",
            language="ru",
        )
        print(f"✅ Создан тестовый пользователь {user.chat_id}")
    return user


def create_test_transaction() -> Tuple[int, int]:
    """Создаёт запись Transaction и возвращает (transaction_id, chat_id)."""
    user = get_fallback_user()
    balance, _ = UserBalance.objects.get_or_create(user=user)
    print(f"Баланс перед тестом: {balance.balance} токенов")

    transaction = Transaction.objects.create(
        user=user,
        type="deposit",
        amount=Decimal("5.00"),
        balance_after=balance.balance,
        description="Тестовый платеж 100 токенов через Lava.top",
        payment_method="card",
        is_pending=True,
        is_completed=False,
    )
    print(f"✅ Создана транзакция ID {transaction.id} (pending)")
    return transaction.id, user.chat_id


def send_webhook(transaction_id: int, status: str = "success") -> bool:
    """Отправляет webhook на Railway."""
    payload = {
        "order_id": str(transaction_id),
        "payment_id": f"lava_payment_{datetime.now().timestamp()}",
        "amount": 5.00,
        "currency": "USD",
        "status": status,
        "email": "test@example.com",
        "timestamp": datetime.now().isoformat(),
    }
    headers = {
        "Authorization": f"Basic {base64.b64encode(f':{WEBHOOK_SECRET}'.encode()).decode()}",
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }
    print(f"\nОтправка webhook для транзакции {transaction_id} ({status})…")
    response = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=15)
    print(f"HTTP {response.status_code}: {response.text}")
    return response.status_code == 200


def check_transaction(transaction_id: int) -> None:
    """Печатает итоговый статус транзакции и баланса."""
    transaction = Transaction.objects.get(id=transaction_id)
    balance = UserBalance.objects.get(user=transaction.user)
    print("\nРЕЗУЛЬТАТ:")
    print(f"  • Статус транзакции: {'completed' if transaction.is_completed else 'pending'}")
    print(f"  • Баланс в записи: {transaction.balance_after}")
    print(f"  • Текущий баланс пользователя: {balance.balance}")


def main() -> None:
    transaction_id, chat_id = create_test_transaction()
    if not send_webhook(transaction_id):
        print("❌ Webhook вернул ошибку, дальнейшая проверка пропущена.")
        return
    time.sleep(1)
    check_transaction(transaction_id)
    print(f"\nПодробности смотрите в Railway логах (chat_id={chat_id}).")


if __name__ == "__main__":
    main()
