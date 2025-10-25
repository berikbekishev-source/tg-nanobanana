from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class VideoGenerationError(Exception):
    """Базовое исключение для ошибок генерации видео."""


@dataclass
class VideoGenerationResult:
    """Результат генерации видео."""

    content: bytes
    mime_type: str = "video/mp4"
    duration: Optional[int] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None
    provider_job_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseVideoProvider(abc.ABC):
    """Интерфейс поставщика генерации видео."""

    slug: str = "base"

    def __init__(self) -> None:
        self._validate_settings()

    @abc.abstractmethod
    def _validate_settings(self) -> None:
        """Проверка наличия необходимых настроек."""

    @abc.abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        model_name: str,
        generation_type: str,
        params: Dict[str, Any],
        input_media: Optional[bytes] = None,
        input_mime_type: Optional[str] = None,
    ) -> VideoGenerationResult:
        """
        Выполнить генерацию видео.

        Args:
            prompt: пользовательский промт
            model_name: имя модели в Vertex/провайдере
            generation_type: text2video или image2video
            params: параметры генерации (duration, resolution, aspect_ratio и т.д.)
            input_media: байты входного изображения (для image2video)
            input_mime_type: MIME тип входного файла
        """

