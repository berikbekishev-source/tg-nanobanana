"""
Интеграция с Lava.top для приема платежей
Полная интеграция через API
"""
import hashlib
import hmac
import json
import logging
import requests
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict
from django.conf import settings

logger = logging.getLogger(__name__)


class LavaAPI:
    """
    Класс для работы с API Lava.top
    """

    BASE_URL = "https://api.lava.top"

    def __init__(self):
        self.api_key = getattr(settings, 'LAVA_API_KEY', None)
        self.webhook_secret = getattr(settings, 'LAVA_WEBHOOK_SECRET', None)

        if not self.api_key:
            logger.warning("LAVA_API_KEY not configured")

        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key
        }

    def create_invoice(self, amount: Decimal, order_id: str,
                      expire_at: Optional[int] = None,
                      custom_fields: Optional[Dict] = None) -> Optional[Dict]:
        """
        Создает счет на оплату через Lava API

        Args:
            amount: Сумма в USD
            order_id: ID заказа в нашей системе
            expire_at: Время жизни счета в минутах (по умолчанию 1440 = 24 часа)
            custom_fields: Дополнительные поля

        Returns:
            Dict с данными счета или None при ошибке
        """

        if not self.api_key:
            logger.error("Cannot create invoice: LAVA_API_KEY not configured")
            return None

        # NOTE: The Lava API endpoint is currently not working.
        # Using static payment links instead (see LAVA_PAYMENT_LINKS below)
        logger.warning("Lava API invoice creation is currently disabled, using static links")
        return None

    def get_invoice_status(self, invoice_id: str) -> Optional[str]:
        """
        Проверяет статус счета

        Args:
            invoice_id: ID счета в Lava

        Returns:
            Статус счета или None при ошибке
        """

        if not self.api_key:
            return None

        url = f"{self.BASE_URL}/invoice/info"

        data = {"id": invoice_id}

        try:
            response = requests.post(
                url,
                json=data,
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()

                if result.get("status") == "success":
                    invoice_data = result.get("data", {})
                    return invoice_data.get("status")

            return None

        except Exception as e:
            logger.error(f"Error checking invoice status: {e}")
            return None

    def verify_webhook_signature(self, data: str, signature: str) -> bool:
        """
        Проверяет подпись webhook от Lava

        Args:
            data: Тело запроса в виде строки
            signature: Подпись из заголовка X-Signature

        Returns:
            True если подпись валидна
        """

        if not self.webhook_secret:
            logger.warning("LAVA_WEBHOOK_SECRET not configured, skipping signature verification")
            return True

        # Вычисляем подпись
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)


# Платежные ссылки для каждого количества токенов
# ВАЖНО: Создайте продукты в Lava.top для каждого пакета и обновите эти ссылки!
LAVA_PAYMENT_LINKS = {
    100: "https://app.lava.top/products/acfa45f0-6fa0-4f3c-b73e-f10b92d6d8fc/072b7520-f963-4650-8bbf-16e7efdbdd21",
    200: "https://app.lava.top/products/PLACEHOLDER_200_TOKENS",  # $10 - замените на реальную ссылку
    500: "https://app.lava.top/products/PLACEHOLDER_500_TOKENS",  # $25 - замените на реальную ссылку
    1000: "https://app.lava.top/products/PLACEHOLDER_1000_TOKENS", # $50 - замените на реальную ссылку
}


def get_payment_url(credits: int, transaction_id, user_email: str = None,
                   use_api: bool = False) -> str:
    """
    Получить ссылку на оплату для указанного количества токенов

    Args:
        credits: Количество токенов (100, 200, 500, 1000)
        transaction_id: ID транзакции для отслеживания
        user_email: Email пользователя (опционально)
        use_api: Использовать API для создания счета (по умолчанию False, так как API не работает)

    Returns:
        URL для оплаты
    """

    # Используем статические ссылки (API временно недоступен)
    base_url = LAVA_PAYMENT_LINKS.get(credits)

    if not base_url:
        logger.error(f"No Lava payment link for {credits} credits")
        return None

    # Добавляем параметры для отслеживания
    payment_url = f"{base_url}?order_id={transaction_id}"

    if user_email:
        payment_url += f"&email={user_email}"

    logger.info(f"Using static payment link for {credits} credits")
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
