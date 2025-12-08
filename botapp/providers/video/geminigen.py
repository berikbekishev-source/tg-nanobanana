from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from django.conf import settings

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult

logger = logging.getLogger(__name__)


class GeminigenVeoProvider(BaseVideoProvider):
    """Провайдер генерации видео через Geminigen (Veo модели)."""

    slug = "veo"
    supports_extension = False
    _ALLOWED_MODELS = {
        "veo-2",
        "veo-3",
        "veo-3-fast",
        "veo-3.1",
        "veo-3.1-fast",
        "sora-2-free",
        "sora-2",
        "sora-2-pro",
        "sora-2-pro-hd",
    }

    _ENDPOINT = "/uapi/v1/video-gen/veo"

    def _validate_settings(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "GEMINIGEN_API_KEY", None)
        if not self._api_key:
            raise VideoGenerationError("GEMINIGEN_API_KEY не задан — Geminigen недоступен.")

        base_url = getattr(settings, "GEMINIGEN_API_BASE_URL", "https://api.geminigen.ai") or "https://api.geminigen.ai"
        self._base_url: str = base_url.rstrip("/")

        timeout_raw = getattr(settings, "GEMINIGEN_REQUEST_TIMEOUT", None)
        self._timeout = (
            httpx.Timeout(float(timeout_raw), connect=10.0)
            if timeout_raw
            else httpx.Timeout(120.0, connect=10.0)
        )
        self._max_retries: int = int(getattr(settings, "GEMINIGEN_MAX_RETRIES", 3) or 0)
        self._retry_backoff: float = float(getattr(settings, "GEMINIGEN_RETRY_BACKOFF", 2.0) or 0.0)

    def _build_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self._api_key,
        }

    def _build_url(self) -> str:
        return f"{self._base_url}{self._ENDPOINT}"

    @classmethod
    def _normalize_model(cls, raw_name: str) -> str:
        """Приводим internal Vertex-подобные имена к списку, который принимает Geminigen."""
        name = (raw_name or "").strip()
        if not name:
            return name

        name = name.split("@", 1)[0]  # убираем @default
        for suffix in ("-generate-preview", "-generate-001", "-generate"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break

        # Если всё ещё не в списке — попробуем подобрать по префиксу
        if name not in cls._ALLOWED_MODELS:
            for allowed in cls._ALLOWED_MODELS:
                if name.startswith(allowed):
                    name = allowed
                    break
        return name

    @staticmethod
    def _pick_mime(mime: Optional[str]) -> str:
        value = (mime or "").lower()
        if value:
            return value
        return "image/png"

    @staticmethod
    def _extract_field(payload: Dict[str, Any], *candidates: str) -> Optional[Any]:
        """Достаёт значение, перебирая несколько ключей и data-блок."""
        for key in candidates:
            if key in payload and payload.get(key) is not None:
                return payload.get(key)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        for key in candidates:
            if key in data and data.get(key) is not None:
                return data.get(key)
        return None

    def _download_media(self, url: str) -> Tuple[bytes, str]:
        """Скачивает видео по media_url, возвращает байты и MIME."""
        timeout = httpx.Timeout(300.0, connect=10.0)
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
        last_frame_media: Optional[bytes] = None,
        last_frame_mime_type: Optional[str] = None,
    ) -> VideoGenerationResult:
        if not prompt or not prompt.strip():
            raise VideoGenerationError("Промт обязателен для Geminigen Veo.")

        raw_model_value = model_name or params.get("model") or params.get("api_model") or params.get("api_model_name")
        model_value = self._normalize_model(raw_model_value)
        if not model_value:
            raise VideoGenerationError("Не задано имя модели для Geminigen Veo.")
        if model_value not in self._ALLOWED_MODELS:
            raise VideoGenerationError(
                f"Модель '{raw_model_value}' не поддерживается Geminigen. "
                f"Разрешенные: {', '.join(sorted(self._ALLOWED_MODELS))}"
            )

        aspect_ratio = params.get("aspect_ratio") or params.get("aspectRatio")
        resolution = params.get("resolution")

        form_data: Dict[str, Any] = {
            "prompt": prompt,
            "model": str(model_value),
        }
        if resolution:
            form_data["resolution"] = str(resolution)
        if aspect_ratio:
            form_data["aspect_ratio"] = str(aspect_ratio)

        ref_history = params.get("ref_history") or params.get("refHistory")
        if ref_history:
            form_data["ref_history"] = str(ref_history)

        files: List[Tuple[str, Tuple[str, bytes, str]]] = []
        if input_media:
            files.append(("files", ("reference.png", input_media, self._pick_mime(input_mime_type))))
        elif params.get("file_urls"):
            form_data["file_urls"] = params.get("file_urls")
        elif params.get("image_url"):
            form_data["file_urls"] = params.get("image_url")

        # Финальный кадр Geminigen пока не поддерживает — сохраняем в метаданных для отладки.
        if last_frame_media:
            form_data["final_frame_hint"] = "attached_in_metadata"

        logger.info(
            "[GEMINIGEN] Отправка запроса: model=%s, mode=%s, aspect_ratio=%s, resolution=%s, has_file=%s",
            model_value,
            generation_type,
            aspect_ratio,
            resolution,
            bool(files),
        )

        response = None
        retries_done = 0
        last_error: Optional[Exception] = None

        while True:
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(
                        self._build_url(),
                        headers=self._build_headers(),
                        data=form_data,
                        files=files or None,
                        follow_redirects=True,
                    )
                    response.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
                resp = exc.response
                status_code = getattr(resp, "status_code", None)
                is_retryable = status_code is not None and 500 <= status_code < 600
                detail = ""
                if resp is not None:
                    try:
                        err_payload = resp.json()
                        detail = json.dumps(err_payload, ensure_ascii=False)
                    except Exception:
                        detail = resp.text

                if is_retryable and retries_done < self._max_retries:
                    delay = self._retry_backoff * (2**retries_done)
                    logger.warning(
                        "[GEMINIGEN] Ошибка %s, попытка %s/%s, повтор через %.1fs: %s",
                        status_code,
                        retries_done + 1,
                        self._max_retries,
                        delay,
                        detail[:500],
                    )
                    last_error = exc
                    retries_done += 1
                    if delay > 0:
                        time.sleep(delay)
                    continue

                raise VideoGenerationError(f"Geminigen вернул ошибку {status_code}: {detail}") from exc
            except httpx.RequestError as exc:
                if retries_done < self._max_retries:
                    delay = self._retry_backoff * (2**retries_done)
                    logger.warning(
                        "[GEMINIGEN] Сетевая ошибка, попытка %s/%s, повтор через %.1fs: %s",
                        retries_done + 1,
                        self._max_retries,
                        delay,
                        str(exc)[:500],
                    )
                    last_error = exc
                    retries_done += 1
                    if delay > 0:
                        time.sleep(delay)
                    continue

                raise VideoGenerationError(f"Не удалось выполнить запрос к Geminigen: {exc}") from exc

        if response is None and last_error:
            raise VideoGenerationError(f"Не удалось выполнить запрос к Geminigen: {last_error}")

        payload: Dict[str, Any] = {}
        try:
            payload = response.json()
        except Exception:
            payload = {"raw_text": response.text}

        logger.info(f"[GEMINIGEN] API response: {json.dumps(payload, ensure_ascii=False)[:500]}")

        job_id = self._extract_field(payload, "uuid", "id", "job_id", "jobId")
        status = self._extract_field(payload, "status", "status_code", "statusCode")
        media_url = self._extract_field(payload, "media_url", "mediaUrl")
        logger.debug(f"[GEMINIGEN] Parsed: job_id={job_id}, status={status}, media_url={str(media_url)[:100] if media_url else None}")

        metadata = {
            "response": payload,
            "request": form_data,
            "generationType": generation_type,
        }
        if files:
            metadata["hasReferenceImage"] = True
        if last_frame_media:
            metadata["finalFrameProvided"] = True

        if media_url:
            logger.info(f"[GEMINIGEN] Скачивание видео: {str(media_url)[:100]}...")
            video_bytes, mime_type = self._download_media(str(media_url))
            logger.info(f"[GEMINIGEN] Видео скачано: {len(video_bytes)} bytes, mime={mime_type}")
            return VideoGenerationResult(
                content=video_bytes,
                mime_type=mime_type or "video/mp4",
                duration=params.get("duration"),
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                provider_job_id=str(job_id) if job_id else None,
                metadata=metadata,
            )

        if not job_id:
            raise VideoGenerationError(
                "Geminigen не вернул идентификатор задачи (uuid) и ссылку на видео. Проверьте параметры или баланс."
            )

        logger.info(
            "[GEMINIGEN] Задача отправлена: uuid=%s, status=%s (ожидание вебхука/пула)",
            job_id,
            status,
        )

        return VideoGenerationResult(
            content=None,
            mime_type="video/mp4",
            duration=params.get("duration"),
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            provider_job_id=str(job_id),
            metadata=metadata,
        )


register_video_provider(GeminigenVeoProvider.slug, GeminigenVeoProvider)
