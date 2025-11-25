from __future__ import annotations

import base64
from io import BytesIO
import json
import threading
import time
from typing import Any, Dict, Iterable, Optional

import httpx
import jwt
from django.conf import settings

from botapp.services import supabase_upload_png

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult


class KlingVideoProvider(BaseVideoProvider):
    """Провайдер генерации видео через Kling."""

    slug = "kling"

    _DEFAULT_BASE_URL = "https://api-singapore.klingai.com"
    _DEFAULT_TEXT2VIDEO_ENDPOINT = "/v1/videos/text2video"
    _DEFAULT_IMAGE2VIDEO_ENDPOINT = "/v1/videos/image2video"
    _DEFAULT_TEXT2VIDEO_STATUS_ENDPOINT = "/v1/videos/text2video/{task_id}"
    _DEFAULT_IMAGE2VIDEO_STATUS_ENDPOINT = "/v1/videos/image2video/{task_id}"
    _DEFAULT_POLL_INTERVAL = 5  # seconds
    _DEFAULT_POLL_TIMEOUT = 12 * 60  # seconds
    _DEFAULT_TIMEOUT = httpx.Timeout(180.0, connect=30.0)

    _SUCCESS_STATUSES = {"success", "succeeded", "completed", "done", "finished", "succeed"}
    _FAIL_STATUSES = {"error", "failed", "canceled", "cancelled", "rejected", "timeout"}

    _EXCLUDE_PARAM_KEYS = {
        "input_image_file_id",
        "input_image_mime_type",
        "telegram_file_id",
        "parent_request_id",
        "extend_parent_request_id",
    }

    def _validate_settings(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "KLING_API_KEY", None)
        if not self._api_key:
            raise VideoGenerationError("KLING_API_KEY не задан — Kling недоступен.")

        self._api_secret: Optional[str] = getattr(settings, "KLING_API_SECRET", None)
        self._organization_id: Optional[str] = getattr(settings, "KLING_ORGANIZATION_ID", None)
        if self._api_secret:
            self._api_secret = str(self._api_secret)
        self._token_lock = threading.Lock()
        self._cached_token: Optional[str] = None
        self._token_exp: float = 0.0

        self._kie_api_key: Optional[str] = getattr(settings, "KIE_API_KEY", None)
        self._use_kie = bool(self._kie_api_key)

        base = getattr(settings, "KLING_API_BASE_URL", self._DEFAULT_BASE_URL) or self._DEFAULT_BASE_URL
        self._api_base = base.rstrip("/")

        text2video_endpoint = self._clean_endpoint(getattr(settings, "KLING_TEXT2VIDEO_ENDPOINT", None))
        create_override = self._clean_endpoint(getattr(settings, "KLING_CREATE_ENDPOINT", None))
        if not text2video_endpoint:
            if create_override and create_override != "/v1/video/generations":
                text2video_endpoint = create_override
            else:
                text2video_endpoint = self._DEFAULT_TEXT2VIDEO_ENDPOINT
        self._text2video_endpoint: str = text2video_endpoint

        image2video_endpoint = self._clean_endpoint(getattr(settings, "KLING_IMAGE2VIDEO_ENDPOINT", None))
        if not image2video_endpoint:
            image2video_endpoint = self._DEFAULT_IMAGE2VIDEO_ENDPOINT
        self._image2video_endpoint: str = image2video_endpoint

        text2video_status = self._clean_endpoint(getattr(settings, "KLING_TEXT2VIDEO_STATUS_ENDPOINT", None))
        status_override = self._clean_endpoint(getattr(settings, "KLING_STATUS_ENDPOINT", None))
        if not text2video_status:
            if status_override and status_override not in {"/v1/video/generations/{job_id}", "/v1/video/generations/{task_id}"}:
                text2video_status = status_override
            else:
                text2video_status = self._DEFAULT_TEXT2VIDEO_STATUS_ENDPOINT
        self._text2video_status_endpoint: str = text2video_status

        image2video_status = self._clean_endpoint(getattr(settings, "KLING_IMAGE2VIDEO_STATUS_ENDPOINT", None))
        if not image2video_status:
            image2video_status = self._DEFAULT_IMAGE2VIDEO_STATUS_ENDPOINT
        self._image2video_status_endpoint: str = image2video_status

        self._poll_interval: int = int(getattr(settings, "KLING_POLL_INTERVAL", self._DEFAULT_POLL_INTERVAL))
        self._poll_timeout: int = int(getattr(settings, "KLING_POLL_TIMEOUT", self._DEFAULT_POLL_TIMEOUT))

        timeout_value = getattr(settings, "KLING_REQUEST_TIMEOUT", None)
        if timeout_value:
            self._request_timeout = httpx.Timeout(float(timeout_value), connect=30.0)
        else:
            self._request_timeout = self._DEFAULT_TIMEOUT

        raw_extra_headers = getattr(settings, "KLING_EXTRA_HEADERS", None)
        self._extra_headers: Dict[str, str] = {}
        if raw_extra_headers:
            parsed: Any = raw_extra_headers
            if isinstance(raw_extra_headers, str):
                try:
                    parsed = json.loads(raw_extra_headers)
                except json.JSONDecodeError:
                    parsed = {}
            if isinstance(parsed, dict):
                self._extra_headers = {str(k): str(v) for k, v in parsed.items()}

        if self._use_kie:
            base_url = getattr(settings, "KIE_API_BASE_URL", "https://api.kie.ai") or "https://api.kie.ai"
            self._kie_base_url = base_url.rstrip("/")
            self._kie_text2video_model: Optional[str] = getattr(settings, "KIE_TEXT2VIDEO_MODEL", None)
            self._kie_image2video_model: Optional[str] = getattr(settings, "KIE_IMAGE2VIDEO_MODEL", None)
            self._kie_poll_interval: int = int(getattr(settings, "KIE_POLL_INTERVAL", self._poll_interval))
            self._kie_poll_timeout: int = int(getattr(settings, "KIE_POLL_TIMEOUT", str(self._poll_timeout)))
            kie_timeout_raw = getattr(settings, "KIE_REQUEST_TIMEOUT", None)
            self._kie_request_timeout = httpx.Timeout(float(kie_timeout_raw), connect=10.0) if kie_timeout_raw else httpx.Timeout(120.0, connect=10.0)

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
        if generation_type not in {"text2video", "image2video"}:
            raise VideoGenerationError(f"Режим '{generation_type}' не поддерживается Kling.")

        if self._use_kie:
            return self._generate_via_kie(
                prompt=prompt,
                model_name=model_name,
                generation_type=generation_type,
                params=params,
                input_media=input_media,
                input_mime_type=input_mime_type,
            )

        if generation_type == "image2video" and not (input_media or params.get("image")):
            raise VideoGenerationError("Для режима image2video необходимо загрузить изображение или ссылку на него.")

        return self._generate_via_native_kling(
            prompt=prompt,
            model_name=model_name,
            generation_type=generation_type,
            params=params,
            input_media=input_media,
            input_mime_type=input_mime_type,
        )

    @staticmethod
    def _clean_endpoint(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    def _generate_via_native_kling(
        self,
        *,
        prompt: str,
        model_name: str,
        generation_type: str,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> VideoGenerationResult:
        endpoints = self._resolve_endpoints(generation_type)

        payload = self._build_payload(
            prompt=prompt,
            model_name=model_name,
            generation_type=generation_type,
            params=params,
            input_media=input_media,
            input_mime_type=input_mime_type,
        )

        initial_response = self._request("POST", endpoints["create"], json_payload=payload)
        job_id = self._extract_job_id(initial_response)
        if not job_id:
            raise VideoGenerationError("Kling API не вернул идентификатор задания.")

        job_status = self._extract_status(initial_response)
        job_payload = (
            initial_response
            if job_status in self._SUCCESS_STATUSES
            else self._poll_job(job_id, endpoints["status"])
        )

        video_bytes, mime_type = self._extract_video_content(job_payload)
        if not video_bytes:
            raise VideoGenerationError("Kling API не вернул ссылку или данные видео.")

        duration = self._extract_first_number(job_payload, ("duration", "video_duration", "seconds"))
        resolution = self._extract_first_string(job_payload, ("resolution", "video_resolution"))
        aspect_ratio = self._extract_first_string(job_payload, ("aspect_ratio", "ratio"))

        metadata = {
            "job": job_payload,
            "initialResponse": initial_response,
            "prompt": prompt,
            "generationType": generation_type,
        }

        return VideoGenerationResult(
            content=video_bytes,
            mime_type=mime_type or "video/mp4",
            duration=int(duration) if isinstance(duration, (int, float)) else None,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            provider_job_id=job_id,
            metadata=metadata,
        )

    def _generate_via_kie(
        self,
        *,
        prompt: str,
        model_name: str,
        generation_type: str,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> VideoGenerationResult:
        model_override = (
            self._kie_text2video_model if generation_type == "text2video" else self._kie_image2video_model
        )
        target_model = model_override or model_name
        if not target_model:
            raise VideoGenerationError("Не удалось определить модель для KIE.AI.")

        input_payload = self._build_kie_input(
            generation_type=generation_type,
            prompt=prompt,
            params=params,
            input_media=input_media,
            input_mime_type=input_mime_type,
        )

        request_payload = {
            "model": target_model,
            "input": input_payload,
        }

        create_resp = self._kie_request("POST", "/api/v1/jobs/createTask", json_payload=request_payload)
        if create_resp.get("code") != 200:
            raise VideoGenerationError(f"KIE.AI createTask error: {create_resp}")
        data = create_resp.get("data") or {}
        task_id = data.get("taskId")
        if not task_id:
            raise VideoGenerationError("KIE.AI не вернул идентификатор задания.")

        job_payload = self._kie_poll_task(task_id)
        result_url = self._extract_kie_result_url(job_payload)
        if not result_url:
            raise VideoGenerationError("KIE.AI не вернул ссылку на результат.")

        video_bytes, mime_type = self._download_file(result_url)
        duration_value = input_payload.get("duration")
        metadata = {
            "job": job_payload,
            "initialResponse": create_resp,
            "prompt": prompt,
            "generationType": generation_type,
            "provider": "kie.ai",
        }

        return VideoGenerationResult(
            content=video_bytes,
            mime_type=mime_type or "video/mp4",
            duration=int(duration_value) if duration_value and str(duration_value).isdigit() else None,
            resolution=None,
            aspect_ratio=None,
            provider_job_id=task_id,
            metadata=metadata,
        )

    def _build_kie_input(
        self,
        *,
        generation_type: str,
        prompt: str,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> Dict[str, Any]:
        effective_params = dict(params or {})
        payload: Dict[str, Any] = {
            "prompt": prompt,
        }

        duration_value = effective_params.get("duration")
        if duration_value is not None:
            payload["duration"] = str(duration_value)

        negative_prompt = effective_params.get("negative_prompt") or effective_params.get("negativePrompt")
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        cfg_scale = effective_params.get("cfg_scale")
        if cfg_scale is not None:
            try:
                payload["cfg_scale"] = float(cfg_scale)
            except (TypeError, ValueError):
                pass

        aspect_ratio = (
            effective_params.get("aspect_ratio")
            or effective_params.get("aspectRatio")
        )
        if aspect_ratio:
            payload["aspect_ratio"] = str(aspect_ratio)

        kling_opts = effective_params.get("kling_options")
        if isinstance(kling_opts, dict):
            payload.update(kling_opts)

        if generation_type == "image2video":
            image_url = (
                effective_params.get("image_url")
                or effective_params.get("imageUrl")
                or effective_params.get("reference_image")
            )
            if not image_url:
                image_url = self._ensure_image_url(input_media, input_mime_type)
            payload["image_url"] = image_url

        return payload

    def _ensure_image_url(self, input_media: Optional[bytes], input_mime_type: Optional[str]) -> str:
        if not input_media:
            raise VideoGenerationError("Для режима image2video необходимо загрузить изображение.")

        png_bytes = self._convert_to_png(input_media, input_mime_type)
        upload_obj = supabase_upload_png(png_bytes)
        if isinstance(upload_obj, dict):
            url = upload_obj.get("public_url") or upload_obj.get("publicUrl") or upload_obj.get("publicURL")
        else:
            url = upload_obj

        if not url:
            raise VideoGenerationError("Не удалось загрузить изображение в хранилище для KIE.AI.")
        return url

    @staticmethod
    def _convert_to_png(content: bytes, input_mime_type: Optional[str]) -> bytes:
        mime = (input_mime_type or "").lower()
        if mime == "image/png":
            return content
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover - Pillow всегда в зависимостях, но на всякий случай
            return content
        try:
            with Image.open(BytesIO(content)) as img:
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                return buffer.getvalue()
        except Exception:
            return content

    def _kie_request(
        self,
        method: str,
        endpoint: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._kie_api_key:
            raise VideoGenerationError("KIE.AI API ключ не задан.")
        url = endpoint
        if not endpoint.startswith("http"):
            url = f"{self._kie_base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self._kie_api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._kie_request_timeout, follow_redirects=True) as client:
                response = client.request(method, url, headers=headers, json=json_payload, params=params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
            detail = self._safe_extract_error(exc.response)
            raise VideoGenerationError(f"KIE.AI error: {exc}\nDetails: {detail}") from exc
        except httpx.HTTPError as exc:  # type: ignore[attr-defined]
            raise VideoGenerationError(f"Ошибка обращения к KIE.AI API: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover
            raise VideoGenerationError(f"KIE.AI вернул некорректный JSON: {response.text}") from exc

    def _kie_poll_task(self, task_id: str) -> Dict[str, Any]:
        started = time.monotonic()
        while True:
            response = self._kie_request(
                "GET",
                "/api/v1/jobs/recordInfo",
                params={"taskId": task_id},
            )
            if response.get("code") != 200:
                raise VideoGenerationError(f"KIE.AI recordInfo error: {response}")
            data = response.get("data") or {}
            state = (data.get("state") or "").lower()
            if state == "success":
                return data
            if state == "fail":
                fail_msg = data.get("failMsg") or data.get("msg") or "KIE.AI task failed."
                raise VideoGenerationError(f"Задача KIE.AI завершилась с ошибкой: {fail_msg}")
            if time.monotonic() - started > self._kie_poll_timeout:
                raise VideoGenerationError("Ожидание результата KIE.AI превысило установленный таймаут.")
            time.sleep(self._kie_poll_interval)

    @staticmethod
    def _extract_kie_result_url(payload: Dict[str, Any]) -> Optional[str]:
        result_json = payload.get("resultJson")
        if isinstance(result_json, dict):
            urls = result_json.get("resultUrls")
            if isinstance(urls, list) and urls:
                return urls[0]
        if isinstance(result_json, str):
            try:
                parsed = json.loads(result_json)
                urls = parsed.get("resultUrls")
                if isinstance(urls, list) and urls:
                    return urls[0]
            except json.JSONDecodeError:
                pass
        return None

    def _resolve_endpoints(self, generation_type: str) -> Dict[str, str]:
        if generation_type == "text2video":
            return {
                "create": self._text2video_endpoint,
                "status": self._text2video_status_endpoint,
            }
        return {
            "create": self._image2video_endpoint,
            "status": self._image2video_status_endpoint,
        }

    def _generate_jwt(self) -> str:
        if not self._api_secret:
            return self._api_key
        now = time.time()
        with self._token_lock:
            if self._cached_token and now < self._token_exp - 5:
                return self._cached_token
            headers = {"alg": "HS256", "typ": "JWT"}
            payload = {
                "iss": self._api_key,
                "exp": int(now) + 1800,
                "nbf": int(now) - 5,
            }
            token = jwt.encode(payload, self._api_secret, headers=headers)
            if isinstance(token, bytes):
                token = token.decode("utf-8")
            self._cached_token = token
            self._token_exp = payload["exp"]
            return token

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
        payload: Dict[str, Any] = {
            "prompt": prompt,
        }

        effective_params = dict(params or {})
        kling_specific = effective_params.pop("kling_options", None)

        for key in list(effective_params.keys()):
            if key in self._EXCLUDE_PARAM_KEYS:
                effective_params.pop(key, None)

        if kling_specific and isinstance(kling_specific, dict):
            effective_params.update(kling_specific)

        provided_model_name = effective_params.pop("model_name", None) or effective_params.pop("model", None)
        if not provided_model_name and model_name:
            provided_model_name = model_name
        if provided_model_name:
            payload["model_name"] = provided_model_name

        provided_mode = effective_params.pop("mode", None)
        if provided_mode and provided_mode not in {"text2video", "image2video"}:
            payload["mode"] = provided_mode

        if generation_type == "image2video":
            image_value = effective_params.pop("image", None)
            if image_value:
                payload["image"] = image_value
            elif input_media:
                payload["image"] = base64.b64encode(input_media).decode("utf-8")
            else:
                raise VideoGenerationError("Для режима image2video необходимо загрузить изображение.")
        else:
            if not prompt:
                raise VideoGenerationError("Для режима text2video требуется текстовый промт.")

        duration_value = effective_params.pop("duration", None)
        if duration_value is not None:
            payload["duration"] = str(duration_value)

        aspect_ratio = effective_params.pop("aspect_ratio", None)
        if aspect_ratio is not None:
            payload["aspect_ratio"] = str(aspect_ratio)

        for key, value in list(effective_params.items()):
            if value is None:
                effective_params.pop(key)

        payload.update(effective_params)

        return payload

    def _poll_job(self, job_id: str, status_endpoint: str) -> Dict[str, Any]:
        started = time.monotonic()
        while True:
            job_response = self._request(
                "GET",
                status_endpoint,
                path_params={"job_id": job_id, "task_id": job_id},
            )
            status = self._extract_status(job_response)
            if status in self._SUCCESS_STATUSES:
                return job_response
            if status in self._FAIL_STATUSES:
                raise VideoGenerationError(self._extract_error_message(job_response, job_id))
            if time.monotonic() - started > self._poll_timeout:
                raise VideoGenerationError(f"Ожидание результата Kling превысило {self._poll_timeout} секунд.")
            time.sleep(self._poll_interval)

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        path_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = self._resolve_url(endpoint, path_params=path_params)
        headers = self._build_headers()
        try:
            with httpx.Client(timeout=self._request_timeout, follow_redirects=True) as client:
                response = client.request(method, url, headers=headers, json=json_payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
            detail = self._safe_extract_error(exc.response)
            raise VideoGenerationError(f"Kling API error: {exc}\nDetails: {detail}") from exc
        except httpx.HTTPError as exc:  # type: ignore[attr-defined]
            raise VideoGenerationError(f"Ошибка обращения к Kling API: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - зависит от внешнего API
            raise VideoGenerationError(f"Кинг вернул некорректный JSON: {response.text}") from exc

    def _build_headers(self) -> Dict[str, str]:
        token = self._generate_jwt() if self._api_secret else self._api_key
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-API-Key": self._api_key,
        }
        if self._api_secret:
            headers["X-API-Secret"] = self._api_secret
        if self._organization_id:
            headers["X-Kling-Org"] = self._organization_id
        if self._extra_headers:
            headers.update(self._extra_headers)
        return headers

    def _resolve_url(self, endpoint: str, *, path_params: Optional[Dict[str, str]] = None) -> str:
        url = endpoint
        if not endpoint.startswith("http"):
            url = f"{self._api_base}{endpoint}"
        if path_params:
            for key, value in path_params.items():
                url = url.replace(f"{{{key}}}", value)
        return url

    def _extract_job_id(self, payload: Dict[str, Any]) -> Optional[str]:
        job = self._unwrap_job(payload)
        for key in ("id", "job_id", "task_id", "request_id"):
            value = job.get(key) or payload.get(key)
            if value:
                return str(value)
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("id", "job_id", "task_id"):
                if data.get(key):
                    return str(data[key])
        return None

    def _extract_status(self, payload: Dict[str, Any]) -> Optional[str]:
        job = self._unwrap_job(payload)
        for key in ("status", "state", "job_status", "task_status"):
            value = job.get(key) or payload.get(key)
            if isinstance(value, str):
                return value.lower()
        return None

    @staticmethod
    def _unwrap_job(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        for key in ("data", "result", "job", "task"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
        return payload

    def _extract_error_message(self, payload: Dict[str, Any], job_id: str) -> str:
        message = self._extract_first_string(
            payload,
            ("error_message", "error", "detail", "message"),
        )
        if message:
            return f"Kling отклонил задачу {job_id}: {message}"
        return f"Kling завершил задачу {job_id} со статусом ошибки."

    def _extract_video_content(self, payload: Dict[str, Any]) -> tuple[Optional[bytes], Optional[str]]:
        job = self._unwrap_job(payload)

        task_result = job.get("task_result") if isinstance(job, dict) else None
        if isinstance(task_result, dict):
            videos = task_result.get("videos")
            if isinstance(videos, list) and videos:
                first_video = videos[0]
                if isinstance(first_video, dict):
                    url = first_video.get("url")
                    if url:
                        return self._download_file(url)
                    encoded_video = first_video.get("video_base64") or first_video.get("video_data")
                    if isinstance(encoded_video, str):
                        decoded = self._safe_b64decode(encoded_video)
                        if decoded:
                            return decoded, "video/mp4"

        for key in ("video_base64", "video_data", "videoBytes", "content"):
            value = job.get(key) if isinstance(job, dict) else None
            if isinstance(value, str):
                decoded = self._safe_b64decode(value)
                if decoded:
                    return decoded, "video/mp4"

        video_url = self._find_first_url(job)
        if video_url:
            return self._download_file(video_url)

        return None, None

    def _download_file(self, url: str) -> tuple[bytes, Optional[str]]:
        headers = {}
        if url.startswith(self._api_base) or url.startswith("/"):
            headers = self._build_headers()
        try:
            with httpx.Client(timeout=self._request_timeout, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:  # type: ignore[attr-defined]
            raise VideoGenerationError(f"Не удалось скачать видео Kling: {exc}") from exc
        mime_type = response.headers.get("Content-Type", "video/mp4")
        return response.content, mime_type

    def _safe_b64decode(self, value: str) -> Optional[bytes]:
        try:
            return base64.b64decode(value, validate=False)
        except Exception:
            return None

    def _find_first_url(self, payload: Any) -> Optional[str]:
        stack = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, str) and self._looks_like_video_url(current):
                return current
            if isinstance(current, dict):
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
        return None

    @staticmethod
    def _looks_like_video_url(value: str) -> bool:
        lowered = value.lower()
        return lowered.startswith("http") and any(ext in lowered for ext in (".mp4", ".mov", ".webm", ".mkv"))

    @staticmethod
    def _extract_first_string(payload: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        job = KlingVideoProvider._unwrap_job(payload)
        for key in keys:
            value = job.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _extract_first_number(payload: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
        for key in keys:
            value = payload.get(key)
            parsed = KlingVideoProvider._maybe_number(value)
            if parsed is not None:
                return parsed
        job = KlingVideoProvider._unwrap_job(payload)
        for key in keys:
            value = job.get(key)
            parsed = KlingVideoProvider._maybe_number(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _maybe_number(value: Any) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _safe_extract_error(response: Optional[httpx.Response]) -> str:
        if not response:
            return ""
        try:
            data = response.json()
            if isinstance(data, dict):
                return json.dumps(data, ensure_ascii=False)
        except Exception:
            pass
        return response.text


register_video_provider(KlingVideoProvider.slug, KlingVideoProvider)
