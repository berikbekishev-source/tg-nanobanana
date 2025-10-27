"""Модели и константы для работы с генерацией промтов по референсу."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ReferencePromptModel:
    """Описание модели генерации промта по референсу."""

    slug: str
    title: str
    description: str
    gemini_model: str = "models/gemini-2.5-pro"


REFERENCE_PROMPT_MODELS: Dict[str, ReferencePromptModel] = {
    "veo_3": ReferencePromptModel(
        slug="veo_3",
        title="VEO_3",
        description="Создание JSON-промта для Veo 3 на основе референса",
    ),
}


def get_reference_prompt_model(slug: str) -> ReferencePromptModel:
    """Возвращает модель по slug либо выбрасывает KeyError."""

    try:
        return REFERENCE_PROMPT_MODELS[slug]
    except KeyError as exc:  # pragma: no cover - защитим от неожиданных значений
        raise KeyError(f"Unknown reference prompt model: {slug}") from exc
