"""Helpers for working with pricing settings."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Tuple, TYPE_CHECKING

from django.apps import apps

if TYPE_CHECKING:  # pragma: no cover
    from botapp.models import AIModel

TOKEN_QUANT = Decimal('0.01')


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
    """Совместимость: кэша больше нет, функция оставлена для вызовов сигналов."""
    return None


def usd_to_tokens(amount_usd: Decimal | float | int) -> Decimal:
    """Переводит сумму USD в токены по текущему курсу."""
    amount = Decimal(str(amount_usd))
    settings = get_pricing_settings()
    tokens = amount * settings.usd_to_token_rate
    return tokens.quantize(TOKEN_QUANT, rounding=ROUND_HALF_UP)


def usd_to_retail_tokens(amount_usd: Decimal | float | int) -> Decimal:
    """Переводит себестоимость в USD в пользовательскую цену (с наценкой и курсом)."""
    amount = Decimal(str(amount_usd))
    settings = get_pricing_settings()
    tokens = amount * settings.usd_to_token_rate * settings.markup_multiplier
    return tokens.quantize(TOKEN_QUANT, rounding=ROUND_HALF_UP)


def _resolve_duration(
    ai_model: 'AIModel',
    duration: Optional[int],
    params: Optional[Dict[str, object]],
) -> int:
    if duration:
        return int(duration)
    if params and params.get("duration"):
        try:
            return int(params["duration"])
        except (TypeError, ValueError):
            pass
    defaults = ai_model.default_params or {}
    if defaults.get("duration"):
        try:
            return int(defaults["duration"])
        except (TypeError, ValueError):
            pass
    return 1


def _resolve_units(
    ai_model: 'AIModel',
    quantity: int = 1,
    duration: Optional[int] = None,
    params: Optional[Dict[str, object]] = None,
) -> Decimal:
    """
    Возвращает количество единиц тарификации с учётом cost_unit модели.
    """
    cost_unit = getattr(ai_model, "cost_unit", None) or ai_model.CostUnit.GENERATION

    if cost_unit == ai_model.CostUnit.IMAGE:
        return Decimal(max(1, quantity))
    if cost_unit == ai_model.CostUnit.SECOND:
        return Decimal(max(1, _resolve_duration(ai_model, duration, params)))
    return Decimal('1')


def compute_seb(
    ai_model: 'AIModel',
    *,
    quantity: int = 1,
    duration: Optional[int] = None,
    params: Optional[Dict[str, object]] = None,
) -> Decimal:
    """Возвращает себестоимость в USD для конкретного запроса."""
    base_cost = ai_model.base_cost_usd or ai_model.unit_cost_usd or Decimal('0.0000')
    cost_unit = ai_model.cost_unit or ai_model.CostUnit.GENERATION

    if cost_unit == ai_model.CostUnit.IMAGE:
        units = Decimal(max(1, quantity))
    elif cost_unit == ai_model.CostUnit.SECOND:
        units = Decimal(max(1, _resolve_duration(ai_model, duration, params)))
    else:
        units = Decimal('1')

    seb = (base_cost * units).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return seb


def calculate_request_cost(
    ai_model: 'AIModel',
    *,
    quantity: int = 1,
    duration: Optional[int] = None,
    params: Optional[Dict[str, object]] = None,
) -> Tuple[Decimal, Decimal]:
    """Возвращает пару (себестоимость USD, цена в токенах) для запроса."""
    seb = compute_seb(ai_model, quantity=quantity, duration=duration, params=params)
    tokens = usd_to_retail_tokens(seb)
    units = _resolve_units(ai_model, quantity=quantity, duration=duration, params=params)

    if seb == Decimal('0.0000'):
        base_price_tokens = Decimal(str(getattr(ai_model, "price", 0) or 0))
        if base_price_tokens > 0 and units > 0:
            tokens = (base_price_tokens * units).quantize(TOKEN_QUANT, rounding=ROUND_HALF_UP)
            settings = get_pricing_settings()
            rate = settings.usd_to_token_rate * settings.markup_multiplier
            if rate > 0:
                seb = (tokens / rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    return seb, tokens


def get_base_price_tokens(ai_model: 'AIModel') -> Decimal:
    """Цена в токенах за базовую единицу (1 изображение или 1 секунду)."""
    _, tokens = calculate_request_cost(ai_model, quantity=1, duration=None, params=None)
    return tokens


def format_price_for_display(tokens: Decimal) -> str:
    return f"⚡{tokens.quantize(TOKEN_QUANT):.2f}"
