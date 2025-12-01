from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

import httpx
from django.conf import settings

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult

logger = logging.getLogger(__name__)


def resolve_sora_size(resolution: Optional[Any], aspect_ratio: Optional[Any]) -> Optional[str]:
    """Подбирает размеры кадра для подсказок (720p/1080p, 16:9 или 9:16)."""
    resolution_str = str(resolution).lower() if resolution else "720p"
    aspect_ratio_str = str(aspect_ratio).replace(" ", "") if aspect_ratio else "16:9"

    if "x" in resolution_str:
        return resolution_str

    presets = {
        ("720p", "16:9"): "1280x720",
        ("720p", "9:16"): "720x1280",
        ("1080p", "16:9"): "1920x1080",
        ("1080p", "9:16"): "1080x1920",
    }

    return presets.get((resolution_str, aspect_ratio_str))


def resolve_sora_dimensions(resolution: Optional[Any], aspect_ratio: Optional[Any]) -> Optional[Tuple[int, int]]:
    """Возвращает требуемые размеры изображения для image2video, если известны."""
    size = resolve_sora_size(resolution, aspect_ratio)
    if not size:
        return None
    try:
        w, h = size.lower().split("x", maxsplit=1)
        return int(w), int(h)
    except Exception:
        return None


class GeminigenSoraProvider(BaseVideoProvider):
    """
    Провайдер генерации видео через Geminigen (Sora endpoint).

    Использует те же переменные окружения, что и Veo на Geminigen:
    - GEMINIGEN_API_KEY
    - GEMINIGEN_API_BASE_URL (default: https://api.geminigen.ai)
    """

    slug = "openai"
    supports_extension = False

    _ENDPOINT = "/uapi/v1/video-gen/sora"
    _ALLOWED_MODELS = {"sora-2", "sora-2-pro", "sora-2-pro-hd"}

    def _validate_settings(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "GEMINIGEN_API_KEY", None)
        if not self._api_key:
            raise VideoGenerationError("GEMINIGEN_API_KEY не задан — Sora недоступна.")

        base_url = getattr(settings, "GEMINIGEN_API_BASE_URL", "https://api.geminigen.ai") or "https://api.geminigen.ai"
        self._base_url: str = base_url.rstrip("/")

        timeout_raw = getattr(settings, "GEMINIGEN_REQUEST_TIMEOUT", None)
        self._timeout = (
            httpx.Timeout(float(timeout_raw), connect=10.0)
            if timeout_raw
            else httpx.Timeout(120.0, connect=10.0)
        )

    @staticmethod
    def _normalize_model(raw: Optional[str]) -> str:
        # По требованию используем sora-2 вне зависимости от внутренних имён.
        _ = raw  # сохраняем аргумент для совместимости
        return "sora-2"

    @staticmethod
    def _map_aspect(raw: Optional[str]) -> Tuple[str, str]:
        """Возвращает (api_value, human_value)."""
        value = (raw or "").lower().replace(" ", "")
        if value in {"16:9", "landscape"}:
            return "landscape", "16:9"
        if value in {"9:16", "portrait"}:
            return "portrait", "9:16"
        return "landscape", "16:9"

    @staticmethod
    def _map_resolution(raw: Optional[str]) -> Tuple[str, str]:
        """Возвращает (api_value, human_value)."""
        val = (raw or "").lower()
        if val in {"1080p", "large"}:
            return "large", "1080p"
        return "small", "720p"

    def _resolve_duration(self, model: str, params: Dict[str, Any]) -> int:
        allowed = [10, 15]
        raw = params.get("duration") or params.get("seconds")
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            value = allowed[0]

        if value not in allowed:
            value = allowed[0]
        return value

    def _download_media(self, url: str) -> Tuple[bytes, str]:
        timeout = httpx.Timeout(600.0, connect=30.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
            mime_type = resp.headers.get("content-type", "video/mp4")
            return resp.content, mime_type.split(";")[0].strip()

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
        if not prompt or not prompt.strip():
            raise VideoGenerationError("Промт обязателен для Sora.")

        raw_model = model_name or params.get("model") or params.get("api_model_name")
        model_value = self._normalize_model(raw_model)
        if not model_value or model_value not in self._ALLOWED_MODELS:
            raise VideoGenerationError(
                f"Модель '{raw_model}' не поддерживается Geminigen Sora. "
                "Используйте: sora-2, sora-2-pro или sora-2-pro-hd."
            )

        aspect_api, aspect_human = self._map_aspect(params.get("aspect_ratio") or params.get("aspectRatio"))
        resolution_api, resolution_human = self._map_resolution(params.get("resolution"))
        duration_value = self._resolve_duration(model_value, params)

        form_data: Dict[str, Any] = {
            "prompt": prompt,
            "model": model_value,
            "aspect_ratio": aspect_api,
            "resolution": resolution_api,
            "duration": duration_value,
        }

        ref_history = params.get("ref_history") or params.get("refHistory")
        if ref_history:
            form_data["ref_history"] = str(ref_history)

        files = None
        if input_media:
            files = {"files": ("reference.png", input_media, input_mime_type or "image/png")}
        elif params.get("file_urls"):
            form_data["file_urls"] = params.get("file_urls")
        elif params.get("image_url"):
            form_data["file_urls"] = params.get("image_url")

        logger.info(
            "[GEMINIGEN_SORA] Запрос: model=%s aspect=%s resolution=%s duration=%s has_file=%s",
            model_value,
            aspect_api,
            resolution_api,
            duration_value,
            bool(files),
        )

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}{self._ENDPOINT}",
                    headers={"x-api-key": self._api_key},
                    data=form_data,
                    files=files,
                    follow_redirects=True,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
            resp = exc.response
            detail = ""
            status_code = getattr(resp, "status_code", None)
            if resp is not None:
                try:
                    err_payload = resp.json()
                    detail = json.dumps(err_payload, ensure_ascii=False)
                except Exception:
                    detail = resp.text
            raise VideoGenerationError(f"Geminigen Sora вернул ошибку {status_code}: {detail}") from exc
        except httpx.RequestError as exc:
            raise VideoGenerationError(f"Не удалось выполнить запрос к Geminigen Sora: {exc}") from exc

        payload: Dict[str, Any] = {}
        try:
            payload = response.json()
        except Exception:
            payload = {"raw_text": response.text}

        job_id = (
            payload.get("uuid")
            or payload.get("id")
            or payload.get("job_id")
            or payload.get("jobId")
            or (payload.get("data") or {}).get("uuid")
        )
        media_url = (
            payload.get("media_url")
            or payload.get("mediaUrl")
            or (payload.get("data") or {}).get("media_url")
            or (payload.get("data") or {}).get("mediaUrl")
        )

        metadata = {
            "response": payload,
            "request": form_data,
            "generationType": generation_type,
        }
        if files:
            metadata["hasReferenceImage"] = True

        if media_url:
            video_bytes, mime_type = self._download_media(str(media_url))
            return VideoGenerationResult(
                content=video_bytes,
                mime_type=mime_type or "video/mp4",
                duration=duration_value,
                aspect_ratio=aspect_human,
                resolution=resolution_human,
                provider_job_id=str(job_id) if job_id else None,
                metadata=metadata,
            )

        if not job_id:
            raise VideoGenerationError(
                "Geminigen Sora не вернул uuid задачи и ссылку на видео. Проверьте параметры или баланс."
            )

        logger.info(
            "[GEMINIGEN_SORA] Задача отправлена: uuid=%s (ожидание вебхука/пула)",
            job_id,
        )

        return VideoGenerationResult(
            content=None,
            mime_type="video/mp4",
            duration=duration_value,
            aspect_ratio=aspect_human,
            resolution=resolution_human,
            provider_job_id=str(job_id),
            metadata=metadata,
        )


register_video_provider(GeminigenSoraProvider.slug, GeminigenSoraProvider)
