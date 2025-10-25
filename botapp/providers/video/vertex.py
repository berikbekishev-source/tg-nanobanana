from __future__ import annotations

import base64
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from . import register_video_provider
from .base import BaseVideoProvider, VideoGenerationError, VideoGenerationResult


class VertexVeoProvider(BaseVideoProvider):
    """Провайдер генерации видео через Veo (Vertex AI, метод predictLongRunning)."""

    slug = "veo"

    _MODEL_NAME_ALIASES: Dict[str, List[str]] = {
        "veo-3.1-fast": [
            "veo-3.1-fast-generate-preview",
            "veo-3.1-fast-generate-001",
        ],
        "veo-3.1": [
            "veo-3.1-generate-preview",
        ],
        "veo-3.0-fast": [
            "veo-3.0-fast-generate-001",
            "veo-3.0-fast-generate-preview",
        ],
        "veo-3.0": [
            "veo-3.0-generate-001",
            "veo-3.0-generate-preview",
        ],
        "veo-2.0": [
            "veo-2.0-generate-001",
        ],
    }

    _DEFAULT_POLL_INTERVAL = 5  # seconds
    _DEFAULT_POLL_TIMEOUT = 15 * 60  # seconds

    def _validate_settings(self) -> None:
        creds_json = getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS_JSON", None)
        if not creds_json:
            raise VideoGenerationError("GOOGLE_APPLICATION_CREDENTIALS_JSON не задан — Veo недоступен.")

        self._credentials_info = service_account.Credentials.from_service_account_info(
            settings.GOOGLE_APPLICATION_CREDENTIALS_JSON  # type: ignore[arg-type]
            if isinstance(settings.GOOGLE_APPLICATION_CREDENTIALS_JSON, dict)
            else self._load_credentials(settings.GOOGLE_APPLICATION_CREDENTIALS_JSON)
        )

        self._project_id: Optional[str] = getattr(settings, "VERTEX_PROJECT_ID", None) or getattr(
            settings, "GCP_PROJECT_ID", None
        )
        if not self._project_id:
            raise VideoGenerationError("VERTEX_PROJECT_ID / GCP_PROJECT_ID не задан.")

        self._location: str = getattr(settings, "VERTEX_LOCATION", "us-central1")

    @staticmethod
    def _load_credentials(raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            with open(raw, "r", encoding="utf-8") as fh:
                return json.load(fh)

    def _get_scoped_credentials(self):
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        return self._credentials_info.with_scopes(scopes)  # type: ignore[attr-defined]

    def _fetch_access_token(self) -> Tuple[str, float]:
        credentials = self._get_scoped_credentials()
        credentials.refresh(Request())
        return credentials.token, credentials.expiry.timestamp() if credentials.expiry else time.time() + 300

    def _request(
        self,
        method: str,
        url: str,
        token: str,
        json_payload: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(300.0, connect=30.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, headers=headers, json=json_payload, follow_redirects=True)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 429:
                    raise VideoGenerationError(
                        "Квота Veo временно исчерпана. Попробуйте повторить запрос через минуту или увеличьте лимиты в Google Cloud."
                    ) from exc
                if status_code == 403:
                    raise VideoGenerationError(
                        "Доступ к модели Veo запрещен. Проверьте IAM-права сервисного аккаунта и включенные регионы."
                    ) from exc
                if exc.response is not None:
                    try:
                        payload = exc.response.json()
                        detail = json.dumps(payload, ensure_ascii=False)
                    except Exception:
                        detail = exc.response.text
                else:
                    detail = str(exc)
                raise VideoGenerationError(f"{exc}\nDetails: {detail}") from exc
            return response

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        return model_name.split("@", 1)[0]

    def _candidate_model_names(self, model_name: str) -> List[str]:
        """Собирает список имён модели с учётом алиасов и @default."""
        seen: set[str] = set()
        result: List[str] = []

        def add(name: Optional[str]) -> None:
            if name and name not in seen:
                seen.add(name)
                result.append(name)

        base_name, _, _ = model_name.partition("@")
        add(model_name)
        add(base_name)

        aliases = self._MODEL_NAME_ALIASES.get(model_name) or self._MODEL_NAME_ALIASES.get(base_name) or []
        for alias in aliases:
            add(alias)

        if "-generate" not in base_name:
            add(f"{base_name}-generate")
        if "-generate-preview" not in base_name:
            add(f"{base_name}-generate-preview")
        if "-generate-001" not in base_name:
            add(f"{base_name}-generate-001")

        current = result[:]
        for name in current:
            normalized = self._normalize_model_name(name)
            add(f"{normalized}@default")

        return result

    @staticmethod
    def _build_instance(
        prompt: str,
        generation_type: str,
        input_media: Optional[bytes],
        input_mime_type: Optional[str],
    ) -> Dict[str, Any]:
        instance: Dict[str, Any] = {"prompt": prompt}

        if generation_type == "image2video" and input_media:
            instance["image"] = {
                "bytesBase64Encoded": base64.b64encode(input_media).decode("utf-8"),
                "mimeType": input_mime_type or "image/png",
            }

        return instance

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"true", "1", "yes", "on"}
        if value is None:
            return False
        return bool(value)

    def _build_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        mapping: Dict[str, Tuple[str, Optional[type]]] = {
            "duration": ("durationSeconds", int),
            "duration_seconds": ("durationSeconds", int),
            "durationSeconds": ("durationSeconds", int),
            "aspect_ratio": ("aspectRatio", None),
            "aspectRatio": ("aspectRatio", None),
            "resolution": ("resolution", None),
            "sample_count": ("sampleCount", int),
            "sampleCount": ("sampleCount", int),
            "seed": ("seed", int),
            "negative_prompt": ("negativePrompt", None),
            "negativePrompt": ("negativePrompt", None),
            "person_generation": ("personGeneration", None),
            "personGeneration": ("personGeneration", None),
            "storage_uri": ("storageUri", None),
            "storageUri": ("storageUri", None),
            "resize_mode": ("resizeMode", None),
            "resizeMode": ("resizeMode", None),
            "compression_quality": ("compressionQuality", None),
            "compressionQuality": ("compressionQuality", None),
            "enhance_prompt": ("enhancePrompt", bool),
            "enhancePrompt": ("enhancePrompt", bool),
            "generate_audio": ("generateAudio", bool),
            "generateAudio": ("generateAudio", bool),
        }

        parameters: Dict[str, Any] = {}
        for key, value in params.items():
            if value is None:
                continue
            target = mapping.get(key)
            if not target:
                continue
            target_key, caster = target
            try:
                if caster is int:
                    parameters[target_key] = int(value)
                elif caster is bool:
                    parameters[target_key] = self._to_bool(value)
                else:
                    parameters[target_key] = value
            except (TypeError, ValueError) as exc:
                raise VideoGenerationError(f"Некорректное значение параметра '{key}': {value}") from exc

        if "sampleCount" not in parameters:
            parameters["sampleCount"] = int(params.get("sampleCount") or params.get("sample_count") or 1)
        if "durationSeconds" not in parameters and params.get("duration"):
            parameters["durationSeconds"] = int(params["duration"])
        if "generateAudio" not in parameters:
            parameters["generateAudio"] = self._to_bool(params.get("generate_audio", True))

        return parameters

    def _invoke_predict_long_running(
        self,
        token: str,
        model_name: str,
        instance: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        url = (
            f"https://{self._location}-aiplatform.googleapis.com/v1/"
            f"projects/{self._project_id}/locations/{self._location}/publishers/google/models/{model_name}:predictLongRunning"
        )
        payload = {
            "instances": [instance],
            "parameters": parameters,
        }
        return self._request("POST", url, token, json_payload=payload).json()

    def _poll_predict_operation(
        self,
        token: str,
        model_name: str,
        operation_name: str,
        timeout_seconds: int = _DEFAULT_POLL_TIMEOUT,
    ) -> Dict[str, Any]:
        fetch_url = (
            f"https://{self._location}-aiplatform.googleapis.com/v1/"
            f"projects/{self._project_id}/locations/{self._location}/publishers/google/models/{model_name}:fetchPredictOperation"
        )
        payload = {"operationName": operation_name}
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            data = self._request("POST", fetch_url, token, json_payload=payload).json()
            if data.get("done"):
                if "error" in data:
                    raise VideoGenerationError(json.dumps(data["error"], ensure_ascii=False))
                return data
            time.sleep(self._DEFAULT_POLL_INTERVAL)

        raise VideoGenerationError("Превышено время ожидания завершения генерации видео.")

    def _download_file_uri(self, token: str, file_uri: str) -> bytes:
        if file_uri.startswith(("https://", "http://")):
            timeout = httpx.Timeout(300.0, connect=30.0)
            with httpx.Client(timeout=timeout) as client:
                response = client.get(file_uri, headers={"Authorization": f"Bearer {token}"}, follow_redirects=True)
                response.raise_for_status()
                return response.content

        if file_uri.startswith("gs://"):
            without_scheme = file_uri[5:]
            bucket, _, blob = without_scheme.partition("/")
            if not bucket or not blob:
                raise VideoGenerationError(f"Некорректный gs:// URI: {file_uri}")
            encoded_blob = quote(blob, safe="")
            url = f"https://storage.googleapis.com/download/storage/v1/b/{bucket}/o/{encoded_blob}?alt=media"
            headers = {"Authorization": f"Bearer {token}"}
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.content

        raise VideoGenerationError(f"Неизвестный формат URI: {file_uri}")

    def _extract_video_from_operation(
        self,
        token: str,
        operation_payload: Dict[str, Any],
    ) -> Tuple[bytes, str, Dict[str, Any]]:
        response = operation_payload.get("response") or {}
        videos = response.get("videos") or []
        if not videos:
            raise VideoGenerationError("Veo не вернул видеоролики в ответе операции.")

        video_entry = videos[0]
        mime_type = video_entry.get("mimeType", "video/mp4")

        if "bytesBase64Encoded" in video_entry:
            video_bytes = base64.b64decode(video_entry["bytesBase64Encoded"])
        elif "gcsUri" in video_entry:
            video_bytes = self._download_file_uri(token, video_entry["gcsUri"])
        else:
            raise VideoGenerationError("Не удалось извлечь ссылку на видео из ответа Veo.")

        metadata = {
            "operation": operation_payload,
            "videoEntry": video_entry,
        }
        return video_bytes, mime_type, metadata

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
        token, _ = self._fetch_access_token()

        instance = self._build_instance(
            prompt=prompt,
            generation_type=generation_type,
            input_media=input_media,
            input_mime_type=input_mime_type,
        )
        parameters = self._build_parameters(params)

        last_error: Optional[Exception] = None
        predict_response: Dict[str, Any] = {}
        resolved_model_name: Optional[str] = None

        for candidate_name in self._candidate_model_names(model_name):
            try:
                predict_response = self._invoke_predict_long_running(
                    token=token,
                    model_name=candidate_name,
                    instance=instance,
                    parameters=parameters,
                )
                resolved_model_name = candidate_name
                break
            except VideoGenerationError as exc:
                last_error = exc
                detail = str(exc).lower()
                if "not found" in detail or "404" in detail:
                    continue
                raise

        if not resolved_model_name:
            if last_error:
                raise last_error
            raise VideoGenerationError("Не удалось определить корректное имя модели Veo.")

        operation_name = predict_response.get("name")
        if not operation_name:
            raise VideoGenerationError("Veo не вернул идентификатор операции для дальнейшего ожидания.")

        operation_result = self._poll_predict_operation(
            token=token,
            model_name=resolved_model_name,
            operation_name=operation_name,
        )

        video_bytes, mime_type, metadata = self._extract_video_from_operation(token, operation_result)

        metadata.update(
            {
                "resolvedModelName": resolved_model_name,
                "parameters": parameters,
                "operationName": operation_name,
            }
        )

        duration = parameters.get("durationSeconds")
        aspect_ratio = parameters.get("aspectRatio") or params.get("aspect_ratio")
        resolution = parameters.get("resolution") or params.get("resolution")

        return VideoGenerationResult(
            content=video_bytes,
            mime_type=mime_type,
            duration=int(duration) if duration else None,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            provider_job_id=operation_name,
            metadata=metadata,
        )


register_video_provider(VertexVeoProvider.slug, VertexVeoProvider)
