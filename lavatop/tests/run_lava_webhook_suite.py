#!/usr/bin/env python3
"""
Comprehensive webhook test suite for the Lava.top integration.

Скрипт последовательно отправляет на боевой Railway endpoint все примерные payload'ы
из официальной документации Lava.top. Перед каждым «успешным» сценарием создаётся
реальная транзакция через endpoint /api/miniapp/create-payment, чтобы webhook
мог корректно привязаться к записи в базе и начислить токены.

Перед запуском убедитесь, что:
  * существует пользователь Telegram с chat_id, указанным в CHAT_ID (по умолчанию 283738604);
  * переменные окружения LAVA_WEBHOOK_SECRET и LAVA_API_KEY соответствуют Railway.
"""

import base64
import json
import sys
import time
from datetime import datetime, timezone, timedelta

import requests

BASE_URL = "https://web-production-96df.up.railway.app"
WEBHOOK_URL = f"{BASE_URL}/api/miniapp/lava-webhook"
CREATE_PAYMENT_URL = f"{BASE_URL}/api/miniapp/create-payment"

API_KEY = "HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb"
WEBHOOK_SECRET = "lava_webhook_secret_ABC123xyz789"
CHAT_ID = 283738604
EMAIL = "test@lava.top"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Basic {base64.b64encode(f':{WEBHOOK_SECRET}'.encode()).decode()}",
    "X-API-Key": API_KEY,
    "User-Agent": "Lava.top/TestSuite/1.0",
}


def log(title: str):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def create_transaction(credits: int = 100, amount: float = 5.0) -> str:
    """Создаёт pending транзакцию через наш API и возвращает её ID."""
    payload = {
        "email": EMAIL,
        "credits": credits,
        "amount": amount,
        "currency": "USD",
        "payment_method": "card",
        "user_id": CHAT_ID,
    }
    response = requests.post(CREATE_PAYMENT_URL, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"Failed to create payment: {data}")
    return str(data["payment_id"])


def send_webhook(payload: dict, description: str):
    """Отправляет webhook и печатает результат."""
    log(f"Sending webhook: {description}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    response = requests.post(WEBHOOK_URL, headers=HEADERS, json=payload, timeout=15)
    print(f"HTTP {response.status_code}: {response.text}")
    time.sleep(1)
    return response


def main():
    try:
        # Успешная покупка (не подписка)
        contract_id_success = create_transaction()
        send_webhook(
            {
                "eventType": "payment.success",
                "product": {
                    "id": "d31384b8-e412-4be5-a2ec-297ae6666c8f",
                    "title": "Тестовый продукт",
                },
                "buyer": {"email": EMAIL},
                "contractId": contract_id_success,
                "amount": 5.00,
                "currency": "USD",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "completed",
                "errorMessage": "",
            },
            "successful_purchase_webhook_payload",
        )

        # Неуспешная покупка
        contract_id_failed = create_transaction()
        send_webhook(
            {
                "eventType": "payment.failed",
                "product": {
                    "id": "d31384b8-e412-4be5-a2ec-297ae6666c8f",
                    "title": "Тестовый продукт",
                },
                "buyer": {"email": "emwbwj@lava.top"},
                "contractId": contract_id_failed,
                "amount": 5.00,
                "currency": "USD",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "errorMessage": "Payment window is opened but not completed",
            },
            "failed_purchase_webhook_payload",
        )

        # Успешная подписка (первый платёж)
        contract_id_subscription = create_transaction()
        send_webhook(
            {
                "eventType": "payment.success",
                "product": {
                    "id": "72d53efb-3696-469f-b856-f0d815748dd6",
                    "title": "Тестовая подписка",
                },
                "buyer": {"email": "emwbwj@lava.top"},
                "contractId": contract_id_subscription,
                "amount": 20.00,
                "currency": "USD",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "subscription-active",
                "errorMessage": "",
            },
            "successful_subscription_webhook_payload",
        )

        # Ошибка при оформлении подписки (первый платёж)
        contract_id_subscription_fail = create_transaction()
        send_webhook(
            {
                "eventType": "payment.failed",
                "product": {
                    "id": "836b9fc5-7ae9-4a27-9642-592bc44072b7",
                    "title": "Тестовая подписка",
                },
                "contractId": contract_id_subscription_fail,
                "buyer": {"email": "zkvgsd@lava.top"},
                "amount": 15.00,
                "currency": "USD",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "subscription-failed",
                "errorMessage": "Not sufficient funds",
            },
            "failed_subscription_webhook_payload",
        )

        # Успешное продление подписки (используем новый contractId)
        recurring_contract = f"recurring-success-{int(time.time())}"
        send_webhook(
            {
                "eventType": "subscription.recurring.payment.success",
                "product": {
                    "id": "72d53efb-3696-469f-b856-f0d815748dd6",
                    "title": "Тестовая подписка",
                },
                "buyer": {"email": "emwbwj@lava.top"},
                "contractId": recurring_contract,
                "parentContractId": contract_id_subscription,
                "amount": 20.00,
                "currency": "USD",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "subscription-active",
                "errorMessage": "",
            },
            "successful_subscription_recurring_webhook_payload",
        )

        # Ошибка при продлении подписки
        recurring_fail_contract = create_transaction()
        send_webhook(
            {
                "eventType": "subscription.recurring.payment.failed",
                "product": {
                    "id": "72d53efb-3696-469f-b856-f0d815748dd6",
                    "title": "Тестовая подписка",
                },
                "buyer": {"email": "emwbwj@lava.top"},
                "contractId": recurring_fail_contract,
                "parentContractId": contract_id_subscription,
                "amount": 20.00,
                "currency": "USD",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "subscription-failed",
                "errorMessage": "Payment window is opened but not completed",
            },
            "failed_subscription_recurring_webhook_payload",
        )

        # Отмена подписки
        send_webhook(
            {
                "eventType": "subscription.cancelled",
                "contractId": contract_id_subscription,
                "product": {
                    "id": "72d53efb-3696-469f-b856-f0d815748dd6",
                    "title": "Тестовая подписка",
                },
                "buyer": {"email": "emwbwj@lava.top"},
                "cancelledAt": datetime.now(timezone.utc).isoformat(),
                "willExpireAt": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
            "subscription_cancelled_webhook_payload",
        )

        print("\n✅ Webhook suite completed.")

    except Exception as exc:
        print(f"\n❌ Test suite aborted: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
