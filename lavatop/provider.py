"""
Lava.top Payment Provider with SDK Integration
Handles payment creation with automatic fallback to static links
"""

import logging
import json
from decimal import Decimal
from typing import Optional, Dict
from django.conf import settings

logger = logging.getLogger(__name__)

# Try to import SDK
try:
    from lava_top_sdk import LavaClient, LavaClientConfig, PaymentCreateRequest
    SDK_AVAILABLE = True
    logger.info("Lava SDK loaded successfully")
except ImportError:
    SDK_AVAILABLE = False
    logger.warning("Lava SDK not installed. Using fallback methods.")


class LavaProvider:
    """
    Main provider for Lava.top payments
    Supports both SDK and static link approaches
    """

    # Static payment links (fallback)
    PAYMENT_LINKS = {
        100: "https://app.lava.top/products/b85a5e3c-d89d-46a9-b6fe-e9f9b9ec4696/45043cfb-f0d3-4b14-8286-3985fee8b4e1?currency=USD",
        # Add more packages as they become available:
        # 200: "...",  # $10
        # 500: "...",  # $25
        # 1000: "...", # $50
    }

    # Supported token packages
    SUPPORTED_PACKAGES = [100]  # Add more as they become available

    def __init__(self):
        self.client = None
        self.product_id = None
        self._init_sdk()

    def _init_sdk(self):
        """Initialize SDK client if available"""
        if not SDK_AVAILABLE:
            return

        api_key = getattr(settings, 'LAVA_API_KEY', None)
        webhook_secret = getattr(settings, 'LAVA_WEBHOOK_SECRET', None)

        if not api_key:
            logger.warning("LAVA_API_KEY not configured")
            return

        try:
            config = LavaClientConfig(
                api_key=api_key,
                webhook_secret_key=webhook_secret,
                env='production',
                timeout=30,
                max_retries=3
            )

            self.client = LavaClient(config=config)
            logger.info("Lava SDK client initialized")
            self._load_product_id()

        except Exception as e:
            logger.error(f"Failed to initialize SDK: {e}")

    def _load_product_id(self):
        """Load product ID from Lava.top"""
        if not self.client:
            return

        try:
            products = self.client.get_products()

            if products:
                # Find product for 100 tokens ($5)
                for product in products:
                    if hasattr(product, 'price'):
                        price = float(product.price) if product.price else 0
                        if abs(price - 5.00) < 0.01:
                            self.product_id = getattr(product, 'id', None)
                            logger.info(f"Found product ID: {self.product_id}")
                            break

                if not self.product_id:
                    logger.warning("Product for 100 tokens not found in Lava")
            else:
                logger.warning("No products found in Lava account")

        except Exception as e:
            logger.error(f"Error loading products: {e}")
            # Extract product ID from static URL as fallback
            self._extract_product_id_from_url()

    def _extract_product_id_from_url(self):
        """Extract product ID from static payment URL"""
        url = self.PAYMENT_LINKS.get(100, "")
        if "products/" in url:
            parts = url.split("products/")[1].split("/")
            if parts:
                self.product_id = parts[0]
                logger.info(f"Using product ID from URL: {self.product_id}")

    def create_payment(
        self,
        credits: int,
        order_id: str,
        email: str = None,
        description: str = None,
        custom_fields: Dict = None
    ) -> Optional[Dict]:
        """
        Create payment through SDK or return static link

        Args:
            credits: Number of tokens
            order_id: Transaction ID
            email: Customer email
            description: Payment description
            custom_fields: Additional data

        Returns:
            Dict with payment URL or None
        """

        # Validate package
        if credits not in self.SUPPORTED_PACKAGES:
            logger.error(f"Unsupported package: {credits} tokens")
            return None

        amount = Decimal(credits * 0.05)  # $0.05 per token

        # Try SDK first
        if self.client and self.product_id:
            try:
                payment_request = PaymentCreateRequest(
                    amount=float(amount),
                    order_id=str(order_id),
                    email=email or "customer@example.com",
                    offer_id=self.product_id,
                    currency="USD",
                    description=description or f"Purchase {credits} tokens",
                    success_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/payment/success",
                    fail_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/payment/fail",
                    hook_url=f"{getattr(settings, 'PUBLIC_BASE_URL', '')}/api/miniapp/lava-webhook",
                    custom_fields=custom_fields or {}
                )

                response = self.client.create_one_time_payment(payment_request)

                if response:
                    payment_url = getattr(response, 'url', None)
                    payment_id = getattr(response, 'id', None)

                    if payment_url:
                        logger.info(f"Payment created via SDK: {payment_id}")
                        return {
                            'url': payment_url,
                            'id': payment_id,
                            'method': 'sdk',
                            'success': True
                        }

            except Exception as e:
                logger.error(f"SDK payment failed: {e}")

        # Fallback to static link
        static_url = self.PAYMENT_LINKS.get(credits)

        if static_url:
            # Add parameters to track the payment
            payment_url = f"{static_url}?order_id={order_id}"
            if email:
                payment_url += f"&email={email}"

            logger.info(f"Using static link for {credits} tokens")
            return {
                'url': payment_url,
                'id': order_id,
                'method': 'static',
                'success': True
            }

        logger.error(f"No payment method available for {credits} tokens")
        return None

    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature through SDK"""
        if self.client:
            try:
                return self.client.verify_webhook_signature(payload, signature)
            except Exception as e:
                logger.error(f"Signature verification failed: {e}")
        return False


# Singleton instance
_provider_instance = None


def get_provider() -> LavaProvider:
    """Get singleton provider instance"""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = LavaProvider()
    return _provider_instance


def get_payment_url(
    credits: int,
    transaction_id: str,
    user_email: str = None,
    use_sdk: bool = True
) -> Optional[str]:
    """
    Get payment URL for token purchase

    Args:
        credits: Number of tokens (currently only 100 supported)
        transaction_id: Transaction ID for tracking
        user_email: Customer email
        use_sdk: Whether to try SDK first

    Returns:
        Payment URL or None
    """

    provider = get_provider()

    result = provider.create_payment(
        credits=credits,
        order_id=transaction_id,
        email=user_email,
        description=f"Purchase {credits} tokens",
        custom_fields={
            'credits': credits,
            'email': user_email or '',
            'transaction_id': str(transaction_id)
        }
    )

    return result['url'] if result else None
