"""Вспомогательные функции для тарификации промта по референсу."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional, Tuple

from asgiref.sync import sync_to_async

from botapp.business.pricing import get_base_price_tokens
from botapp.models import AIModel
from . import REFERENCE_PROMPT_PRICING_SLUG

logger = logging.getLogger(__name__)


async def get_reference_pricing_model() -> Optional[AIModel]:
    """Возвращает модель тарификации промта по референсу."""
    try:
        return await sync_to_async(AIModel.objects.get)(slug=REFERENCE_PROMPT_PRICING_SLUG, is_active=True)
    except AIModel.DoesNotExist:
        return None


async def get_reference_prompt_price_tokens(model: Optional[AIModel] = None) -> Optional[Decimal]:
    """Стоимость в токенах за генерацию промта по референсу."""
    target_model = model or await get_reference_pricing_model()
    if not target_model:
        return None
    try:
        return await sync_to_async(get_base_price_tokens)(target_model)
    except Exception as exc:  # pragma: no cover - для логирования редких ошибок
        logger.warning("Не удалось получить стоимость промта по референсу: %s", exc)
        return None


async def get_reference_pricing_model_and_cost() -> Tuple[Optional[AIModel], Optional[Decimal]]:
    """Возвращает пару (модель, стоимость в токенах)."""
    model = await get_reference_pricing_model()
    cost = await get_reference_prompt_price_tokens(model) if model else None
    return model, cost


async def build_reference_prompt_price_line() -> str:
    """Формирует строку со стоимостью для вывода пользователю."""
    cost_tokens = await get_reference_prompt_price_tokens()
    if cost_tokens is None:
        return "Стоимость генерации временно недоступна."
    return f"Стоимость генерации ⚡{cost_tokens:.2f} токенов за один промт."
