"""Утилиты для генерации JSON-промтов по референсу."""

REFERENCE_PROMPT_PRICING_SLUG = "gemini-2.5-pro"

from .models import ReferencePromptModel, REFERENCE_PROMPT_MODELS, get_reference_prompt_model
from .service import ReferencePromptService, ReferencePromptResult, ReferenceInputPayload

__all__ = [
    "ReferencePromptModel",
    "REFERENCE_PROMPT_MODELS",
    "REFERENCE_PROMPT_PRICING_SLUG",
    "get_reference_prompt_model",
    "ReferencePromptService",
    "ReferencePromptResult",
    "ReferenceInputPayload",
]
