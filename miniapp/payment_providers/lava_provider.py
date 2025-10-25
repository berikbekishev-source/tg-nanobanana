"""
Интеграция с Lava.top для приема платежей
"""
import hashlib
import hmac
import logging
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)


# Платежные ссылки для каждого количества токенов
LAVA_PAYMENT_LINKS = {
    100: "https://app.lava.top/products/acfa45f0-6fa0-4f3c-b73e-f10b92d6d8fc",
    # TODO: Добавьте ссылки для других пакетов:
    # 200: "https://app.lava.top/products/...",
    # 500: "https://app.lava.top/products/...",
    # 1000: "https://app.lava.top/products/...",
}


def get_payment_url(credits: int, transaction_id: int, user_email: str = None) -> str:
    """
    Получить ссылку на оплату для указанного количества токенов

    Args:
        credits: Количество токенов (100, 200, 500, 1000)
        transaction_id: ID транзакции для отслеживания
        user_email: Email пользователя (опционально)

    Returns:
        URL для оплаты
    """
    base_url = LAVA_PAYMENT_LINKS.get(credits)

    if not base_url:
        logger.error(f"No Lava payment link for {credits} credits")
        return None

    # Добавляем параметры для отслеживания
    # Lava.top обычно поддерживает custom параметры
    payment_url = f"{base_url}?order_id={transaction_id}"

    if user_email:
        payment_url += f"&email={user_email}"

    return payment_url


def verify_webhook_signature(payload: dict, signature: str) -> bool:
    """
    Проверка подписи webhook от Lava.top

    Args:
        payload: Данные от webhook
        signature: Подпись из заголовка

    Returns:
        True если подпись валидна
    """
    # TODO: Реализовать проверку подписи согласно документации Lava.top
    # Обычно это HMAC SHA256

    try:
        secret = settings.LAVA_WEBHOOK_SECRET

        # Создаем строку для подписи (зависит от документации Lava)
        # Пример: order_id + amount + status
        data_string = f"{payload.get('order_id')}{payload.get('amount')}{payload.get('status')}"

        # Вычисляем HMAC
        expected_signature = hmac.new(
            secret.encode(),
            data_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)

    except Exception as e:
        logger.error(f"Error verifying Lava webhook signature: {e}")
        return False


def parse_webhook_data(payload: dict) -> dict:
    """
    Парсинг данных от webhook Lava.top

    Args:
        payload: Данные от webhook

    Returns:
        Словарь с распарсенными данными
    """
    return {
        'order_id': payload.get('order_id') or payload.get('custom_id'),
        'amount': Decimal(str(payload.get('amount', 0))),
        'status': payload.get('status'),
        'payment_id': payload.get('id') or payload.get('payment_id'),
        'currency': payload.get('currency', 'USD'),
        'email': payload.get('email'),
        'raw_data': payload
    }
