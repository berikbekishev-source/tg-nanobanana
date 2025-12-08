from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

from botapp.services import (
    KIE_DEFAULT_BASE_URL,
    _kie_api_request,
    _kie_extract_result_urls,
    _kie_poll_task,
    _download_binary_file,
    supabase_upload_png,
)

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult


class MidjourneyVideoProvider(BaseVideoProvider):
    """Провайдер генерации видео через Midjourney (KIE.AI)."""

    slug = "midjourney"

    _CREATE_ENDPOINT = "/api/v1/mj/generate"
    _STATUS_ENDPOINT = "/api/v1/mj/record-info"
    _DEFAULT_POLL_INTERVAL = 5
    _DEFAULT_POLL_TIMEOUT = 12 * 60
    _MAX_IMAGE_BYTES = 10 * 1024 * 1024

    def _validate_settings(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "MIDJOURNEY_KIE_API_KEY", None)
        if not self._api_key:
            raise VideoGenerationError("MIDJOURNEY_KIE_API_KEY не задан — Midjourney Video недоступен.")

        base_url = getattr(settings, "MIDJOURNEY_KIE_BASE_URL", KIE_DEFAULT_BASE_URL) or KIE_DEFAULT_BASE_URL
        self._base_url: str = base_url.rstrip("/")

        poll_interval = getattr(settings, "MIDJOURNEY_KIE_POLL_INTERVAL", None)
        poll_timeout = getattr(settings, "MIDJOURNEY_KIE_POLL_TIMEOUT", None)
        self._poll_interval: int = int(poll_interval) if poll_interval else self._DEFAULT_POLL_INTERVAL
        self._poll_timeout: int = int(poll_timeout) if poll_timeout else self._DEFAULT_POLL_TIMEOUT

        timeout_raw = getattr(settings, "MIDJOURNEY_KIE_REQUEST_TIMEOUT", None)
        self._request_timeout = (
            httpx.Timeout(float(timeout_raw), connect=10.0)
            if timeout_raw
            else httpx.Timeout(120.0, connect=10.0)
        )

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
        logger.info(f"[MIDJOURNEY_VIDEO] Начало генерации: type={generation_type}, prompt={prompt[:100]}...")
        if (generation_type or "").lower() != "image2video":
            raise VideoGenerationError("Midjourney Video поддерживает только режим image2video.")

        if not input_media and params.get("image_url"):
            try:
                logger.info(f"[MIDJOURNEY_VIDEO] Скачивание изображения: {params.get('image_url')[:100]}...")
                input_media = _download_binary_file(str(params.get("image_url")))
                input_mime_type = input_mime_type or params.get("input_image_mime_type") or "image/png"
            except Exception as exc:
                logger.error(f"[MIDJOURNEY_VIDEO] Ошибка загрузки изображения: {exc}")
                raise VideoGenerationError("Не удалось загрузить исходное изображение по ссылке.") from exc

        if not input_media:
            raise VideoGenerationError("Не передано изображение для режима image2video.")

        if len(input_media) > self._MAX_IMAGE_BYTES:
            logger.error(f"[MIDJOURNEY_VIDEO] Изображение слишком большое: {len(input_media)} bytes")
            raise VideoGenerationError("Изображение превышает максимально допустимый размер (10 МБ).")

        logger.info(f"[MIDJOURNEY_VIDEO] Конвертация в PNG и загрузка в Supabase")
        png_bytes = self._convert_to_png_bytes(input_media, input_mime_type)
        upload_obj = supabase_upload_png(png_bytes)
        image_url = self._extract_public_url(upload_obj)
        if not image_url:
            logger.error(f"[MIDJOURNEY_VIDEO] Не получен public_url от Supabase: {upload_obj}")
            raise VideoGenerationError("Не удалось получить ссылку на изображение после загрузки.")
        logger.info(f"[MIDJOURNEY_VIDEO] Изображение загружено: {image_url[:100]}...")

        payload: Dict[str, Any] = {
            "taskType": "mj_video",
            "prompt": prompt,
            "fileUrl": image_url,
        }

        aspect_ratio = params.get("aspect_ratio") or params.get("aspectRatio")
        if aspect_ratio:
            payload["aspectRatio"] = str(aspect_ratio)

        version = params.get("version") or params.get("modelVersion") or "7"
        payload["version"] = str(version)

        for key, field in (
            ("speed", "speed"),
            ("variety", "variety"),
            ("stylization", "stylization"),
            ("weirdness", "weirdness"),
            ("watermark", "waterMark"),
            ("waterMark", "waterMark"),
            ("callBackUrl", "callBackUrl"),
            ("ow", "ow"),
        ):
            value = params.get(key)
            if value is not None:
                payload[field] = value

        logger.debug(f"[MIDJOURNEY_VIDEO] Payload: {json.dumps(payload, ensure_ascii=False)[:500]}")
        response = _kie_api_request(
            base_url=self._base_url,
            api_key=self._api_key,
            method="POST",
            endpoint=self._CREATE_ENDPOINT,
            json_payload=payload,
            timeout=self._request_timeout,
        )
        logger.info(f"[MIDJOURNEY_VIDEO] Create response: code={response.get('code')}, data={json.dumps(response.get('data', {}), ensure_ascii=False)[:300]}")

        if response.get("code") != 200:
            logger.error(f"[MIDJOURNEY_VIDEO] Ошибка создания задачи: {json.dumps(response, ensure_ascii=False)[:500]}")
            raise VideoGenerationError(f"Midjourney: ошибка создания задачи: {response}")

        data = response.get("data") or {}
        task_id = data.get("taskId")
        if not task_id:
            logger.error(f"[MIDJOURNEY_VIDEO] Нет taskId в ответе: {json.dumps(data, ensure_ascii=False)[:300]}")
            raise VideoGenerationError("Midjourney не вернул идентификатор задачи.")

        logger.info(f"[MIDJOURNEY_VIDEO] Задача создана: task_id={task_id}, начинаем polling")
        job_data = _kie_poll_task(
            base_url=self._base_url,
            api_key=self._api_key,
            task_id=task_id,
            timeout=self._request_timeout,
            poll_interval=self._poll_interval,
            poll_timeout=self._poll_timeout,
            endpoint=self._STATUS_ENDPOINT,
        )
        logger.info(f"[MIDJOURNEY_VIDEO] Polling завершен, status={job_data.get('status')}")

        urls = _kie_extract_result_urls(job_data)
        if not urls:
            logger.error(f"[MIDJOURNEY_VIDEO] Нет URL результата в job_data: {json.dumps(job_data, ensure_ascii=False)[:500]}")
            raise VideoGenerationError("Midjourney не вернул ссылку на результат.")

        logger.info(f"[MIDJOURNEY_VIDEO] Скачивание видео: {urls[0][:100]}...")
        video_bytes = None
        for url in urls:
            try:
                video_bytes = _download_binary_file(url)
                logger.info(f"[MIDJOURNEY_VIDEO] Видео скачано: {len(video_bytes)} bytes")
                break
            except Exception as exc:
                logger.warning(f"[MIDJOURNEY_VIDEO] Ошибка скачивания {url[:100]}: {exc}")
                continue
        if not video_bytes:
            logger.error(f"[MIDJOURNEY_VIDEO] Не удалось скачать видео ни по одной ссылке")
            raise VideoGenerationError("Не удалось скачать видео от Midjourney.")

        duration = self._extract_first_number(job_data, ("duration", "videoDuration", "seconds"))
        aspect = self._extract_first_string(job_data, ("aspectRatio", "ratio")) or aspect_ratio
        resolution = self._extract_first_string(job_data, ("resolution", "videoResolution"))

        metadata = {
            "job": job_data,
            "initialPayload": payload,
            "prompt": prompt,
            "generationType": generation_type,
        }

        return VideoGenerationResult(
            content=video_bytes,
            mime_type="video/mp4",
            duration=int(duration) if isinstance(duration, (int, float)) else None,
            aspect_ratio=aspect,
            resolution=resolution,
            provider_job_id=task_id,
            metadata=metadata,
        )

    @staticmethod
    def _convert_to_png_bytes(raw: bytes, mime: Optional[str]) -> bytes:
        mime_value = (mime or "").lower()
        if mime_value == "image/png":
            return raw
        try:
            from PIL import Image
        except ImportError:
            return raw
        try:
            from io import BytesIO

            with Image.open(BytesIO(raw)) as img:
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                return buffer.getvalue()
        except Exception:
            return raw

    @staticmethod
    def _extract_public_url(upload_obj) -> Optional[str]:
        if isinstance(upload_obj, dict):
            return upload_obj.get("public_url") or upload_obj.get("publicUrl") or upload_obj.get("publicURL")
        return upload_obj

    @staticmethod
    def _extract_first_number(payload: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
            if isinstance(value, dict):
                for inner_key in ("value", "duration"):
                    inner_val = value.get(inner_key)
                    if isinstance(inner_val, (int, float)):
                        return float(inner_val)
        return None

    @staticmethod
    def _extract_first_string(payload: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


register_video_provider(MidjourneyVideoProvider.slug, MidjourneyVideoProvider)
