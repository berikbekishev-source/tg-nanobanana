from __future__ import annotations

import base64
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from django.conf import settings

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult


class OpenAISoraProvider(BaseVideoProvider):
    """Провайдер генерации видео через OpenAI Sora v2."""

    slug = "openai"

    _DEFAULT_API_BASE = "https://api.openai.com/v1"
    _DEFAULT_POLL_INTERVAL = 5  # seconds
    _DEFAULT_POLL_TIMEOUT = 15 * 60  # seconds
    _DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=30.0)
    _DEFAULT_CONTENT_TIMEOUT = httpx.Timeout(600.0, connect=30.0)
    _SUPPORTED_PARAM_KEYS = {
        "duration",
        "duration_seconds",
        "aspect_ratio",
        "resolution",
        "fps",
        "seed",
        "style",
        "camera",
        "camera_motion",
        "motion",
        "look",
        "lighting",
        "negative_prompt",
        "audio",
    }

    def _validate_settings(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "OPENAI_API_KEY", None)
        if not self._api_key:
            raise VideoGenerationError("OPENAI_API_KEY не задан — Sora недоступна.")

        self._api_base: str = getattr(settings, "OPENAI_API_BASE", self._DEFAULT_API_BASE) or self._DEFAULT_API_BASE
        self._organization: Optional[str] = getattr(settings, "OPENAI_ORGANIZATION", None)
        self._poll_interval: int = int(
            getattr(settings, "OPENAI_VIDEO_POLL_INTERVAL", self._DEFAULT_POLL_INTERVAL)
        )
        self._poll_timeout: int = int(getattr(settings, "OPENAI_VIDEO_POLL_TIMEOUT", self._DEFAULT_POLL_TIMEOUT))
        self._request_timeout = self._resolve_timeout(
            getattr(settings, "OPENAI_VIDEO_REQUEST_TIMEOUT", None),
            default=self._DEFAULT_TIMEOUT,
            default_connect=30.0,
        )
        self._content_timeout = self._resolve_timeout(
            getattr(settings, "OPENAI_VIDEO_CONTENT_TIMEOUT", None),
            default=self._DEFAULT_CONTENT_TIMEOUT,
            default_connect=30.0,
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
        payload = self._build_payload(
            prompt=prompt,
            model_name=model_name,
            generation_type=generation_type,
            params=params,
            input_media=input_media,
            input_mime_type=input_mime_type,
        )

        initial_response = self._request_json("POST", "/videos", json_payload=payload)
        job_id = initial_response.get("id")
        if not job_id:
            raise VideoGenerationError("OpenAI Sora не вернул идентификатор задания.")

        job_status = initial_response.get("status")
        if job_status != "succeeded":
            job_details = self._poll_job(job_id)
        else:
            job_details = initial_response

        video_bytes, mime_type = self._download_video(job_id)

        metadata = {
            "job": job_details,
            "initialResponse": initial_response,
            "prompt": prompt,
            "generationType": generation_type,
        }

        output_info: Dict[str, Any] = job_details.get("output") or job_details.get("result") or {}
        duration = self._extract_duration(output_info, params)
        resolution = self._extract_resolution(output_info, params)
        aspect_ratio = self._extract_aspect_ratio(output_info, params)

        return VideoGenerationResult(
            content=video_bytes,
            mime_type=mime_type or "video/mp4",
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            provider_job_id=job_id,
            metadata=metadata,
        )

    def _build_payload(
        self,
        *,
        prompt: str,
        model_name: str,
        generation_type: str,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> Dict[str, Any]:
        if generation_type not in {"text2video", "image2video"}:
            raise VideoGenerationError(f"Режим генерации '{generation_type}' не поддерживается Sora.")

        payload: Dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "mode": "image2video" if generation_type == "image2video" else "text2video",
        }

        if generation_type == "image2video":
            if not input_media:
                raise VideoGenerationError("Для режима image2video требуется входное изображение.")
            encoded_media = base64.b64encode(input_media).decode("utf-8")
            payload["input_image"] = {
                "data": encoded_media,
                "mime_type": input_mime_type or "image/png",
            }

        for key, value in (params or {}).items():
            if value is None:
                continue
            normalized_key = key.strip()
            if normalized_key in self._SUPPORTED_PARAM_KEYS:
                payload[normalized_key] = value
            elif normalized_key == "durationSeconds":
                payload["duration"] = value
            elif normalized_key == "aspectRatio":
                payload["aspect_ratio"] = value
            elif normalized_key == "resolution":
                payload["resolution"] = value

        return payload

    def _poll_job(self, job_id: str) -> Dict[str, Any]:
        start_time = time.monotonic()
        while True:
            if time.monotonic() - start_time > self._poll_timeout:
                raise VideoGenerationError("Превышено время ожидания результата от Sora.")

            job_details = self._request_json("GET", f"/videos/{job_id}")
            status = job_details.get("status")
            if status in {"queued", "processing", "running"}:
                time.sleep(self._poll_interval)
                continue
            if status == "succeeded":
                return job_details
            if status == "failed":
                error_detail = job_details.get("error") or job_details.get("failure_reason")
                raise VideoGenerationError(f"Sora не смогла завершить генерацию: {error_detail}")
            raise VideoGenerationError(f"Неизвестный статус задания Sora: {status}")

    def _download_video(self, job_id: str) -> Tuple[bytes, Optional[str]]:
        response = self._request(
            "GET",
            f"/videos/{job_id}/content",
            timeout=self._content_timeout,
        )
        mime_type = response.headers.get("content-type")
        return response.content, mime_type

    def _extract_duration(self, output_info: Dict[str, Any], params: Dict[str, Any]) -> Optional[int]:
        for key in ("duration_seconds", "duration", "length"):
            if key in output_info and output_info[key] is not None:
                try:
                    return int(round(float(output_info[key])))
                except (TypeError, ValueError):
                    continue
        value = params.get("duration") or params.get("duration_seconds")
        if value is not None:
            try:
                return int(round(float(value)))
            except (TypeError, ValueError):
                return None
        return None

    def _extract_resolution(self, output_info: Dict[str, Any], params: Dict[str, Any]) -> Optional[str]:
        for key in ("resolution", "video_resolution"):
            value = output_info.get(key)
            if isinstance(value, str):
                return value
        return params.get("resolution") or None

    def _extract_aspect_ratio(self, output_info: Dict[str, Any], params: Dict[str, Any]) -> Optional[str]:
        value = output_info.get("aspect_ratio") or output_info.get("aspectRatio")
        if isinstance(value, str):
            return value
        return params.get("aspect_ratio")

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> Dict[str, Any]:
        response = self._request(method, path, json=json_payload, timeout=timeout)
        try:
            return response.json()
        except ValueError as exc:
            raise VideoGenerationError("OpenAI Sora вернула некорректный JSON.") from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> httpx.Response:
        url = self._build_url(path)
        headers = self._build_headers()
        request_timeout = timeout or self._request_timeout

        try:
            with httpx.Client(timeout=request_timeout) as client:
                response = client.request(method, url, headers=headers, json=json, follow_redirects=True)
                response.raise_for_status()
                return response
        except httpx.TimeoutException as exc:
            raise VideoGenerationError("Превышен таймаут запроса к OpenAI Sora.") from exc
        except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
            detail = self._format_error_detail(exc.response)
            status_code = exc.response.status_code if exc.response else None
            if status_code == 401:
                raise VideoGenerationError("Неверный OpenAI API ключ или нет доступа к Sora.") from exc
            if status_code == 403:
                raise VideoGenerationError("Доступ к модели Sora запрещён. Проверьте разрешения в аккаунте OpenAI.") from exc
            if status_code == 429:
                raise VideoGenerationError(
                    "Превышены лимиты OpenAI Sora. Снизьте частоту запросов или увеличьте квоты."
                ) from exc
            raise VideoGenerationError(f"Ошибка OpenAI Sora ({status_code}): {detail}") from exc
        except httpx.RequestError as exc:
            raise VideoGenerationError(f"Ошибка соединения с OpenAI Sora: {exc}") from exc

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }
        if self._organization:
            headers["OpenAI-Organization"] = self._organization
        return headers

    def _build_url(self, path: str) -> str:
        base = self._api_base.rstrip("/")
        subpath = path.lstrip("/")
        return f"{base}/{subpath}"

    @staticmethod
    def _format_error_detail(response: Optional[httpx.Response]) -> str:
        if not response:
            return "нет дополнительной информации"
        try:
            payload = response.json()
        except ValueError:
            return response.text
        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("message") or str(error)
        if isinstance(error, str):
            return error
        return response.text

    @staticmethod
    def _resolve_timeout(value: Any, *, default: httpx.Timeout, default_connect: float) -> httpx.Timeout:
        if isinstance(value, httpx.Timeout):
            return value
        if isinstance(value, (int, float)):
            return httpx.Timeout(float(value), connect=default_connect)
        return default


register_video_provider(OpenAISoraProvider.slug, OpenAISoraProvider)
