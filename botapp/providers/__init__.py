"""
Provider registry for model integrations (video, image, etc.).

Currently used for video generation providers.
"""

from .video import get_video_provider, register_video_provider, VideoGenerationError, VideoGenerationResult

__all__ = [
    "get_video_provider",
    "register_video_provider",
    "VideoGenerationError",
    "VideoGenerationResult",
]

