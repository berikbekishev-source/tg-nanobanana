"""
Интеграция с Lava.top через официальную SDK
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, List
from django.conf import settings

try:
    from lava_top_sdk import LavaClient, LavaClientConfig, PaymentCreateRequest
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


class LavaSDKProvider:
    """
    Провайдер для работы с Lava.top через официальную SDK
    """

    def __init__(self):
        self.client = None
        self.products = {}

        if not SDK_AVAILABLE:
            logger.error("Lava SDK not installed. Run: pip install lava-top-sdk")
            return

        api_key = getattr(settings, 'LAVA_API_KEY', None)
        webhook_secret = getattr(settings, 'LAVA_WEBHOOK_SECRET', None)

        if not api_key:
            logger.warning("LAVA_API_KEY not configured")
            return

        try:
            # Создаем конфигурацию
            config = LavaClientConfig(
                api_key=api_key,
                webhook_secret_key=webhook_secret,
                env='production'
            )

            # Инициализируем клиент
            self.client = LavaClient(config=config)
            logger.info("Lava SDK client initialized successfully")

            # Загружаем список продуктов
            self.load_products()

        except Exception as e:
            logger.error(f"Failed to initialize Lava SDK client: {e}")

    def load_products(self):
        """
        Загружает список продуктов из Lava.top
        """
        if not self.client:
            return

        try:
            products = self.client.get_products()
            if products:
                for product in products:
                    # Сохраняем продукты по цене для быстрого доступа
                    if hasattr(product, 'price') and hasattr(product, 'id'):
                        price = float(product.price)
                        self.products[price] = product.id
                        logger.info(f"Loaded product: ${price} -> {product.id}")

                logger.info(f"Loaded {len(self.products)} products from Lava")
            else:
                logger.warning("No products found in Lava")

        except Exception as e:
            logger.error(f"Failed to load products: {e}")

    def create_payment(self, amount: Decimal, order_id: str,
                      email: str, description: str = None,
                      custom_fields: Dict = None) -> Optional[Dict]:
        """
        Создает платеж через SDK

        Args:
            amount: Сумма платежа
            order_id: ID заказа
            email: Email покупателя
            description: Описание платежа
            custom_fields: Дополнительные поля

        Returns:
            Словарь с данными платежа или None при ошибке
        """
        if not self.client:
            logger.error("Lava SDK client not initialized")
            return None

        try:
            # Ищем подходящий продукт по цене
            price_float = float(amount)
            offer_id = self.products.get(price_float)

            if not offer_id:
                # Пытаемся найти ближайший продукт
                logger.warning(f"No product found for price ${price_float}")
                # Можно попробовать создать без offer_id (если SDK позволяет)
                offer_id = None

            # Создаем запрос на платеж
            payment_request = PaymentCreateRequest(
                amount=price_float,
                order_id=str(order_id),
                email=email,
                offer_id=offer_id,  # ID продукта из Lava
                currency="USD",
                description=description or f"Пополнение баланса на ${price_float}",
                success_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/payment/success",
                fail_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/payment/fail",
                hook_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/api/miniapp/lava-webhook",
                custom_fields=custom_fields or {}
            )

            # Создаем платеж
            response = self.client.create_one_time_payment(payment_request)

            if response:
                result = {
                    'id': getattr(response, 'id', None),
                    'url': getattr(response, 'url', None),
                    'status': getattr(response, 'status', None),
                    'amount': price_float,
                    'order_id': order_id
                }

                logger.info(f"Payment created via SDK: {result['id']}")
                return result
            else:
                logger.error("Failed to create payment via SDK")
                return None

        except Exception as e:
            logger.error(f"Error creating payment via SDK: {e}")
            return None

    def verify_webhook(self, payload: str, signature: str) -> bool:
        """
        Проверяет подпись webhook

        Args:
            payload: Тело запроса
            signature: Подпись из заголовка

        Returns:
            True если подпись валидна
        """
        if not self.client:
            return False

        try:
            return self.client.verify_webhook_signature(payload, signature)
        except Exception as e:
            logger.error(f"Error verifying webhook: {e}")
            return False

    def parse_webhook(self, payload: Dict) -> Dict:
        """
        Парсит данные webhook

        Args:
            payload: Данные webhook

        Returns:
            Распарсенные данные
        """
        if not self.client:
            return payload

        try:
            parsed = self.client.parse_webhook(payload)
            return {
                'order_id': getattr(parsed, 'order_id', None),
                'status': getattr(parsed, 'status', None),
                'amount': getattr(parsed, 'amount', None),
                'payment_id': getattr(parsed, 'id', None),
                'raw_data': payload
            }
        except Exception as e:
            logger.error(f"Error parsing webhook: {e}")
            return payload


# Глобальный экземпляр провайдера
_provider_instance = None


def get_lava_sdk_provider() -> Optional[LavaSDKProvider]:
    """
    Получает экземпляр SDK провайдера (singleton)
    """
    global _provider_instance

    if _provider_instance is None:
        _provider_instance = LavaSDKProvider()

    return _provider_instance if _provider_instance.client else None


def create_payment_via_sdk(credits: int, transaction_id: str,
                          user_email: str) -> Optional[str]:
    """
    Создает платеж через SDK

    Args:
        credits: Количество токенов
        transaction_id: ID транзакции
        user_email: Email пользователя

    Returns:
        URL для оплаты или None
    """
    provider = get_lava_sdk_provider()

    if not provider:
        logger.error("Lava SDK provider not available")
        return None

    # Рассчитываем сумму
    amount = Decimal(credits * 0.05)  # $0.05 за токен

    # Создаем платеж
    payment = provider.create_payment(
        amount=amount,
        order_id=transaction_id,
        email=user_email,
        description=f"Покупка {credits} токенов",
        custom_fields={
            'credits': credits,
            'transaction_id': str(transaction_id)
        }
    )

    if payment and payment.get('url'):
        return payment['url']

    return None