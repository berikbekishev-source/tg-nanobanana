from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from django.conf import settings

from botapp.media_utils import prepare_image_for_dimensions

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult


def resolve_sora_size(resolution: Optional[Any], aspect_ratio: Optional[Any]) -> Optional[str]:
    """Возвращает строку с размерами (например, 1280x720) для заданного качества/соотношения."""
    if not resolution and not aspect_ratio:
        return None

    resolution_str = str(resolution).lower() if resolution else ""
    aspect_ratio_str = str(aspect_ratio).replace(" ", "") if aspect_ratio else ""

    if "x" in resolution_str:
        return resolution_str

    presets = {
        ("720p", "16:9"): "1280x720",
        ("720p", "9:16"): "720x1280",
        ("720p", "1:1"): "720x720",
        # Sora Video API для 1080p фактически принимает 720p-глубину (1792/1024 не поддерживаются)
        ("1080p", "16:9"): "1280x720",
        ("1080p", "9:16"): "720x1280",
        ("1080p", "1:1"): "1024x1024",
    }

    if not aspect_ratio_str:
        aspect_ratio_str = "16:9"

    if not resolution_str:
        resolution_str = "720p"

    return presets.get((resolution_str, aspect_ratio_str))


def parse_size_value(size: Optional[str]) -> Optional[Tuple[int, int]]:
    if not size:
        return None
    try:
        width_str, height_str = size.lower().split("x", maxsplit=1)
        width = int(width_str.strip())
        height = int(height_str.strip())
        if width > 0 and height > 0:
            return width, height
    except (ValueError, AttributeError):
        return None
    return None


def resolve_sora_dimensions(resolution: Optional[Any], aspect_ratio: Optional[Any]) -> Optional[Tuple[int, int]]:
    """Помогает внешнему коду узнать требуемые размеры входного изображения."""
    size = resolve_sora_size(resolution, aspect_ratio)
    return parse_size_value(size)


class OpenAISoraProvider(BaseVideoProvider):
    """Провайдер генерации видео через OpenAI Sora v2."""

    slug = "openai"

    _DEFAULT_API_BASE = "https://api.openai.com/v1"
    _DEFAULT_POLL_INTERVAL = 5  # seconds
    _DEFAULT_POLL_TIMEOUT = 15 * 60  # seconds
    _DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=30.0)
    _DEFAULT_CONTENT_TIMEOUT = httpx.Timeout(600.0, connect=30.0)

    def _validate_settings(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "OPENAI_API_KEY", None)
        if not self._api_key:
            raise VideoGenerationError("OPENAI_API_KEY не задан — Sora недоступна.")

        self._api_base: str = getattr(settings, "OPENAI_API_BASE", self._DEFAULT_API_BASE) or self._DEFAULT_API_BASE
        self._organization: Optional[str] = getattr(settings, "OPENAI_ORGANIZATION", None)
        self._project_id: Optional[str] = getattr(settings, "OPENAI_PROJECT_ID", None)
        self._beta_header: Optional[str] = getattr(settings, "OPENAI_BETA_HEADER", None)
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
        json_payload, form_payload, files = self._build_create_payload(
            prompt=prompt,
            model_name=model_name,
            generation_type=generation_type,
            params=params,
            input_media=input_media,
            input_mime_type=input_mime_type,
        )

        max_attempts = 3  # 1 основной запрос + 2 ретрая для transient video_generation_failed
        attempt = 0
        last_error: Optional[Exception] = None
        while attempt < max_attempts:
            attempt += 1
            initial_response = self._request_json(
                "POST",
                "/videos",
                json_payload=json_payload,
                data=form_payload,
                files=files,
            )
            job_id = initial_response.get("id")
            if not job_id:
                raise VideoGenerationError("OpenAI Sora не вернул идентификатор задания.")

            job_status = initial_response.get("status")

            try:
                job_details = initial_response if job_status == "succeeded" else self._poll_job(job_id)
                # если дошли сюда без исключения — успех
                break
            except VideoGenerationError as exc:
                message = str(exc).lower()
                if "video_generation_failed" in message and attempt < max_attempts:
                    # transient сбой на стороне Sora — небольшой backoff и повтор
                    time.sleep(3 * attempt)
                    last_error = exc
                    continue
                raise
        else:
            # Если по какой-то причине цикл не вышел через break
            raise last_error or VideoGenerationError("Sora не смогла завершить генерацию после нескольких попыток.")

        video_bytes, mime_type = self._download_video(job_details)

        metadata = {
            "job": job_details,
            "initialResponse": initial_response,
            "prompt": prompt,
            "generationType": generation_type,
        }

        duration = self._extract_duration(job_details, params)
        resolution, aspect_ratio = self._extract_geometry(job_details, params)

        return VideoGenerationResult(
            content=video_bytes,
            mime_type=mime_type or "video/mp4",
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            provider_job_id=job_id,
            metadata=metadata,
        )

    def _build_create_payload(
        self,
        *,
        prompt: str,
        model_name: str,
        generation_type: str,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]], Optional[Dict[str, Tuple[str, bytes, str]]]]:
        if generation_type not in {"text2video", "image2video"}:
            raise VideoGenerationError(f"Режим генерации '{generation_type}' не поддерживается Sora.")

        base_payload: Dict[str, Any] = {
            "prompt": prompt,
        }
        # OpenAI Videos API accepts only prompt/model/seconds/size at creation time.
        if model_name:
            base_payload["model"] = model_name

        seconds = self._resolve_seconds(params)
        if seconds is not None:
            base_payload["seconds"] = str(seconds)

        size = self._resolve_size(params)
        if size:
            base_payload["size"] = size

        json_payload: Optional[Dict[str, Any]] = base_payload.copy()
        form_payload: Optional[Dict[str, str]] = None
        files: Optional[Dict[str, Tuple[str, bytes, str]]] = None

        if generation_type == "image2video":
            if not input_media:
                raise VideoGenerationError("Для режима image2video требуется входное изображение.")
            mime = (input_mime_type or "image/png").lower()
            processed_media = input_media
            size_value = base_payload.get("size")
            target_dims = self._parse_size(size_value) if size_value else None
            if target_dims and mime.startswith("image/"):
                processed_media, mime, _ = prepare_image_for_dimensions(
                    input_media,
                    target_dims[0],
                    target_dims[1],
                    preferred_mime=mime,
                )
            form_payload = {key: str(value) for key, value in base_payload.items()}
            files = {"input_reference": ("reference_image", processed_media, mime)}
            json_payload = None

        return json_payload, form_payload, files

    def _poll_job(self, job_id: str) -> Dict[str, Any]:
        start_time = time.monotonic()
        in_progress_statuses = {"queued", "processing", "running", "in_progress", "in-progress"}
        success_statuses = {"succeeded", "completed"}
        while True:
            if time.monotonic() - start_time > self._poll_timeout:
                raise VideoGenerationError("Превышено время ожидания результата от Sora.")

            job_details = self._request_json("GET", f"/videos/{job_id}")
            status = job_details.get("status")
            if status in in_progress_statuses:
                time.sleep(self._poll_interval)
                continue
            if status in success_statuses:
                return job_details
            if status == "failed":
                error_detail = job_details.get("error") or job_details.get("failure_reason")
                raise VideoGenerationError(f"Sora не смогла завершить генерацию: {error_detail}")
            raise VideoGenerationError(f"Неизвестный статус задания Sora: {status}")

    def _download_video(self, job_details: Dict[str, Any]) -> Tuple[bytes, Optional[str]]:
        download_url = job_details.get("download_url") or job_details.get("video_url")
        if download_url:
            try:
                with httpx.Client(timeout=self._content_timeout) as client:
                    response = client.get(download_url, follow_redirects=True)
                    response.raise_for_status()
                    return response.content, response.headers.get("content-type")
            except httpx.RequestError as exc:
                raise VideoGenerationError(f"Не удалось загрузить видео по ссылке Sora: {exc}") from exc

        job_id = job_details.get("id")
        if not job_id:
            raise VideoGenerationError("Sora вернула ответ без идентификатора задания.")

        for path in (f"/videos/{job_id}/download", f"/videos/{job_id}/content"):
            try:
                response = self._request(
                    "GET",
                    path,
                    timeout=self._content_timeout,
                )
                mime_type = response.headers.get("content-type")
                return response.content, mime_type
            except VideoGenerationError:
                continue

        raise VideoGenerationError("Не удалось получить готовое видео из Sora.")

    def _extract_duration(self, job_details: Dict[str, Any], params: Dict[str, Any]) -> Optional[int]:
        for key in ("seconds", "duration", "duration_seconds"):
            value = job_details.get(key)
            if value is None:
                value = params.get(key)
            if value is None:
                continue
            try:
                return int(round(float(value)))
            except (TypeError, ValueError):
                continue
        return None

    def _extract_geometry(
        self,
        job_details: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        size_value: Optional[str] = job_details.get("size") or params.get("size")
        if not size_value:
            size_value = self._map_size_from_resolution(params.get("resolution"), params.get("aspect_ratio"))

        resolution: Optional[str] = self._normalize_resolution(job_details.get("resolution"))
        aspect_ratio: Optional[str] = job_details.get("aspect_ratio")

        dimensions = self._parse_size(size_value) if size_value else None
        if dimensions:
            width, height = dimensions
            if not resolution:
                resolution = self._resolution_from_dimensions(width, height)
            if not aspect_ratio:
                aspect_ratio = self._format_aspect_ratio(width, height)

        if not resolution:
            resolution = self._normalize_resolution(params.get("resolution"))
        if not aspect_ratio:
            aspect_ratio = params.get("aspect_ratio")

        return resolution, aspect_ratio

    def _resolve_seconds(self, params: Dict[str, Any]) -> Optional[int]:
        for key in ("seconds", "duration", "duration_seconds"):
            value = params.get(key)
            if value is None:
                continue
            try:
                return int(round(float(value)))
            except (TypeError, ValueError):
                continue
        return None

    def _resolve_size(self, params: Dict[str, Any]) -> Optional[str]:
        size = params.get("size")
        if isinstance(size, str) and size.strip():
            return size.strip().lower()
        resolution = params.get("resolution")
        aspect_ratio = params.get("aspect_ratio")
        return self._map_size_from_resolution(resolution, aspect_ratio)

    def _map_size_from_resolution(
        self,
        resolution: Optional[Any],
        aspect_ratio: Optional[Any],
    ) -> Optional[str]:
        return resolve_sora_size(resolution, aspect_ratio)

    @staticmethod
    def _parse_size(size: str) -> Optional[Tuple[int, int]]:
        return parse_size_value(size)

    @staticmethod
    def _resolution_from_dimensions(width: int, height: int) -> Optional[str]:
        if width <= 0 or height <= 0:
            return None
        base = min(width, height)
        mapping = {
            480: "480p",
            512: "512p",
            640: "640p",
            720: "720p",
            768: "768p",
            1080: "1080p",
            1440: "1440p",
            2160: "2160p",
        }
        return mapping.get(base, f"{base}p")

    @staticmethod
    def _format_aspect_ratio(width: int, height: int) -> Optional[str]:
        if width <= 0 or height <= 0:
            return None
        divisor = math.gcd(width, height)
        if divisor == 0:
            return None
        return f"{width // divisor}:{height // divisor}"

    def _normalize_resolution(self, value: Any) -> Optional[str]:
        if not value:
            return None
        text = str(value).strip().lower()
        if not text:
            return None
        if "x" in text:
            dims = self._parse_size(text)
            if dims:
                return self._resolution_from_dimensions(*dims)
        if text.endswith("p"):
            return text
        try:
            number = int(text)
            if number > 0:
                return f"{number}p"
        except ValueError:
            pass
        return text

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, Tuple[str, bytes, str]]] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> Dict[str, Any]:
        response = self._request(method, path, json=json_payload, data=data, files=files, timeout=timeout)
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
        data: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, Tuple[str, bytes, str]]] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> httpx.Response:
        url = self._build_url(path)
        headers = self._build_headers()
        request_timeout = timeout or self._request_timeout

        try:
            with httpx.Client(timeout=request_timeout) as client:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    data=data,
                    files=files,
                    follow_redirects=True,
                )
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
        if self._project_id:
            headers["OpenAI-Project"] = self._project_id
        if self._beta_header:
            headers["OpenAI-Beta"] = self._beta_header
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
