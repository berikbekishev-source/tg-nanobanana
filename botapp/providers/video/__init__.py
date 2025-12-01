"""
Video generation provider registry and utilities.
"""
from typing import Dict, Type

from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult

_VIDEO_PROVIDERS: Dict[str, Type[BaseVideoProvider]] = {}


def register_video_provider(slug: str, provider_cls: Type[BaseVideoProvider]) -> None:
    """Register provider implementation under given slug (e.g. 'veo')."""
    _VIDEO_PROVIDERS[slug] = provider_cls


def get_video_provider(slug: str) -> BaseVideoProvider:
    """Instantiate provider by slug."""
    provider_cls = _VIDEO_PROVIDERS.get(slug)
    if not provider_cls:
        raise VideoGenerationError(f"Video provider '{slug}' не настроен.")
    return provider_cls()


__all__ = [
    "BaseVideoProvider",
    "VideoGenerationError",
    "VideoGenerationResult",
    "register_video_provider",
    "get_video_provider",
]

# Register built-in providers
from . import geminigen  # noqa: E402,F401
from . import openai_sora  # noqa: E402,F401
from . import kling  # noqa: E402,F401
from . import midjourney  # noqa: E402,F401
