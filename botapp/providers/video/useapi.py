from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

from botapp.services import _download_binary_file

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult


class UseApiRunwayVideoProvider(BaseVideoProvider):
    """Провайдер генерации видео Runway Gen-4 через useapi.net."""

    slug = "useapi"

    _DEFAULT_BASE_URL = "https://api.useapi.net"
    _ASSETS_ENDPOINT = "/v1/runwayml/assets/"
    _CREATE_ENDPOINT = "/v1/runwayml/gen4/create"
    _VIDEO_ENDPOINT = "/v1/runwayml/gen4/video"
    _TASK_ENDPOINT = "/v1/runwayml/tasks/{task_id}"

    _SUCCESS_STATUSES = {"SUCCEEDED", "SUCCESS", "COMPLETED", "DONE"}
    _FAIL_STATUSES = {"FAILED", "ERROR", "CANCELLED", "CANCELED", "REJECTED", "MODERATED"}

    def _validate_settings(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "USEAPI_API_KEY", None)
        if not self._api_key:
            raise VideoGenerationError("USEAPI_API_KEY не задан — Runway недоступен.")

        base_url = getattr(settings, "USEAPI_BASE_URL", self._DEFAULT_BASE_URL) or self._DEFAULT_BASE_URL
        self._base_url: str = base_url.rstrip("/")

        self._poll_interval: int = int(getattr(settings, "USEAPI_POLL_INTERVAL", 5))
        self._poll_timeout: int = int(getattr(settings, "USEAPI_POLL_TIMEOUT", 12 * 60))

        raw_timeout = getattr(settings, "USEAPI_REQUEST_TIMEOUT", None)
        self._request_timeout = (
            httpx.Timeout(float(raw_timeout), connect=15.0)
            if raw_timeout
            else httpx.Timeout(180.0, connect=20.0)
        )

        try:
            self._max_jobs: int = int(getattr(settings, "USEAPI_MAX_JOBS", "5") or 5)
        except Exception:
            self._max_jobs = 5
        self._account_email: Optional[str] = getattr(settings, "USEAPI_ACCOUNT_EMAIL", None)

        try:
            self._asset_upload_retries: int = max(1, int(getattr(settings, "USEAPI_ASSET_RETRIES", "5") or 5))
        except Exception:
            self._asset_upload_retries = 5
        try:
            self._asset_retry_backoff: float = float(getattr(settings, "USEAPI_ASSET_RETRY_BACKOFF", "2.0") or 2.0)
        except Exception:
            self._asset_retry_backoff = 2.0
        # Данные аккаунта Runway (если заданы — проверим/создадим конфиг перед генерацией)
        self._account_email: Optional[str] = getattr(settings, "USEAPI_ACCOUNT_EMAIL", None)
        self._account_password: Optional[str] = getattr(settings, "USEAPI_ACCOUNT_PASSWORD", None)
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
                params=params,
                input_media=input_media,
                input_mime_type=input_mime_type,
            )
        if generation_type == "video2video":
            return self._generate_video_to_video(
                prompt=prompt,
                params=params,
                input_media=input_media,
                input_mime_type=input_mime_type,
            )
        raise VideoGenerationError("Runway (useapi) поддерживает режимы image2video и video2video.")

    def _generate_image_to_video(
        self,
        *,
        prompt: str,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> VideoGenerationResult:
        logger.info(f"[USEAPI] Начало image2video: prompt={prompt[:100]}...")
        image_bytes = input_media
        if not image_bytes and params.get("image_url"):
            try:
                image_bytes = _download_binary_file(str(params["image_url"]))
            except Exception as exc:
                logger.error(f"[USEAPI] Не удалось скачать изображение: {exc}")
                raise VideoGenerationError("Не удалось скачать исходное изображение.") from exc

        if not image_bytes:
            raise VideoGenerationError("Не передано изображение для режима image2video.")

        mime_type = (input_mime_type or params.get("input_image_mime_type") or "image/png").strip() or "image/png"
        file_name = params.get("imageName") or "image.png"

        aspect_ratio = (
            params.get("aspect_ratio")
            or params.get("aspectRatio")
            or params.get("ratio")
            or params.get("format")
            or "16:9"
        )
        seconds = self._sanitize_seconds(params.get("seconds") or params.get("duration"))
        resolution = (params.get("resolution") or "720p").lower()

        self._ensure_account_ready()

        logger.info(f"[USEAPI] Загрузка ассета: mime={mime_type}, name={file_name}")
        asset_id = self._upload_asset(image_bytes, mime_type, file_name)
        if not asset_id:
            logger.error("[USEAPI] Не получен assetId для изображения")
            raise VideoGenerationError("useapi не вернул assetId для исходного изображения.")
        logger.info(f"[USEAPI] Ассет загружен: asset_id={asset_id}")

        create_payload: Dict[str, Any] = {
            "firstImage_assetId": asset_id,
            "text_prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "seconds": seconds,
            "maxJobs": self._max_jobs,
        }
        logger.debug(f"[USEAPI] Create payload: {json.dumps(create_payload, ensure_ascii=False)[:500]}")

        create_response = self._request(
            "POST",
            self._CREATE_ENDPOINT,
            json_payload=create_payload,
        )
        logger.info(f"[USEAPI] Create response: {json.dumps(create_response, ensure_ascii=False)[:500]}")

        task_id = self._extract_task_id(create_response)
        if not task_id:
            logger.error(f"[USEAPI] Не получен taskId: {create_response}")
            raise VideoGenerationError(f"useapi не вернул taskId: {create_response}")
        logger.info(f"[USEAPI] Задача создана: task_id={task_id}")

        task_payload = self._poll_task(task_id)

        status = self._extract_status(task_payload)
        if status and status in self._FAIL_STATUSES:
            logger.error(f"[USEAPI] Задача провалилась: status={status}, payload={json.dumps(task_payload, ensure_ascii=False)[:1000]}")
            raise VideoGenerationError(f"Runway завершилась с ошибкой: {task_payload}")

        video_url = self._extract_video_url(task_payload)
        if not video_url:
            logger.error(f"[USEAPI] Нет URL видео в ответе: {json.dumps(task_payload, ensure_ascii=False)[:1000]}")
            raise VideoGenerationError("Не удалось получить ссылку на видео в ответе Runway.")

        logger.info(f"[USEAPI] Скачивание видео: {video_url[:100]}...")
        try:
            video_bytes = _download_binary_file(video_url)
            logger.info(f"[USEAPI] Видео скачано: {len(video_bytes)} bytes")
        except Exception as exc:
            logger.error(f"[USEAPI] Ошибка скачивания видео: {exc}")
            raise VideoGenerationError("Не удалось скачать видео из Runway.") from exc

        duration_value = self._extract_number(task_payload, ["seconds", "duration"])

        metadata = {
            "createResponse": create_response,
            "task": task_payload,
            "request": create_payload,
        }

        return VideoGenerationResult(
            content=video_bytes,
            mime_type="video/mp4",
            duration=int(duration_value) if isinstance(duration_value, (int, float)) else None,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            provider_job_id=task_id,
            metadata=metadata,
        )

    def _generate_video_to_video(
        self,
        *,
        prompt: str,
        params: Dict[str, Any],
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> VideoGenerationResult:
        logger.info(f"[USEAPI] Начало video2video: prompt={prompt[:100]}...")
        video_bytes = input_media
        if not video_bytes and params.get("video_url"):
            try:
                video_bytes = _download_binary_file(str(params["video_url"]))
            except Exception as exc:
                logger.error(f"[USEAPI] Не удалось скачать исходное видео: {exc}")
                raise VideoGenerationError("Не удалось скачать исходное видео.") from exc

        if not video_bytes:
            raise VideoGenerationError("Не передано видео для режима video2video.")

        mime_type = (input_mime_type or params.get("input_video_mime_type") or "video/mp4").strip() or "video/mp4"
        file_name = params.get("videoName") or params.get("video_name") or "video.mp4"
        aspect_ratio = (
            params.get("aspect_ratio")
            or params.get("aspectRatio")
            or params.get("ratio")
            or "16:9"
        )
        seed = self._sanitize_seed(params.get("seed"))
        explore_mode = params.get("exploreMode")
        reply_url = params.get("replyUrl") or params.get("reply_url")
        reply_ref = params.get("replyRef") or params.get("reply_ref")
        max_jobs = self._sanitize_max_jobs(params.get("maxJobs"))

        self._ensure_account_ready()

        logger.info(f"[USEAPI] Загрузка видео-ассета: mime={mime_type}, name={file_name}")
        video_asset_id = self._upload_asset(video_bytes, mime_type, file_name)
        if not video_asset_id:
            logger.error("[USEAPI] Не получен assetId для видео")
            raise VideoGenerationError("useapi не вернул assetId для исходного видео.")
        logger.info(f"[USEAPI] Видео-ассет загружен: asset_id={video_asset_id}")

        create_payload: Dict[str, Any] = {
            "video_assetId": video_asset_id,
            "text_prompt": prompt,
            "maxJobs": max_jobs,
        }
        if seed is not None:
            create_payload["seed"] = seed
        if isinstance(explore_mode, bool):
            create_payload["exploreMode"] = explore_mode
        if reply_url:
            create_payload["replyUrl"] = str(reply_url)
        if reply_ref:
            create_payload["replyRef"] = str(reply_ref)

        logger.debug(f"[USEAPI] Video create payload: {json.dumps(create_payload, ensure_ascii=False)[:500]}")
        create_response = self._request(
            "POST",
            self._VIDEO_ENDPOINT,
            json_payload=create_payload,
        )
        logger.info(f"[USEAPI] Video create response: {json.dumps(create_response, ensure_ascii=False)[:500]}")

        task_id = self._extract_task_id(create_response)
        if not task_id:
            logger.error(f"[USEAPI] Не получен taskId: {create_response}")
            raise VideoGenerationError(f"useapi не вернул taskId: {create_response}")
        logger.info(f"[USEAPI] Задача создана: task_id={task_id}")

        task_payload = self._poll_task(task_id)

        status = self._extract_status(task_payload)
        if status and status in self._FAIL_STATUSES:
            logger.error(f"[USEAPI] Задача провалилась: status={status}, payload={json.dumps(task_payload, ensure_ascii=False)[:1000]}")
            raise VideoGenerationError(f"Runway завершилась с ошибкой: {task_payload}")

        video_url = self._extract_video_url(task_payload)
        if not video_url:
            logger.error(f"[USEAPI] Нет URL видео в ответе: {json.dumps(task_payload, ensure_ascii=False)[:1000]}")
            raise VideoGenerationError("Не удалось получить ссылку на видео в ответе Runway.")

        logger.info(f"[USEAPI] Скачивание результата: {video_url[:100]}...")
        try:
            final_video_bytes = _download_binary_file(video_url)
            logger.info(f"[USEAPI] Результат скачан: {len(final_video_bytes)} bytes")
        except Exception as exc:
            logger.error(f"[USEAPI] Ошибка скачивания результата: {exc}")
            raise VideoGenerationError("Не удалось скачать видео из Runway.") from exc

        duration_value = self._extract_number(task_payload, ["seconds", "duration"])
        resolution = self._extract_resolution(task_payload)

        metadata = {
            "createResponse": create_response,
            "task": task_payload,
            "request": create_payload,
        }

        return VideoGenerationResult(
            content=final_video_bytes,
            mime_type="video/mp4",
            duration=int(duration_value) if isinstance(duration_value, (int, float)) else None,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            provider_job_id=task_id,
            metadata=metadata,
        )

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self._base_url}{endpoint}"
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
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response else str(exc)
            raise VideoGenerationError(f"useapi HTTP {exc.response.status_code if exc.response else ''}: {detail}") from exc
        except Exception as exc:
            raise VideoGenerationError(f"Ошибка запроса к useapi: {exc}") from exc

    def _ensure_account_ready(self) -> None:
        """
        Если заданы USEAPI_ACCOUNT_EMAIL/PASSWORD, проверяем/создаем конфиг Runway аккаунта в useapi.
        Выполняется один раз за процесс.
        """
        if self._account_ready or not (self._account_email and self._account_password):
            return

        endpoint = f"/v1/runwayml/accounts/{self._account_email}"
        payload = {
            "email": self._account_email,
            "password": self._account_password,
            "maxJobs": self._max_jobs,
        }
        try:
            self._request("POST", endpoint, json_payload=payload)
            self._account_ready = True
        except VideoGenerationError:
            # Пробуем еще раз на всякий случай (вдруг 5xx)
            try:
                time.sleep(2.0)
                self._request("POST", endpoint, json_payload=payload)
                self._account_ready = True
            except Exception as exc:
                raise VideoGenerationError("useapi: не удалось настроить аккаунт Runway. Попробуйте позже.") from exc

    def _upload_asset(self, image_bytes: bytes, mime_type: str, file_name: str) -> Optional[str]:
        url = f"{self._base_url}{self._ASSETS_ENDPOINT}"
        params: Dict[str, Any] = {"name": file_name}
        if self._account_email:
            params["email"] = self._account_email
        retryable_statuses = {500, 502, 503, 504, 520, 521, 522, 524}
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._asset_upload_retries + 1):
            try:
                with httpx.Client(timeout=self._request_timeout, follow_redirects=True) as client:
                    response = client.post(
                        url,
                        params=params,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Accept": "application/json",
                            "Content-Type": mime_type or "image/png",
                        },
                        content=image_bytes,
                    )
                    response.raise_for_status()
                    data = response.json()
                asset_id = self._extract_asset_id(data)
                if asset_id:
                    return asset_id
                raise VideoGenerationError("useapi не вернул assetId для исходного изображения.")
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code if exc.response else None
                if status in retryable_statuses and attempt < self._asset_upload_retries:
                    delay = self._asset_retry_backoff * (2 ** (attempt - 1))
                    time.sleep(delay)
                    continue
                raise VideoGenerationError(
                    f"useapi: не удалось загрузить ассет ({status}). Попробуйте ещё раз."
                ) from exc
            except Exception as exc:
                last_exc = exc
                if attempt < self._asset_upload_retries:
                    delay = self._asset_retry_backoff * (2 ** (attempt - 1))
                    time.sleep(delay)
                    continue
                raise VideoGenerationError(f"useapi: ошибка загрузки ассета: {exc}") from exc

        raise VideoGenerationError("useapi: не удалось загрузить ассет после нескольких попыток.") from last_exc

    def _poll_task(self, task_id: str) -> Dict[str, Any]:
        endpoint = self._TASK_ENDPOINT.format(task_id=task_id)
        deadline = time.time() + self._poll_timeout
        last_payload: Dict[str, Any] = {}
        poll_count = 0

        logger.info(f"[USEAPI] Начало polling задачи {task_id}, timeout={self._poll_timeout}s")
        while time.time() < deadline:
            last_payload = self._request("GET", endpoint)
            status = self._extract_status(last_payload)
            poll_count += 1
            if poll_count % 10 == 1:
                logger.debug(f"[USEAPI] Poll #{poll_count} task={task_id}, status={status}")
            if status and status in self._SUCCESS_STATUSES:
                logger.info(f"[USEAPI] Задача {task_id} завершена успешно: status={status}")
                return last_payload
            if status and status in self._FAIL_STATUSES:
                logger.warning(f"[USEAPI] Задача {task_id} провалилась: status={status}, payload={json.dumps(last_payload, ensure_ascii=False)[:500]}")
                return last_payload
            time.sleep(self._poll_interval)

        logger.error(f"[USEAPI] Timeout задачи {task_id} после {poll_count} попыток")
        raise VideoGenerationError(f"useapi: превышено время ожидания задачи {task_id}")

    @staticmethod
    def _extract_asset_id(payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        for key in ("assetId", "asset_id", "id"):
            if payload.get(key):
                return str(payload[key])
        if isinstance(payload.get("asset"), dict):
            for key in ("assetId", "id"):
                if payload["asset"].get(key):
                    return str(payload["asset"][key])
        return None

    @staticmethod
    def _extract_task_id(payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        if payload.get("taskId"):
            return str(payload["taskId"])
        if isinstance(payload.get("task"), dict):
            task = payload["task"]
            return str(task.get("taskId") or task.get("id") or task.get("task_id")) if (task.get("taskId") or task.get("id") or task.get("task_id")) else None
        return None

    @staticmethod
    def _extract_status(payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        for key in ("status", "task_status", "state"):
            value = payload.get(key)
            if isinstance(value, str):
                return value.upper()
        task = payload.get("task")
        if isinstance(task, dict):
            for key in ("status", "task_status", "state"):
                value = task.get(key)
                if isinstance(value, str):
                    return value.upper()
        return None

    @staticmethod
    def _extract_video_url(payload: Dict[str, Any]) -> Optional[str]:
        task = payload.get("task") if isinstance(payload, dict) else None
        artifacts = None
        if isinstance(task, dict):
            artifacts = task.get("artifacts") or task.get("result") or task.get("results")
        if artifacts is None and isinstance(payload, dict):
            artifacts = payload.get("artifacts") or payload.get("result") or payload.get("results")

        if isinstance(artifacts, list):
            for item in artifacts:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    for key in ("url", "downloadUrl", "downloadURL", "videoUrl", "videoURL"):
                        url_val = item.get(key)
                        if isinstance(url_val, str) and url_val.startswith("http"):
                            return url_val
        if isinstance(artifacts, dict):
            for key in ("url", "downloadUrl", "videoUrl"):
                val = artifacts.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    return val
        return None

    def _sanitize_max_jobs(self, value: Any) -> int:
        try:
            jobs = int(value)
        except (TypeError, ValueError):
            jobs = self._max_jobs
        if jobs <= 0:
            jobs = self._max_jobs
        return min(max(1, jobs), 10)

    @staticmethod
    def _sanitize_seed(value: Any) -> Optional[int]:
        try:
            seed_value = int(value)
        except (TypeError, ValueError):
            return None
        if 1 <= seed_value <= 4294967294:
            return seed_value
        return None

    @staticmethod
    def _sanitize_seconds(value: Any) -> int:
        try:
            ivalue = int(float(value))
        except Exception:
            ivalue = 5
        return 10 if ivalue >= 10 else 5

    @staticmethod
    def _extract_resolution(payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None

        candidates: list[Dict[str, Any]] = [payload]
        task = payload.get("task")
        if isinstance(task, dict):
            candidates.append(task)
            options = task.get("options")
            if isinstance(options, dict):
                candidates.append(options)

        width = None
        height = None
        for item in candidates:
            maybe_w = item.get("width") if isinstance(item, dict) else None
            maybe_h = item.get("height") if isinstance(item, dict) else None
            if width is None and isinstance(maybe_w, (int, float)):
                width = int(maybe_w)
            if height is None and isinstance(maybe_h, (int, float)):
                height = int(maybe_h)
            if width is not None and height is not None:
                break

        if width and height:
            return f"{width}x{height}"
        return None

    @staticmethod
    def _extract_number(payload: Dict[str, Any], keys: Any) -> Optional[float]:
        if not isinstance(payload, dict):
            return None
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        task = payload.get("task")
        if isinstance(task, dict):
            for key in keys:
                value = task.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        return None


register_video_provider(UseApiRunwayVideoProvider.slug, UseApiRunwayVideoProvider)
