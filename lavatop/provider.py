"""Lava.top payment provider using official REST API.

The provider tries to follow the reference flow from Lava documentation:
1. Получить список продуктов через `/api/v2/products`.
2. Найти оффер (offerId) для нашего пакета токенов.
3. Создать контракт `/api/v2/invoice` и вернуть `paymentUrl`.
Если REST‑вызовы недоступны, используется статическая fallback‑ссылка из конфигурации.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://gate.lava.top"
PRODUCTS_CACHE_TTL = 300  # seconds


class LavaProvider:
    """Wrapper around Lava.top public API."""

    def __init__(self) -> None:
        self.api_base = getattr(settings, "LAVA_API_BASE_URL", DEFAULT_API_BASE).rstrip("/")
        self.api_key = getattr(settings, "LAVA_API_KEY", None)
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-Api-Key": self.api_key})
        self.session.headers.update({"Accept": "application/json"})

        self._products_cache: Optional[list] = None
        self._products_cache_ts: float = 0.0
        self.config = self._load_config()

        # Для совместимости с webhook.verify_signature
        self.client = None

    # ------------------------------------------------------------------
    # Конфигурация и данные из API
    # ------------------------------------------------------------------
    @staticmethod
    def _load_config() -> Dict:
        config_path = Path(__file__).resolve().parent / "config" / "products.json"
        try:
            return json.loads(config_path.read_text("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load Lava products config: %s", exc)
            return {"products": []}

    def _fetch_products(self) -> list:
        if self._products_cache and time.time() - self._products_cache_ts < PRODUCTS_CACHE_TTL:
            return self._products_cache

        if not self.api_key:
            logger.warning("LAVA_API_KEY not configured; skipping Lava API request")
            self._products_cache = []
            self._products_cache_ts = time.time()
            return self._products_cache

        url = f"{self.api_base}/api/v2/products"
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            items = data.get("items") or data.get("data") or []
            self._products_cache = items
            self._products_cache_ts = time.time()
            logger.debug("Fetched %s products from Lava", len(items))
        except requests.HTTPError as exc:  # noqa: BLE001
            logger.error("Failed to fetch Lava products: %s - %s", exc.response.status_code, exc.response.text)
            self._products_cache = []
            self._products_cache_ts = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch Lava products: %s", exc)
            self._products_cache = []
            self._products_cache_ts = time.time()
        return self._products_cache

    def _config_entry(self, credits: int) -> Optional[Dict]:
        for product in self.config.get("products", []):
            if product.get("tokens") == credits and product.get("active", True):
                return product
        return None

    def _resolve_offer(self, entry: Dict) -> Optional[Dict]:
        products = self._fetch_products()
        currency = entry.get("currency", "USD")
        amount = entry.get("price")
        configured_product_id = entry.get("lava_product_id")
        configured_offer_id = entry.get("offer_id")

        candidate = None
        for product in products:
            if configured_product_id and product.get("id") != configured_product_id:
                continue
            for offer in product.get("offers") or []:
                if configured_offer_id and offer.get("id") != configured_offer_id:
                    continue
                for price in offer.get("prices") or []:
                    if currency and price.get("currency") != currency:
                        continue
                    if amount is not None and price.get("amount") is not None:
                        if abs(price["amount"] - amount) > 1e-6:
                            continue
                    candidate = {
                        "product_id": product.get("id"),
                        "offer_id": offer.get("id"),
                        "currency": price.get("currency", currency),
                        "amount": price.get("amount", amount),
                        "periodicity": price.get("periodicity"),
                    }
                    break
                if candidate:
                    break
            if candidate:
                break

        if candidate:
            return candidate

        if configured_offer_id:
            logger.warning(
                "Offer %s not found in Lava API; using config fallback",
                configured_offer_id,
            )
            return {
                "product_id": configured_product_id,
                "offer_id": configured_offer_id,
                "currency": currency,
                "amount": amount,
                "periodicity": entry.get("periodicity"),
            }

        logger.error("Unable to resolve offer for product config: %s", entry)
        return None

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------
    def create_payment(
        self,
        credits: int,
        order_id: str,
        email: Optional[str] = None,
        description: Optional[str] = None,
        custom_fields: Optional[Dict] = None,
    ) -> Optional[Dict]:
        entry = self._config_entry(credits)
        if not entry:
            logger.error("Unsupported credits package: %s", credits)
            return self._build_fallback(entry, order_id, email)

        offer = self._resolve_offer(entry)
        if not offer or not offer.get("offer_id"):
            return self._build_fallback(entry, order_id, email)

        if not self.api_key:
            logger.warning("LAVA_API_KEY is missing; falling back to static link")
            return self._build_fallback(entry, order_id, email)

        payload: Dict[str, object] = {
            "email": email or entry.get("default_email") or "customer@example.com",
            "offerId": offer["offer_id"],
            "currency": offer.get("currency") or entry.get("currency") or "USD",
        }
        if entry.get("payment_method"):
            payload["paymentMethod"] = entry["payment_method"]
        if entry.get("periodicity"):
            payload["periodicity"] = entry["periodicity"]
        if entry.get("buyer_language"):
            payload["buyerLanguage"] = entry["buyer_language"]

        url = f"{self.api_base}/api/v2/invoice"
        try:
            response = self.session.post(url, json=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
            payment_url = data.get("paymentUrl")
            if payment_url:
                logger.info("Lava invoice %s created via API", data.get("id"))
                return {
                    "url": payment_url,
                    "payment_id": data.get("id"),
                    "method": "api",
                    "raw": data,
                }
            logger.error("Invoice created without paymentUrl: %s", data)
        except requests.HTTPError as exc:  # noqa: BLE001
            logger.error(
                "Failed to create Lava invoice (status %s): %s",
                exc.response.status_code,
                exc.response.text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to create Lava invoice: %s", exc)

        return self._build_fallback(entry, order_id, email)

    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """SDK недоступен – возвращаем None, чтобы fallback сработал."""
        return False

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------
    @staticmethod
    def _build_fallback(entry: Optional[Dict], order_id: str, email: Optional[str]) -> Optional[Dict]:
        if not entry:
            logger.error("Fallback requested without product entry")
            return None

        static_url = entry.get("static_url")
        if not static_url:
            logger.error("No fallback URL configured for product %s", entry.get("tokens"))
            return None

        url = static_url
        params = []
        if order_id:
            params.append(f"order_id={order_id}")
        if email:
            params.append(f"email={email}")
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{'&'.join(params)}"

        logger.info("Using fallback static link for order %s", order_id)
        return {"url": url, "payment_id": order_id, "method": "static"}


_provider_instance: Optional[LavaProvider] = None


def get_provider() -> LavaProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = LavaProvider()
    return _provider_instance


def get_payment_url(
    credits: int,
    transaction_id: str,
    user_email: Optional[str] = None,
    custom_fields: Optional[Dict] = None,
) -> Optional[Dict]:
    provider = get_provider()
    return provider.create_payment(
        credits=credits,
        order_id=str(transaction_id),
        email=user_email,
        description=f"Purchase {credits} tokens",
        custom_fields=custom_fields,
    )
