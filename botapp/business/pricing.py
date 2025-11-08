"""Helpers for working with pricing settings."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache

from django.apps import apps

TOKEN_QUANT = Decimal('0.01')


@lru_cache(maxsize=1)
def _get_cached_settings():
    PricingSettings = apps.get_model('botapp', 'PricingSettings')
    settings = PricingSettings.objects.order_by('id').first()
    if not settings:
        raise RuntimeError("Pricing settings are not configured")
    return settings


def get_pricing_settings():
    """Возвращает текущие настройки прайсинга."""
    return _get_cached_settings()


def invalidate_pricing_settings_cache() -> None:
    """Сбрасывает кэш настроек (используется сигналами/admin)."""
    _get_cached_settings.cache_clear()


def usd_to_tokens(amount_usd: Decimal | float | int) -> Decimal:
    """Переводит сумму USD в токены по текущему курсу."""
    amount = Decimal(str(amount_usd))
    settings = get_pricing_settings()
    tokens = amount * settings.usd_to_token_rate
    return tokens.quantize(TOKEN_QUANT, rounding=ROUND_HALF_UP)
