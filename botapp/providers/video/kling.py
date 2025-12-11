from __future__ import annotations

import logging
import time
from io import BytesIO
from typing import Any, Dict, Iterable, Optional, Tuple

import httpx
from django.conf import settings

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult

logger = logging.getLogger(__name__)


class KlingVideoProvider(BaseVideoProvider):
    """Провайдер генерации Kling через useapi.net."""

    slug = "kling"

    _DEFAULT_BASE_URL = "https://api.useapi.net"
    _TEXT2VIDEO_ENDPOINT = "/v1/kling/videos/text2video"
    _IMAGE2VIDEO_ENDPOINT = "/v1/kling/videos/image2video-frames"
    _TASK_ENDPOINT = "/v1/kling/tasks/{task_id}"
    _TASK_ENDPOINT_FALLBACK = "/v1/tasks/{task_id}"
    _ASSETS_DOWNLOAD_ENDPOINT = "/v1/kling/assets/download"

    _SUCCESS_STATUSES = {"SUCCEED", "SUCCEEDED", "SUCCESS", "DONE", "99"}
    _FAIL_STATUSES = {"FAILED", "ERROR", "CANCELLED", "CANCELED", "REJECTED", "53", "54", "58", "6", "7", "9", "50"}

    def _validate_settings(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "USEAPI_API_KEY", None) or getattr(settings, "KLING_API_KEY", None)
        if not self._api_key:
            raise VideoGenerationError("USEAPI_API_KEY не задан — Kling недоступен.")

        base_url = getattr(settings, "USEAPI_BASE_URL", self._DEFAULT_BASE_URL) or self._DEFAULT_BASE_URL
        self._base_url: str = base_url.rstrip("/")

        self._poll_interval: int = int(
            getattr(settings, "USEAPI_POLL_INTERVAL", getattr(settings, "KLING_POLL_INTERVAL", 5))
        )
        self._poll_timeout: int = int(
            getattr(settings, "USEAPI_POLL_TIMEOUT", getattr(settings, "KLING_POLL_TIMEOUT", 12 * 60))
        )

        raw_timeout = getattr(settings, "USEAPI_REQUEST_TIMEOUT", getattr(settings, "KLING_REQUEST_TIMEOUT", None))
        self._request_timeout = (
            httpx.Timeout(float(raw_timeout), connect=20.0)
            if raw_timeout
            else httpx.Timeout(180.0, connect=20.0)
        )

        max_jobs_raw = (
            getattr(settings, "USEAPI_KLING_MAX_JOBS", None)
            or getattr(settings, "USEAPI_MAX_JOBS", None)
        )
        self._max_jobs: Optional[int] = (
            self._sanitize_max_jobs(max_jobs_raw) if max_jobs_raw is not None else None
        )

        self._account_email: Optional[str] = getattr(settings, "USEAPI_KLING_ACCOUNT_EMAIL", None)
        self._account_password: Optional[str] = getattr(settings, "USEAPI_KLING_ACCOUNT_PASSWORD", None)
        self._account_ready: bool = False

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
        generation_type = (generation_type or "").lower()
        if generation_type == "image2video":
            return self._generate_image_to_video(
                prompt=prompt,
                model_name=model_name,
                params=params,
                input_media=input_media,
                input_mime_type=input_mime_type,
            )
        if generation_type == "text2video":
            return self._generate_text_to_video(
                prompt=prompt,
                model_name=model_name,
                params=params,
            )
        raise VideoGenerationError("Kling поддерживает только режимы text2video и image2video.")

    def _generate_text_to_video(
        self,
        *,
        prompt: str,
        model_name: str,
        params: Dict[str, Any],
    ) -> VideoGenerationResult:
        self._ensure_account_ready()
        payload = self._build_text_payload(prompt=prompt, model_name=model_name, params=params)
        create_response = self._request("POST", self._TEXT2VIDEO_ENDPOINT, json_payload=payload)

        task_id = self._extract_task_id(create_response)
        if not task_id:
            message = self._extract_error_message(create_response) or "useapi не вернул идентификатор задачи."
            raise VideoGenerationError(message)

        task_payload = self._poll_task(task_id)
        self._raise_if_failed(task_payload, task_id)

        video_url = self._extract_download_url(task_payload) or self._extract_video_url(task_payload)
        if not video_url:
            raise VideoGenerationError("Не удалось получить ссылку на видео Kling.")

        video_bytes, mime_type = self._download_file(video_url)
        duration = self._extract_duration(task_payload) or self._sanitize_duration(params.get("duration"))
        aspect_ratio = self._extract_aspect_ratio(task_payload) or params.get("aspect_ratio")

        metadata = {
            "createResponse": create_response,
            "task": task_payload,
            "request": payload,
        }

        return VideoGenerationResult(
            content=video_bytes,
            mime_type=mime_type or "video/mp4",
            duration=int(duration) if isinstance(duration, (int, float)) else None,
            aspect_ratio=str(aspect_ratio) if aspect_ratio else None,
            resolution=self._extract_resolution(task_payload),
            provider_job_id=task_id,
            metadata=metadata,
        )

    def _generate_image_to_video(
        self,
        *,
        prompt: str,
        model_name: str,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> VideoGenerationResult:
        self._ensure_account_ready()

        image_url = self._resolve_image_url(params=params, input_media=input_media, input_mime_type=input_mime_type)
        tail_image_url = self._resolve_tail_image(params=params)
        payload = self._build_image_payload(
            prompt=prompt,
            model_name=model_name,
            params=params,
            image_url=image_url,
            tail_image_url=tail_image_url,
        )

        create_response = self._request("POST", self._IMAGE2VIDEO_ENDPOINT, json_payload=payload)
        task_id = self._extract_task_id(create_response)
        if not task_id:
            message = self._extract_error_message(create_response) or "useapi не вернул идентификатор задачи."
            raise VideoGenerationError(message)

        task_payload = self._poll_task(task_id)
        self._raise_if_failed(task_payload, task_id)

        video_url = self._extract_download_url(task_payload) or self._extract_video_url(task_payload)
        if not video_url:
            raise VideoGenerationError("Не удалось получить ссылку на видео Kling.")

        video_bytes, mime_type = self._download_file(video_url)
        duration = self._extract_duration(task_payload) or self._sanitize_duration(params.get("duration"))

        metadata = {
            "createResponse": create_response,
            "task": task_payload,
            "request": payload,
        }

        return VideoGenerationResult(
            content=video_bytes,
            mime_type=mime_type or "video/mp4",
            duration=int(duration) if isinstance(duration, (int, float)) else None,
            aspect_ratio=self._extract_aspect_ratio(task_payload),
            resolution=self._extract_resolution(task_payload),
            provider_job_id=task_id,
            metadata=metadata,
        )

    def _build_text_payload(self, *, prompt: str, model_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._build_base_payload(prompt=prompt, model_name=model_name, params=params)
        model = payload.get("model_name") or self._normalize_model_name(model_name)

        aspect_ratio = (
            params.get("aspect_ratio")
            or params.get("aspectRatio")
            or params.get("ratio")
        )
        if aspect_ratio:
            payload["aspect_ratio"] = str(aspect_ratio)

        if not (model and model.startswith("kling-v2-")):
            cfg_scale = self._sanitize_cfg(params.get("cfg_scale") or params.get("cfg") or params.get("cfgScale"))
            if cfg_scale is not None:
                payload["cfg_scale"] = cfg_scale

        negative_prompt = params.get("negative_prompt") or params.get("negativePrompt")
        if negative_prompt and not (model and "v2-5" in model):
            payload["negative_prompt"] = negative_prompt

        # enable_audio доступен для text2video (особенно для kling-v2-6)
        enable_audio = params.get("enable_audio")
        if isinstance(enable_audio, bool):
            payload["enable_audio"] = enable_audio

        return payload

    def _build_image_payload(
        self,
        *,
        prompt: str,
        model_name: str,
        params: Dict[str, Any],
        image_url: str,
        tail_image_url: Optional[str],
    ) -> Dict[str, Any]:
        payload = self._build_base_payload(prompt=prompt, model_name=model_name, params=params)
        model = payload.get("model_name") or self._normalize_model_name(model_name)
        payload["image"] = image_url

        if tail_image_url:
            payload["image_tail"] = tail_image_url
            payload["mode"] = "pro"

        if not (model and model.startswith("kling-v2-")):
            cfg_scale = self._sanitize_cfg(params.get("cfg_scale") or params.get("cfg") or params.get("cfgScale"))
            if cfg_scale is not None:
                payload["cfg_scale"] = cfg_scale

        enable_audio = params.get("enable_audio")
        if isinstance(enable_audio, bool):
            payload["enable_audio"] = enable_audio

        return payload

    def _build_base_payload(self, *, prompt: str, model_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "prompt": prompt,
        }

        duration = self._sanitize_duration(params.get("duration") or params.get("seconds"))
        if duration:
            payload["duration"] = str(duration)

        normalized_model = self._normalize_model_name(
            params.get("model_name") or params.get("model") or model_name
        )
        if normalized_model:
            payload["model_name"] = normalized_model

        max_jobs_value = params.get("maxJobs") or params.get("max_jobs") or self._max_jobs
        if max_jobs_value is not None:
            payload["maxJobs"] = self._sanitize_max_jobs(max_jobs_value)

        if self._account_email:
            payload["email"] = self._account_email

        reply_url = params.get("replyUrl") or params.get("reply_url")
        if reply_url:
            payload["replyUrl"] = reply_url
        reply_ref = params.get("replyRef") or params.get("reply_ref")
        if reply_ref:
            payload["replyRef"] = reply_ref

        # mode не поддерживается для kling-v2-1-master и kling-v2-5
        mode = params.get("mode")
        if isinstance(mode, str) and normalized_model not in {"kling-v2-1-master", "kling-v2-5"}:
            normalized_mode = mode.strip().lower()
            if normalized_mode in {"std", "pro"}:
                payload["mode"] = normalized_mode

        return payload

    def _ensure_account_ready(self) -> None:
        if self._account_ready or not (self._account_email and self._account_password):
            return

        payload = {
            "email": self._account_email,
            "password": self._account_password,
        }
        if self._max_jobs is not None:
            payload["maxJobs"] = self._max_jobs

        try:
            self._request("POST", "/v1/kling/accounts", json_payload=payload)
            self._account_ready = True
        except VideoGenerationError as exc:
            logger.warning("Kling account setup via useapi failed: %s", exc)
            time.sleep(2.0)
            self._request("POST", "/v1/kling/accounts", json_payload=payload)
            self._account_ready = True

    def _poll_task(self, task_id: str) -> Dict[str, Any]:
        deadline = time.time() + self._poll_timeout
        last_payload: Dict[str, Any] = {}

        while time.time() < deadline:
            try:
                last_payload = self._fetch_task_payload(task_id)
            except VideoGenerationError as exc:
                message = str(exc)
                if "404" in message or "ResourceNotFound" in message:
                    time.sleep(self._poll_interval)
                    continue
                raise
            status, is_final = self._extract_status(last_payload)
            if status in self._SUCCESS_STATUSES or (is_final and status not in self._FAIL_STATUSES):
                return last_payload
            if status in self._FAIL_STATUSES or (is_final and status not in self._SUCCESS_STATUSES):
                return last_payload
            time.sleep(self._poll_interval)

        raise VideoGenerationError(f"useapi: ожидание результата Kling превысило {self._poll_timeout} секунд.")

    def _fetch_task_payload(self, task_id: str) -> Dict[str, Any]:
        """
        В новых доках useapi статус задач Kling доступен по /v1/tasks/{task_id},
        но для обратной совместимости пробуем и старый путь /v1/kling/tasks/{task_id}.
        """
        endpoints = (
            self._TASK_ENDPOINT.format(task_id=task_id),
            self._TASK_ENDPOINT_FALLBACK.format(task_id=task_id),
        )
        last_error: Optional[VideoGenerationError] = None
        for endpoint in endpoints:
            try:
                return self._request(
                    "GET",
                    endpoint,
                    params=self._task_params(),
                )
            except VideoGenerationError as exc:
                last_error = exc
                message = str(exc)
                if "404" in message or "ResourceNotFound" in message:
                    continue
                raise
        if last_error:
            raise last_error
        raise VideoGenerationError("useapi Kling: не удалось получить статус задачи.")

    def _raise_if_failed(self, payload: Dict[str, Any], task_id: str) -> None:
        status, status_final = self._extract_status(payload)
        if status in self._FAIL_STATUSES or (status_final and status not in self._SUCCESS_STATUSES):
            message = self._extract_error_message(payload) or status or "Задача завершилась с ошибкой."
            logger.warning("Kling task %s failed: %s", task_id, message)
            raise VideoGenerationError(f"Kling: {message}")

    def _extract_download_url(self, payload: Dict[str, Any]) -> Optional[str]:
        work_id = self._extract_first_work_id(payload)
        if not work_id:
            return None

        # ВАЖНО: fileTypes=MP4 нужен чтобы получить mp4 файл, а не zip архив
        params: Dict[str, Any] = {
            "workIds": str(work_id),
            "fileTypes": "MP4",
        }
        if self._account_email:
            params["email"] = self._account_email

        try:
            response = self._request("GET", self._ASSETS_DOWNLOAD_ENDPOINT, params=params)
        except VideoGenerationError as exc:
            logger.info("Kling assets download fallback failed: %s", exc)
            return None

        cdn_url = response.get("cdnUrl") or response.get("cdn_url")
        if isinstance(cdn_url, str) and cdn_url.startswith("http"):
            return cdn_url
        return None

    def _extract_video_url(self, payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None

        direct_candidates = [
            payload.get("cdnUrl"),
            payload.get("cdn_url"),
            payload.get("url"),
            payload.get("videoUrl"),
        ]
        for candidate in direct_candidates:
            if isinstance(candidate, str) and candidate.startswith("http"):
                return candidate

        for work in self._collect_works(payload):
            resource = work.get("resource") if isinstance(work, dict) else None
            if isinstance(resource, dict):
                for key in ("resource", "url", "cdnUrl", "downloadUrl"):
                    value = resource.get(key)
                    if isinstance(value, str) and value.startswith("http"):
                        return value
            if isinstance(work, dict):
                for key in ("url", "cdnUrl", "downloadUrl", "videoUrl"):
                    value = work.get(key)
                    if isinstance(value, str) and value.startswith("http"):
                        return value

        task = payload.get("task")
        if isinstance(task, dict):
            resource = task.get("resource")
            if isinstance(resource, dict):
                for key in ("resource", "url", "cdnUrl"):
                    value = resource.get(key)
                    if isinstance(value, str) and value.startswith("http"):
                        return value

        return None

    def _extract_duration(self, payload: Dict[str, Any]) -> Optional[int]:
        # Сначала проверяем arguments - там duration в секундах
        arguments = self._extract_arguments_map(payload)
        for key in ("duration", "seconds"):
            if key in arguments:
                try:
                    return int(float(arguments[key]))
                except (TypeError, ValueError):
                    continue
        # Fallback: resource.duration в миллисекундах - конвертируем в секунды
        for work in self._collect_works(payload):
            if not isinstance(work, dict):
                continue
            resource = work.get("resource")
            if isinstance(resource, dict):
                duration_value = resource.get("duration")
                if isinstance(duration_value, (int, float)) and duration_value > 0:
                    # Kling API возвращает duration в миллисекундах
                    return int(duration_value / 1000)
        return None

    def _extract_aspect_ratio(self, payload: Dict[str, Any]) -> Optional[str]:
        arguments = self._extract_arguments_map(payload)
        for key in ("aspect_ratio", "aspectRatio", "ratio"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_resolution(self, payload: Dict[str, Any]) -> Optional[str]:
        for work in self._collect_works(payload):
            if not isinstance(work, dict):
                continue
            resource = work.get("resource")
            if isinstance(resource, dict):
                width = resource.get("width")
                height = resource.get("height")
                if isinstance(width, (int, float)) and isinstance(height, (int, float)):
                    return f"{int(width)}x{int(height)}"
        return None

    def _extract_arguments_map(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        info: Optional[Dict[str, Any]] = None

        task = payload.get("task") if isinstance(payload, dict) else None
        if isinstance(task, dict):
            info = task.get("taskInfo") or task.get("task_info")

        if not info:
            for work in self._collect_works(payload):
                if isinstance(work, dict):
                    info = work.get("taskInfo") or work.get("task_info")
                    if info:
                        break

        arguments = info.get("arguments") if isinstance(info, dict) else []
        result: Dict[str, Any] = {}
        if isinstance(arguments, Iterable):
            for item in arguments:
                if isinstance(item, dict):
                    name = item.get("name")
                    value = item.get("value")
                    if isinstance(name, str):
                        result[name] = value
        return result

    def _extract_task_id(self, payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        if payload.get("taskId"):
            return str(payload["taskId"])

        task = payload.get("task")
        if isinstance(task, dict):
            for key in ("id", "taskId", "task_id"):
                if task.get(key):
                    return str(task[key])

        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("id", "taskId", "task_id"):
                if data.get(key):
                    return str(data[key])

        return None

    def _extract_status(self, payload: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        status_final = False
        status_value: Optional[str] = None

        if isinstance(payload, dict):
            status_value = payload.get("status_name") or payload.get("status") or payload.get("state")
            status_final = bool(payload.get("status_final") or payload.get("statusFinal"))

            task = payload.get("task")
            if isinstance(task, dict):
                status_value = status_value or task.get("status_name") or task.get("status") or task.get("state")
                status_final = status_final or bool(task.get("status_final") or task.get("statusFinal"))

            works = self._collect_works(payload)
            if works:
                work = works[0]
                if isinstance(work, dict):
                    status_value = status_value or work.get("status_name") or work.get("status")
                    status_final = status_final or bool(work.get("status_final") or work.get("statusFinal"))

        return self._normalize_status(status_value), status_final

    def _extract_error_message(self, payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None

        for key in ("message", "error", "detail", "failMsg", "fail_message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        task = payload.get("task")
        if isinstance(task, dict):
            for key in ("message", "error", "detail", "failMsg", "fail_message"):
                value = task.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        for work in self._collect_works(payload):
            if isinstance(work, dict):
                for key in ("message", "error", "detail", "failMsg", "fail_message"):
                    value = work.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return None

    def _collect_works(self, payload: Dict[str, Any]) -> list:
        works = []
        if isinstance(payload, dict):
            if isinstance(payload.get("works"), list):
                works.extend(payload["works"])
            history = payload.get("history")
            if isinstance(history, list):
                for item in history:
                    if isinstance(item, dict) and isinstance(item.get("works"), list):
                        works.extend(item["works"])
        return works

    def _extract_first_work_id(self, payload: Dict[str, Any]) -> Optional[str]:
        for work in self._collect_works(payload):
            if isinstance(work, dict):
                for key in ("workId", "work_id", "id"):
                    if work.get(key):
                        return str(work[key])
        return None

    def _resolve_image_url(
        self,
        *,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> str:
        # Если передан URL изображения - проверяем его
        raw_url = params.get("image_url") or params.get("imageUrl") or params.get("reference_image")
        if raw_url:
            url_str = str(raw_url)
            # Если URL уже с домена Kling - используем как есть
            if self._is_useapi_asset(url_str):
                return url_str
            # Иначе скачиваем и загружаем через Kling assets API
            # (Kling API не может получить доступ к внешним URL напрямую)
            image_bytes, mime = self._download_raw(url_str)
            return self._upload_image_asset(
                image_bytes,
                mime_type=mime or input_mime_type,
                file_name="reference_image.png",
            )

        # Если передан бинарный контент - загружаем через Kling assets API
        if input_media:
            return self._upload_image_asset(
                input_media,
                mime_type=input_mime_type,
                file_name="input_image.png",
            )

        raise VideoGenerationError("Для режима image2video необходимо загрузить изображение.")

    def _resolve_tail_image(self, *, params: Dict[str, Any]) -> Optional[str]:
        tail_image = params.get("image_tail") or params.get("tail_image") or params.get("imageTail")
        if not tail_image:
            return None
        return str(tail_image)

    def _download_file(self, url: str) -> Tuple[bytes, Optional[str]]:
        try:
            with httpx.Client(timeout=self._request_timeout, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:  # type: ignore[attr-defined]
            raise VideoGenerationError(f"Не удалось скачать видео Kling: {exc}") from exc
        # Kling всегда возвращает mp4, но CDN может отдавать неправильный Content-Type
        # Принудительно используем video/mp4 для корректного сохранения
        return response.content, "video/mp4"

    def _download_raw(self, url: str) -> Tuple[bytes, Optional[str]]:
        try:
            with httpx.Client(timeout=self._request_timeout, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:  # type: ignore[attr-defined]
            raise VideoGenerationError(f"Не удалось скачать изображение Kling: {exc}") from exc
        return response.content, response.headers.get("Content-Type")

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = self._resolve_url(endpoint)
        try:
            with httpx.Client(timeout=self._request_timeout, follow_redirects=True) as client:
                response = client.request(
                    method,
                    url,
                    headers=self._build_headers(),
                    json=json_payload,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict):
                    return data
                raise VideoGenerationError(f"useapi вернул не-JSON объект: {data}")
        except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
            detail = self._safe_extract_error(exc.response)
            raise VideoGenerationError(f"useapi Kling HTTP {exc.response.status_code if exc.response else ''}: {detail}") from exc
        except httpx.HTTPError as exc:  # type: ignore[attr-defined]
            raise VideoGenerationError(f"Ошибка запроса к useapi Kling: {exc}") from exc

    def _resolve_url(self, endpoint: str) -> str:
        if endpoint.startswith("http"):
            return endpoint
        base_url = self._base_url
        if base_url.endswith("/v1") and endpoint.startswith("/v1/"):
            base_url = base_url[:-3]
        return f"{base_url}{endpoint}"

    def _upload_image_asset(self, content: bytes, *, mime_type: Optional[str], file_name: str) -> str:
        """Загружает изображение в Kling через useapi assets API."""
        # Лимит Kling: 10MB для изображений
        max_size = 10 * 1024 * 1024  # 10MB

        # Если изображение больше лимита - сжимаем в JPEG
        if len(content) > max_size:
            content, mime_type = self._compress_image(content, max_size)

        mime = (mime_type or "image/png").split(";")[0].strip() or "image/png"
        if not mime.startswith("image/"):
            mime = "image/png"

        url = self._resolve_url("/v1/kling/assets/")
        # Согласно документации useapi Kling assets - только email в query params
        params: Dict[str, Any] = {}
        if self._account_email:
            params["email"] = self._account_email

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": mime,
        }

        try:
            with httpx.Client(timeout=self._request_timeout, follow_redirects=True) as client:
                response = client.post(url, headers=headers, params=params, content=content)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
            detail = self._safe_extract_error(exc.response)
            raise VideoGenerationError(f"useapi Kling HTTP {exc.response.status_code if exc.response else ''}: {detail}") from exc
        except httpx.HTTPError as exc:  # type: ignore[attr-defined]
            raise VideoGenerationError(f"Ошибка запроса к useapi Kling: {exc}") from exc
        except Exception as exc:
            raise VideoGenerationError(f"Не удалось загрузить ассет в Kling: {exc}") from exc

        asset_url = None
        if isinstance(data, dict):
            asset_url = data.get("url") or data.get("resourceUrl") or data.get("resource_url")
        if not (isinstance(asset_url, str) and asset_url.startswith("http")):
            raise VideoGenerationError(f"useapi не вернул ссылку на ассет Kling: {data}")
        return asset_url

    def _compress_image(self, content: bytes, max_size: int) -> Tuple[bytes, str]:
        """Сжимает изображение до указанного размера."""
        try:
            from PIL import Image
        except ImportError:
            logger.warning("PIL не установлен, сжатие изображения невозможно")
            return content, "image/png"

        try:
            img = Image.open(BytesIO(content))
            # Конвертируем в RGB если нужно (для JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Пробуем разные уровни качества
            for quality in [85, 70, 50, 30]:
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                compressed = buffer.getvalue()
                if len(compressed) <= max_size:
                    logger.info(f"Изображение сжато: {len(content)} -> {len(compressed)} байт (quality={quality})")
                    return compressed, "image/jpeg"

            # Если всё ещё большое - уменьшаем размер
            width, height = img.size
            while len(compressed) > max_size and width > 300 and height > 300:
                width = int(width * 0.8)
                height = int(height * 0.8)
                resized = img.resize((width, height), Image.Resampling.LANCZOS)
                buffer = BytesIO()
                resized.save(buffer, format="JPEG", quality=70, optimize=True)
                compressed = buffer.getvalue()

            logger.info(f"Изображение сжато с ресайзом: {len(content)} -> {len(compressed)} байт")
            return compressed, "image/jpeg"
        except Exception as exc:
            logger.warning(f"Ошибка сжатия изображения: {exc}")
            return content, "image/png"

    @staticmethod
    def _is_useapi_asset(url: str) -> bool:
        lower = url.lower()
        return "useapi.net" in lower or "klingai.com" in lower

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _task_params(self) -> Optional[Dict[str, Any]]:
        if self._account_email:
            return {"email": self._account_email}
        return None

    @staticmethod
    def _safe_extract_error(response: Optional[httpx.Response]) -> str:
        if not response:
            return ""
        try:
            data = response.json()
            if isinstance(data, dict):
                # Извлекаем читаемое сообщение из известных полей
                for key in ("message", "error", "detail", "failMsg", "fail_message", "reason"):
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                # Проверяем вложенный объект error
                error_obj = data.get("error")
                if isinstance(error_obj, dict):
                    for key in ("message", "detail", "reason"):
                        value = error_obj.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
                # Fallback - весь JSON если ничего не нашли
                return str(data)
        except Exception:
            pass
        return response.text or ""

    @staticmethod
    def _convert_to_png(content: bytes, input_mime_type: Optional[str]) -> bytes:
        mime = (input_mime_type or "").lower()
        if mime == "image/png":
            return content
        try:
            from PIL import Image
        except ImportError:
            return content
        try:
            with Image.open(BytesIO(content)) as img:
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                return buffer.getvalue()
        except Exception:
            return content

    @staticmethod
    def _sanitize_duration(value: Any) -> int:
        try:
            ivalue = int(float(value))
        except Exception:
            ivalue = 5
        return 10 if ivalue >= 10 else 5

    @staticmethod
    def _sanitize_max_jobs(value: Any) -> int:
        try:
            jobs = int(value)
        except (TypeError, ValueError):
            jobs = 5
        if jobs < 1:
            jobs = 1
        if jobs > 50:
            jobs = 50
        return jobs

    @staticmethod
    def _sanitize_cfg(value: Any) -> Optional[float]:
        try:
            cfg = float(value)
        except (TypeError, ValueError):
            return None
        cfg = max(0.0, min(1.0, cfg))
        return round(cfg, 2)

    @staticmethod
    def _normalize_status(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return str(int(value))
        if isinstance(value, str):
            return value.strip().upper()
        return str(value)

    @staticmethod
    def _normalize_model_name(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        value = str(raw).strip().lower().replace("_", "-")
        if "v2-6" in value:
            return "kling-v2-6"
        if "v2-5" in value:
            return "kling-v2-5"
        if "v2-1" in value and "master" in value:
            return "kling-v2-1-master"
        if "v2-1" in value:
            return "kling-v2-1"
        if "v1-6" in value:
            return "kling-v1-6"
        if "v1-5" in value:
            return "kling-v1-5"
        if value.startswith("kling"):
            return value
        return f"kling-{value}"


register_video_provider(KlingVideoProvider.slug, KlingVideoProvider)
