"""
Интеграция с Lava.top для приема платежей
Использует официальную SDK с fallback на статические ссылки
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

# Пытаемся импортировать SDK
try:
    from lava_top_sdk import LavaClient, LavaClientConfig, PaymentCreateRequest
    SDK_AVAILABLE = True
    logger.info("Lava SDK loaded successfully")
except ImportError:
    SDK_AVAILABLE = False
    logger.warning("Lava SDK not installed. Using fallback methods.")


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


class LavaSDK:
    """
    Класс для работы с официальной SDK Lava.top
    """

    def __init__(self):
        self.client = None
        self.product_id = None  # ID продукта для 100 токенов

        if not SDK_AVAILABLE:
            logger.warning("SDK not available, LavaSDK class will not be functional")
            return

        api_key = getattr(settings, 'LAVA_API_KEY', None)
        webhook_secret = getattr(settings, 'LAVA_WEBHOOK_SECRET', None)

        if not api_key:
            logger.warning("LAVA_API_KEY not configured for SDK")
            return

        try:
            # Создаем конфигурацию
            config = LavaClientConfig(
                api_key=api_key,
                webhook_secret_key=webhook_secret,
                env='production',
                timeout=30,
                max_retries=3
            )

            # Инициализируем клиент
            self.client = LavaClient(config=config)
            logger.info("Lava SDK client initialized successfully")

            # Получаем ID продукта для 100 токенов
            self.load_product_id()

        except Exception as e:
            logger.error(f"Failed to initialize Lava SDK: {e}")
            self.client = None

    def load_product_id(self):
        """
        Загружает ID продукта для 100 токенов из Lava
        """
        try:
            # Пытаемся получить список продуктов
            products = self.client.get_products()

            if products:
                # Ищем продукт с ценой $5 (100 токенов)
                for product in products:
                    if hasattr(product, 'price'):
                        price = float(product.price) if product.price else 0
                        if abs(price - 5.00) < 0.01:  # $5 для 100 токенов
                            self.product_id = getattr(product, 'id', None)
                            logger.info(f"Found product for 100 tokens: {self.product_id}")
                            break

                if not self.product_id:
                    logger.warning("Product for 100 tokens ($5) not found in Lava")
            else:
                logger.warning("No products found in Lava account")

        except Exception as e:
            logger.error(f"Error loading products from Lava: {e}")
            # Используем ID из статической ссылки как fallback
            # Извлекаем из URL: .../products/{product_id}/{offer_id}
            static_url = LAVA_PAYMENT_LINKS.get(100, "")
            if "products/" in static_url:
                parts = static_url.split("products/")[1].split("/")
                if len(parts) >= 1:
                    self.product_id = parts[0]
                    logger.info(f"Using product ID from static URL: {self.product_id}")

    def create_payment(self, amount: Decimal, order_id: str,
                      email: str = None, description: str = None,
                      custom_fields: Dict = None) -> Optional[Dict]:
        """
        Создает платеж через SDK

        Returns:
            Dict с URL платежа или None
        """
        if not self.client:
            logger.error("SDK client not initialized")
            return None

        try:
            # Подготавливаем запрос
            payment_request = PaymentCreateRequest(
                amount=float(amount),
                order_id=str(order_id),
                email=email or "customer@example.com",  # Email обязателен в SDK
                offer_id=self.product_id,  # ID продукта
                currency="USD",
                description=description or f"Покупка токенов",
                success_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/payment/success",
                fail_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/payment/fail",
                hook_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/api/miniapp/lava-webhook",
                custom_fields=custom_fields or {}
            )

            logger.info(f"Creating payment via SDK: order_id={order_id}, amount=${amount}")

            # Создаем платеж
            response = self.client.create_one_time_payment(payment_request)

            if response:
                payment_url = getattr(response, 'url', None)
                payment_id = getattr(response, 'id', None)

                if payment_url:
                    logger.info(f"Payment created via SDK: {payment_id}, URL: {payment_url}")
                    return {
                        'url': payment_url,
                        'id': payment_id,
                        'success': True
                    }
                else:
                    logger.error("SDK response missing payment URL")

        except Exception as e:
            logger.error(f"Error creating payment via SDK: {e}")

        return None

    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """
        Проверяет подпись webhook через SDK
        """
        if not self.client:
            return False

        try:
            return self.client.verify_webhook_signature(payload, signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature via SDK: {e}")
            return False


# Глобальный экземпляр SDK (singleton)
_sdk_instance = None


def get_sdk_instance():
    """Получает или создает экземпляр SDK"""
    global _sdk_instance
    if _sdk_instance is None and SDK_AVAILABLE:
        _sdk_instance = LavaSDK()
    return _sdk_instance


# Платежные ссылки для каждого количества токенов
# ВАЖНО: Создайте продукты в Lava.top для каждого пакета и обновите эти ссылки!
LAVA_PAYMENT_LINKS = {
    100: "https://app.lava.top/products/acfa45f0-6fa0-4f3c-b73e-f10b92d6d8fc/072b7520-f963-4650-8bbf-16e7efdbdd21",
    # Остальные ссылки будут добавлены позже
    # 200: "...",  # $10
    # 500: "...",  # $25
    # 1000: "...", # $50
}


def get_payment_url(credits: int, transaction_id, user_email: str = None,
                   use_sdk: bool = True) -> str:
    """
    Получить ссылку на оплату для указанного количества токенов

    Args:
        credits: Количество токенов (100, 200, 500, 1000)
        transaction_id: ID транзакции для отслеживания
        user_email: Email пользователя
        use_sdk: Использовать SDK для создания счета (по умолчанию True)

    Returns:
        URL для оплаты или None при ошибке
    """

    # Проверяем поддерживаемые пакеты токенов
    if credits not in [100]:  # Пока поддерживаем только 100 токенов
        logger.error(f"Unsupported token package: {credits}. Currently only 100 tokens supported.")
        return None

    # Рассчитываем сумму ($0.05 за токен)
    amount = Decimal(credits * 0.05)

    # Пробуем создать платеж через SDK
    if use_sdk and SDK_AVAILABLE:
        sdk_instance = get_sdk_instance()

        if sdk_instance and sdk_instance.client:
            logger.info(f"Attempting to create payment via SDK for {credits} tokens")

            # Создаем платеж через SDK
            payment_result = sdk_instance.create_payment(
                amount=amount,
                order_id=transaction_id,
                email=user_email,
                description=f"Покупка {credits} токенов",
                custom_fields={
                    'credits': credits,
                    'email': user_email or '',
                    'transaction_id': str(transaction_id)
                }
            )

            if payment_result and payment_result.get('url'):
                logger.info(f"Payment URL created via SDK: {payment_result['id']}")
                return payment_result['url']
            else:
                logger.warning("SDK payment creation failed, falling back to static links")

    # Fallback на статические ссылки
    logger.info(f"Using static payment link for {credits} tokens")
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
        payload: Данные от webhook (dict или строка)
        signature: Подпись из заголовка

    Returns:
        True если подпись валидна
    """

    # Сначала пытаемся проверить через SDK
    if SDK_AVAILABLE:
        sdk_instance = get_sdk_instance()
        if sdk_instance and sdk_instance.client:
            try:
                # Преобразуем payload в строку если нужно
                payload_str = json.dumps(payload) if isinstance(payload, dict) else str(payload)

                result = sdk_instance.verify_webhook_signature(payload_str, signature)
                logger.info(f"Webhook signature verification via SDK: {result}")
                return result
            except Exception as e:
                logger.warning(f"SDK webhook verification failed: {e}, falling back to manual")

    # Fallback на ручную проверку
    try:
        secret = settings.LAVA_WEBHOOK_SECRET

        if not secret:
            logger.warning("LAVA_WEBHOOK_SECRET not configured, skipping signature verification")
            return True  # Пропускаем проверку если секрет не настроен

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
