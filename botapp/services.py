import base64
import httpx
import uuid
import json
import io
import re
import os
import time
from json import JSONDecoder
from typing import Any, Dict, List, Optional, Tuple
from django.conf import settings
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
try:
    from supabase import create_client
except ImportError:  # pragma: no cover
    create_client = None

GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_IMAGE_URL = "https://api.openai.com/v1/images/generations"
OPENAI_IMAGE_EDIT_URL = "https://api.openai.com/v1/images/edits"
KIE_DEFAULT_BASE_URL = "https://api.kie.ai"
DEFAULT_VERTEX_IMAGE_MODEL = "imagen-4.0-generate-001"

def vertex_generate_images(prompt: str, quantity: int, params: Optional[Dict[str, Any]] = None) -> List[bytes]:
    """Генерация изображений через Vertex AI Imagen."""
    from google.cloud import aiplatform
    from google.oauth2 import service_account
    from vertexai.preview.vision_models import ImageGenerationModel

    # Parse credentials from environment
    creds_dict = _load_service_account_info()
    credentials = service_account.Credentials.from_service_account_info(creds_dict)

    # Initialize Vertex AI
    project_id = getattr(settings, 'GCP_PROJECT_ID', creds_dict.get('project_id'))
    location = getattr(settings, 'GCP_LOCATION', 'us-central1')
    aiplatform.init(project=project_id, location=location, credentials=credentials)

    # Load Imagen model
    model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")

    images_bytes = []
    for _ in range(quantity):
        response = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_some",
            person_generation="allow_adult",
        )

        if response.images:
            img = response.images[0]
            buffer = io.BytesIO()
            img._pil_image.save(buffer, format="PNG")
            images_bytes.append(buffer.getvalue())

    return images_bytes


def vertex_edit_images(
    prompt: str,
    quantity: int,
    input_images: List[Dict[str, Any]],
    params: Optional[Dict[str, Any]] = None,
    *,
    image_mode: Optional[str] = None,
) -> List[bytes]:
    if not input_images:
        raise ValueError("Для режима image2image необходимо загрузить изображения.")

    session = _authorized_vertex_session()
    creds_info = _load_service_account_info()

    project_id = getattr(settings, "GCP_PROJECT_ID", creds_info.get("project_id"))
    location = getattr(settings, "GCP_LOCATION", "us-central1")
    model_name = getattr(settings, "VERTEX_IMAGE_EDIT_MODEL", "imagen-3.0-capability-001")
    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model_name}:predict"

    mode = image_mode or params.get("image_mode") if params else None
    reference_images = []
    raw_entry = next((img for img in input_images if img.get("role") == "raw"), None)
    mask_entry = next((img for img in input_images if img.get("role") == "mask"), None)
    subject_entries: List[Dict[str, Any]] = []
    for idx, image in enumerate(input_images, start=1):
        if image.get("role") not in (None, "subject"):
            continue
        content = image.get("content")
        if not content:
            continue
        b64 = base64.b64encode(content).decode()
        subject_entries.append(
            {
                "referenceType": "REFERENCE_TYPE_SUBJECT",
                "referenceId": idx,
                "referenceImage": {"bytesBase64Encoded": b64},
                "subjectImageConfig": {
                    "subjectDescription": (params or {}).get("subject_description", f"reference {idx}"),
                    "subjectType": (params or {}).get("subject_type", "SUBJECT_TYPE_DEFAULT"),
                },
            }
        )

    if mode == "edit":
        if not raw_entry or not mask_entry:
            raise ValueError("Для редактирования необходимо отправить изображение и маску.")
        reference_images.append(
            {
                "referenceType": "REFERENCE_TYPE_RAW",
                "referenceId": 1,
                "referenceImage": {"bytesBase64Encoded": base64.b64encode(raw_entry["content"]).decode()},
            }
        )
        reference_images.append(
            {
                "referenceType": "REFERENCE_TYPE_MASK",
                "referenceId": 2,
                "referenceImage": {"bytesBase64Encoded": base64.b64encode(mask_entry["content"]).decode()},
                "maskImageConfig": {
                    "maskMode": (params or {}).get("mask_mode", "MASK_MODE_USER_PROVIDED"),
                    "dilation": (params or {}).get("mask_dilation", 0.01),
                },
            }
        )
        for idx, entry in enumerate(subject_entries, start=3):
            entry["referenceId"] = idx
            reference_images.append(entry)
    else:
        reference_images.extend(subject_entries)

    if not reference_images:
        raise ValueError("Не удалось подготовить изображения для Vertex edit.")

    request_payload = {
        "instances": [
            {
                "prompt": prompt,
                "referenceImages": reference_images,
            }
        ],
        "parameters": {
            "sampleCount": max(1, min(quantity, 4)),
        },
    }
    if mode == "edit":
        request_payload["parameters"]["editMode"] = (params or {}).get("edit_mode", "EDIT_MODE_INPAINT_INSERTION")

    response = session.post(url, json=request_payload, timeout=120)
    if response.status_code >= 400:
        detail = response.text
        try:
            payload = response.json()
            error_obj = payload.get("error")
            if isinstance(error_obj, dict):
                detail = error_obj.get("message") or str(error_obj)
            elif isinstance(payload, dict):
                detail = payload.get("message") or detail
        except ValueError:
            pass
        raise ValueError(f"Vertex Imagen error ({response.status_code}): {detail}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError(f"Vertex Imagen возвращает неожиданный ответ: {response.text}") from exc
    predictions = data.get("predictions") or []
    results: List[bytes] = []
    for prediction in predictions:
        b64_data = prediction.get("bytesBase64Encoded")
        if b64_data:
            results.append(base64.b64decode(b64_data))
    return results

class GeminiBlockedError(Exception):
    """Исключение когда Gemini заблокировал генерацию."""
    def __init__(self, message: str, finish_reason: str = None, block_reason: str = None, safety_ratings: list = None):
        super().__init__(message)
        self.finish_reason = finish_reason
        self.block_reason = block_reason
        self.safety_ratings = safety_ratings or []


def gemini_generate_images(
    prompt: str,
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
    *,
    model_name: Optional[str] = None,
    generation_type: str = "text2image",
    input_images: Optional[List[Dict[str, Any]]] = None,
    image_mode: Optional[str] = None,
) -> List[bytes]:
    """Возвращает список байтов изображений через публичный Gemini API."""
    import logging
    logger = logging.getLogger(__name__)

    if not model_name:
        raise ValueError("model_name обязателен для Gemini image генерации и должен приходить из AIModel.api_model_name")

    if generation_type == "image2image" and not input_images:
        raise ValueError("Для режима image2image необходимо передать хотя бы одно изображение.")

    params = params or {}
    model_id = _gemini_model_name(model_name)

    url = GEMINI_URL_TMPL.format(model=model_id)
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY не настроен для Gemini image генерации")
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    parts: List[Dict[str, Any]] = [{"text": prompt}]
    # Gemini 3 Pro Image Preview поддерживает до 14 референсов.
    for img in (input_images or [])[:14]:
        content = img.get("content")
        if not content:
            continue
        parts.append(
            {
                "inlineData": {
                    "mimeType": img.get("mime_type", "image/png"),
                    "data": base64.b64encode(content).decode(),
                }
            }
        )

    payload: Dict[str, Any] = {"contents": [{"role": "user", "parts": parts}]}

    generation_config: Dict[str, Any] = {"responseModalities": ["IMAGE"]}
    image_config: Dict[str, Any] = {}

    for key in ("temperature", "top_p", "top_k"):
        if key in params:
            generation_config[key] = params[key]

    aspect_ratio = params.get("aspect_ratio") or params.get("aspectRatio")
    image_size = params.get("image_size") or params.get("imageSize")
    if aspect_ratio:
        image_config["aspectRatio"] = str(aspect_ratio)
    if image_size:
        image_config["imageSize"] = str(image_size).upper()
    if image_config:
        generation_config["imageConfig"] = image_config

    payload["generationConfig"] = generation_config

    imgs: List[bytes] = []
    with httpx.Client(timeout=120) as client:
        for i in range(quantity):
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

            # Извлекаем информацию о блокировке из ответа
            candidates = data.get("candidates") or []
            candidate = candidates[0] if candidates else {}
            finish_reason = candidate.get("finishReason")
            safety_ratings = candidate.get("safetyRatings") or []
            prompt_feedback = data.get("promptFeedback") or {}
            block_reason = prompt_feedback.get("blockReason")

            parts_resp = candidate.get("content", {}).get("parts", [])
            inline = next((p.get("inlineData", {}).get("data") for p in parts_resp if p.get("inlineData")), None)
            if inline:
                imgs.append(base64.b64decode(inline))
                continue
            file_uri = next((p.get("fileData", {}).get("fileUri") for p in parts_resp if p.get("fileData")), None)
            if file_uri:
                fr = client.get(file_uri)
                fr.raise_for_status()
                imgs.append(fr.content)
                continue

            # Если изображение не получено - логируем и выбрасываем информативную ошибку
            logger.error(
                f"[GEMINI_IMAGE] Изображение не получено (итерация {i+1}/{quantity}). "
                f"finishReason={finish_reason}, blockReason={block_reason}, "
                f"safetyRatings={safety_ratings}, promptFeedback={prompt_feedback}"
            )
            logger.debug(f"[GEMINI_IMAGE] Полный ответ API: {json.dumps(data, ensure_ascii=False)[:2000]}")

            # Формируем понятное сообщение об ошибке
            error_parts = []
            if finish_reason and finish_reason != "STOP":
                error_parts.append(f"finishReason: {finish_reason}")
            if block_reason:
                error_parts.append(f"blockReason: {block_reason}")
            if safety_ratings:
                high_risk = [r for r in safety_ratings if r.get("probability") in ("HIGH", "MEDIUM")]
                if high_risk:
                    categories = [r.get("category", "UNKNOWN") for r in high_risk]
                    error_parts.append(f"safetyCategories: {', '.join(categories)}")

            if error_parts:
                error_msg = f"Gemini отклонил запрос: {'; '.join(error_parts)}"
            else:
                error_msg = "Gemini не вернул изображение без указания причины"

            raise GeminiBlockedError(
                error_msg,
                finish_reason=finish_reason,
                block_reason=block_reason,
                safety_ratings=safety_ratings
            )

    return imgs

def openai_generate_images(
    prompt: str,
    quantity: int,
    *,
    params: Optional[Dict[str, Any]] = None,
    model_name: Optional[str] = None,
    generation_type: str = "text2image",
    input_images: Optional[List[Dict[str, Any]]] = None,
    image_mode: Optional[str] = None,
) -> List[bytes]:
    """Генерация изображений через OpenAI GPT-Image API."""
    logger.info(f"[OPENAI_IMAGE] Начало генерации: type={generation_type}, quantity={quantity}, prompt={prompt[:100]}...")
    if not settings.OPENAI_API_KEY:
        logger.error("[OPENAI_IMAGE] OPENAI_API_KEY не задан")
        raise ValueError("OPENAI_API_KEY is not configured for OpenAI image generation")

    effective_params = dict(params or {})
    payload_base: Dict[str, Any] = {
        "model": effective_params.get("model") or model_name or getattr(settings, "OPENAI_IMAGE_MODEL", "gpt-image-1"),
        "prompt": prompt,
        "n": 1,
    }

    def _normalize_size(value: Any) -> Optional[str]:
        allowed_sizes = {
            "512x512",
            "768x1024",
            "1024x768",
            "1024x1024",
            "1024x1536",
            "1536x1024",
        }
        if not value:
            return "1024x1024"
        text = str(value).lower()
        if text == "auto":
            return "auto"
        if text in allowed_sizes:
            return text
        if re.fullmatch(r"\d+x\d+", text):
            return "1024x1024"
        return "1024x1024"

    size_value = _normalize_size(effective_params.get("size"))
    if size_value:
        payload_base["size"] = size_value

    allowed_quality = {"low", "medium", "high", "auto"}
    quality_value = str(effective_params.get("quality", "auto")).lower()
    if quality_value not in allowed_quality:
        quality_value = "auto"
    payload_base["quality"] = quality_value

    if effective_params.get("background") == "transparent":
        payload_base["background"] = "transparent"

    image_format = effective_params.get("format") or effective_params.get("output_format")
    if image_format:
        fmt = str(image_format).lower()
        if fmt == "jpg":
            fmt = "jpeg"
        if fmt in {"png", "jpeg", "webp"}:
            payload_base["format"] = fmt

            compression = effective_params.get("output_compression")
            if compression is not None and fmt in {"jpeg", "webp"}:
                try:
                    comp_value = int(compression)
                except (TypeError, ValueError):
                    comp_value = None
                if comp_value is not None:
                    comp_value = max(0, min(100, comp_value))
                    payload_base["output_compression"] = comp_value

    moderation_value = effective_params.get("moderation")
    if moderation_value:
        moderation_value = str(moderation_value).lower()
        if moderation_value in {"auto", "low"}:
            payload_base["moderation"] = moderation_value

    if effective_params.get("seed") is not None:
        payload_base["seed"] = effective_params["seed"]

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
    }
    if getattr(settings, "OPENAI_ORGANIZATION", None):
        headers["OpenAI-Organization"] = settings.OPENAI_ORGANIZATION
    if getattr(settings, "OPENAI_PROJECT_ID", None):
        headers["OpenAI-Project"] = settings.OPENAI_PROJECT_ID
    json_headers = {**headers, "Content-Type": "application/json"}

    def _format_openai_error(resp: httpx.Response) -> str:
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                err = payload.get("error")
                if isinstance(err, dict):
                    return err.get("message") or str(err)
                if isinstance(err, str):
                    return err
                return json.dumps(payload)
            return resp.text
        except Exception:  # pragma: no cover - fallback path
            return resp.text


    def _call_openai_image_edit(
        client: httpx.Client,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        prompt: str,
        input_images: List[Dict[str, Any]],
    ) -> List[bytes]:
        if not input_images:
            raise ValueError("Для режима image2image необходимо добавить изображение.")
        files = []
        for idx, image in enumerate(input_images):
            content = image.get("content")
            if not content:
                continue
            filename = image.get("filename") or f"image_{idx}.png"
            mime = image.get("mime_type") or "image/png"
            files.append(("image[]", (filename, content, mime)))
        if not files:
            raise ValueError("Не удалось подготовить изображения для режима image2image.")

        data_fields: Dict[str, str] = {
            "prompt": prompt,
            "model": payload.get("model", "gpt-image-1"),
            "n": str(payload.get("n", 1)),
        }
        for key in ("size", "quality", "background", "format", "output_compression", "moderation", "seed"):
            if key in payload:
                data_fields[key] = str(payload[key])

        logger.debug(f"[OPENAI_IMAGE] Edit payload: {json.dumps(data_fields, ensure_ascii=False)[:500]}")
        response = client.post(
            OPENAI_IMAGE_EDIT_URL,
            headers=headers,
            data=data_fields,
            files=files,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _format_openai_error(exc.response)
            logger.error(f"[OPENAI_IMAGE] HTTP ошибка при edit: status={exc.response.status_code}, detail={detail[:500]}")
            raise ValueError(f"OpenAI image generation failed: {detail}") from exc

        data = response.json()
        logger.info(f"[OPENAI_IMAGE] Edit response: {json.dumps(data, ensure_ascii=False)[:500]}")
        entries = data.get("data") or []
        results: List[bytes] = []
        for entry in entries:
            if entry.get("b64_json"):
                results.append(base64.b64decode(entry["b64_json"]))
        logger.info(f"[OPENAI_IMAGE] Edit завершен: получено {len(results)} изображений")
        return results

    imgs: List[bytes] = []
    with httpx.Client(timeout=120) as client:
        if generation_type == "image2image":
            edit_payload = payload_base.copy()
            edit_payload["n"] = quantity
            return _call_openai_image_edit(
                client=client,
                headers=headers,
                payload=edit_payload,
                prompt=prompt,
                input_images=input_images or [],
            )

        logger.debug(f"[OPENAI_IMAGE] Generate payload: {json.dumps(payload_base, ensure_ascii=False)[:500]}")
        for idx in range(quantity):
            logger.debug(f"[OPENAI_IMAGE] Генерация изображения {idx + 1}/{quantity}")
            response = client.post(OPENAI_IMAGE_URL, headers=json_headers, json=payload_base)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = _format_openai_error(exc.response)
                logger.error(f"[OPENAI_IMAGE] HTTP ошибка: status={exc.response.status_code}, detail={detail[:500]}")
                raise ValueError(f"OpenAI image generation failed: {detail}") from exc
            data = response.json()
            logger.debug(f"[OPENAI_IMAGE] Response {idx + 1}: {json.dumps(data, ensure_ascii=False)[:300]}")
            entries = data.get("data") or []
            if not entries:
                logger.warning(f"[OPENAI_IMAGE] Пустой ответ для изображения {idx + 1}")
                continue
            entry = entries[0]
            if entry.get("b64_json"):
                imgs.append(base64.b64decode(entry["b64_json"]))
                continue
            if entry.get("url"):
                logger.debug(f"[OPENAI_IMAGE] Скачивание по URL: {entry['url'][:100]}...")
                file_resp = client.get(entry["url"])
                file_resp.raise_for_status()
                imgs.append(file_resp.content)
                continue
    logger.info(f"[OPENAI_IMAGE] Генерация завершена: получено {len(imgs)} изображений")
    return imgs


def midjourney_generate_images(
    prompt: str,
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
    *,
    generation_type: str = "text2image",
    input_images: Optional[List[Dict[str, Any]]] = None,
) -> List[bytes]:
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"[MIDJOURNEY_KIE] Начало генерации: prompt={prompt[:100]}..., quantity={quantity}, generation_type={generation_type}")
    logger.info(f"[MIDJOURNEY_KIE] Параметры: {params}")

    api_key = getattr(settings, "MIDJOURNEY_KIE_API_KEY", None)
    if not api_key:
        logger.error("[MIDJOURNEY_KIE] MIDJOURNEY_KIE_API_KEY не задан")
        raise ValueError("API-ключ Midjourney не задан.")

    base_url = getattr(settings, "MIDJOURNEY_KIE_BASE_URL", KIE_DEFAULT_BASE_URL) or KIE_DEFAULT_BASE_URL
    base_url = base_url.rstrip("/")
    text_model = getattr(settings, "MIDJOURNEY_KIE_TEXT_MODEL", "midjourney/v6-text-to-image")
    image_model = getattr(settings, "MIDJOURNEY_KIE_IMAGE_MODEL", "midjourney/v6-image-to-image")
    poll_interval = int(getattr(settings, "MIDJOURNEY_KIE_POLL_INTERVAL", 5))
    poll_timeout = int(getattr(settings, "MIDJOURNEY_KIE_POLL_TIMEOUT", 12 * 60))
    timeout_raw = getattr(settings, "MIDJOURNEY_KIE_REQUEST_TIMEOUT", None)
    request_timeout = httpx.Timeout(float(timeout_raw), connect=10.0) if timeout_raw else httpx.Timeout(120.0, connect=10.0)

    if generation_type == "image2image" and not input_images:
        raise ValueError("Для режима image2image необходимо загрузить хотя бы одно изображение.")

    model_name = text_model if generation_type != "image2image" else image_model
    if not model_name:
        raise ValueError("Не задана модель Midjourney.")

    results: List[bytes] = []
    for _ in range(quantity):
        payload = _build_midjourney_input(
            prompt=prompt,
            params=params or {},
            generation_type=generation_type,
            input_images=input_images or [],
        )

        payload["version"] = payload.get("version") or params.get("version") or "7"
        payload["taskType"] = payload.get("taskType") or (
            "mj_img2img" if generation_type == "image2image" else "mj_txt2img"
        )
        payload["speed"] = payload.get("speed") or params.get("speed") or "fast"
        payload["model"] = model_name

        logger.info(f"[MIDJOURNEY_KIE] Отправка запроса на {base_url}/api/v1/mj/generate")
        logger.debug(f"[MIDJOURNEY_KIE] Payload: {json.dumps(payload, ensure_ascii=False)[:500]}")

        create_resp = _kie_api_request(
            base_url=base_url,
            api_key=api_key,
            method="POST",
            endpoint="/api/v1/mj/generate",
            json_payload=payload,
            timeout=request_timeout,
        )

        logger.info(f"[MIDJOURNEY_KIE] Ответ от API: code={create_resp.get('code')}, msg={create_resp.get('msg')}")

        if create_resp.get("code") != 200:
            logger.error(f"[MIDJOURNEY_KIE] Ошибка создания задачи: {create_resp}")
            raise ValueError(f"Midjourney: ошибка создания задачи: {create_resp}")
        data = create_resp.get("data") or {}
        task_id = data.get("taskId")
        if not task_id:
            logger.error("[MIDJOURNEY_KIE] API не вернул идентификатор задачи")
            raise ValueError("Midjourney не вернул идентификатор задачи.")

        logger.info(f"[MIDJOURNEY_KIE] Задача создана: task_id={task_id}")

        job_data = _kie_poll_task(
            base_url=base_url,
            api_key=api_key,
            task_id=task_id,
            timeout=request_timeout,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
            endpoint="/api/v1/mj/record-info",
        )
        urls = _kie_extract_result_urls(job_data)
        if not urls:
            raise ValueError("Midjourney не вернул ссылки на изображения.")

        added = False
        for url in urls:
            try:
                image_bytes = _download_binary_file(url)
            except Exception:
                continue
            results.append(image_bytes)
            added = True

        if not added:
            raise ValueError("Midjourney не удалось загрузить изображения по ссылкам.")

    return results


def generate_images_for_model(
    model,
    prompt: str,
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
    *,
    generation_type: str = "text2image",
    input_images: Optional[List[Dict[str, Any]]] = None,
    image_mode: Optional[str] = None,
) -> List[bytes]:
    """Вызывает подходящего провайдера генерации на основе модели."""
    provider = getattr(model, "provider", None)
    slug = getattr(model, "slug", "")
    supports_image_input = bool(getattr(model, "supports_image_input", False))
    if generation_type == "image2image" and not supports_image_input:
        raise ValueError(f"Модель {slug or provider or 'unknown'} не поддерживает загрузку изображений.")
    if generation_type == "image2image" and not input_images:
        raise ValueError("Для режима image2image необходимо передать хотя бы одно изображение.")

    merged_params: Dict[str, Any] = {}
    if getattr(model, "default_params", None):
        merged_params.update(model.default_params)
    if params:
        merged_params.update(params)

    if provider == "openai_image":
        return openai_generate_images(
            prompt,
            quantity,
            params=merged_params,
            model_name=model.api_model_name,
            generation_type=generation_type,
            input_images=input_images,
            image_mode=image_mode,
        )
    elif provider in {"gemini", "gemini_vertex"}:
        return gemini_generate_images(
            prompt,
            quantity,
            params=merged_params,
            model_name=getattr(model, "api_model_name", None),
            generation_type=generation_type,
            input_images=input_images or [],
            image_mode=image_mode,
        )
    elif provider == "vertex":
        if generation_type == "image2image":
            return vertex_edit_images(prompt, quantity, input_images or [], merged_params, image_mode=image_mode)
        return vertex_generate_images(prompt, quantity, params=merged_params)
    elif provider == "midjourney":
        return midjourney_generate_images(
            prompt,
            quantity,
            params=merged_params,
            generation_type=generation_type,
            input_images=input_images or [],
        )

    raise ValueError(f"Провайдер {provider or 'unknown'} не поддерживает генерацию изображений.")


def generate_images(prompt: str, quantity: int) -> List[bytes]:
    """Старый интерфейс для обратной совместимости (использует модель из аргумента, а не из env)."""
    raise ValueError("generate_images требует явного указания модели через AIModel; используйте generate_images_for_model.")

def supabase_upload_png(content: bytes) -> str:
    """Загружает PNG в Supabase Storage и возвращает ПУБЛИЧНЫЙ URL."""
    if create_client is None:
        raise RuntimeError("Supabase client library не установлена")
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    key = f"images/{uuid.uuid4().hex}.png"
    # upload (важно указать content-type)
    supabase.storage.from_(settings.SUPABASE_BUCKET).upload(
        path=key, file=content, file_options={"content-type": "image/png", "upsert": "true"}
    )
    # public URL
    public = supabase.storage.from_(settings.SUPABASE_BUCKET).get_public_url(key)
    return public  # dict или строка — у lib v2 возвращается объект; возьмём .get("publicUrl") при необходимости


def supabase_upload_video(content: bytes, mime_type: str = "video/mp4") -> str:
    """Загружает видео в Supabase Storage и возвращает публичный URL."""
    if create_client is None:
        raise RuntimeError("Supabase client library не установлена")
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    extension = "mp4" if "mp4" in mime_type else "webm"
    key = f"videos/{uuid.uuid4().hex}.{extension}"
    supabase.storage.from_(settings.SUPABASE_VIDEO_BUCKET).upload(
        path=key,
        file=content,
        file_options={"content-type": mime_type, "upsert": "true"},
    )
    public = supabase.storage.from_(settings.SUPABASE_VIDEO_BUCKET).get_public_url(key)
    return public


def _build_midjourney_input(
    *,
    prompt: str,
    params: Dict[str, Any],
    generation_type: str,
    input_images: List[Dict[str, Any]],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "prompt": prompt,
    }

    task_type = "mj_img2img" if generation_type == "image2image" else "mj_txt2img"
    payload["taskType"] = task_type

    aspect_ratio = params.get("aspect_ratio") or params.get("aspectRatio")
    if aspect_ratio:
        payload["aspectRatio"] = str(aspect_ratio)

    for key, field in (
        ("speed", "speed"),
        ("version", "version"),
        ("variety", "variety"),
        ("stylization", "stylization"),
        ("weirdness", "weirdness"),
        ("watermark", "waterMark"),
        ("waterMark", "waterMark"),
        ("enableTranslation", "enableTranslation"),
        ("callBackUrl", "callBackUrl"),
        ("ow", "ow"),
        ("videoBatchSize", "videoBatchSize"),
        ("motion", "motion"),
    ):
        value = params.get(key)
        if value is not None:
            payload[field] = value

    if params.get("negative_prompt") or params.get("negativePrompt"):
        payload["negativePrompt"] = params.get("negative_prompt") or params.get("negativePrompt")

    if generation_type == "image2image":
        payload["fileUrls"] = _upload_reference_images_for_midjourney(input_images)

    mj_opts = params.get("midjourney_options")
    if isinstance(mj_opts, dict):
        payload.update(mj_opts)

    return payload


def _upload_reference_images_for_midjourney(input_images: List[Dict[str, Any]]) -> List[str]:
    urls: List[str] = []
    for entry in input_images:
        content = entry.get("content")
        if not content:
            continue
        upload_obj = supabase_upload_png(content)
        if isinstance(upload_obj, dict):
            url = upload_obj.get("public_url") or upload_obj.get("publicUrl") or upload_obj.get("publicURL")
        else:
            url = upload_obj
        if url:
            urls.append(url)
    if not urls:
        raise ValueError("Не удалось загрузить изображения для Midjourney.")
    return urls


def _kie_api_request(
    *,
    base_url: str,
    api_key: str,
    method: str,
    endpoint: str,
    json_payload: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: httpx.Timeout,
) -> Dict[str, Any]:
    url = endpoint if endpoint.startswith("http") else f"{base_url}{endpoint}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.request(method, url, headers=headers, json=json_payload, params=params)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:  # type: ignore[attr-defined]
        detail = _format_kie_error(exc.response)
        raise ValueError(f"Сервис Midjourney вернул ошибку: {detail}") from exc
    except httpx.HTTPError as exc:  # type: ignore[attr-defined]
        raise ValueError(f"Ошибка обращения к сервису Midjourney: {exc}") from exc

    try:
        return response.json()
    except ValueError as exc:  # pragma: no cover
        raise ValueError(f"Сервис Midjourney вернул некорректный ответ: {response.text}") from exc


def _kie_poll_task(
    *,
    base_url: str,
    api_key: str,
    task_id: str,
    timeout: httpx.Timeout,
    poll_interval: int,
    poll_timeout: int,
    endpoint: str = "/api/v1/jobs/recordInfo",
) -> Dict[str, Any]:
    started = time.monotonic()
    while True:
        response = _kie_api_request(
            base_url=base_url,
            api_key=api_key,
            method="GET",
            endpoint=endpoint,
            params={"taskId": task_id},
            timeout=timeout,
        )
        if response.get("code") != 200:
            raise ValueError(f"Midjourney: ошибка статуса задачи: {response}")
        data = response.get("data") or {}
        if "state" in data:
            state = (data.get("state") or "").lower()
            if state == "success":
                return data
            if state == "fail":
                fail_msg = data.get("failMsg") or data.get("msg") or "Задача Midjourney завершилась с ошибкой."
                raise ValueError(f"Задача Midjourney завершилась с ошибкой: {fail_msg}")
        elif "successFlag" in data:
            flag = data.get("successFlag")
            if flag == 1:
                return data
            if flag in (2, 3):
                fail_msg = data.get("errorMessage") or data.get("msg") or "Задача Midjourney завершилась с ошибкой."
                raise ValueError(f"Задача Midjourney завершилась с ошибкой: {fail_msg}")
        if time.monotonic() - started > poll_timeout:
            raise ValueError("Ожидание результата Midjourney превысило установленный таймаут.")
        time.sleep(max(1, poll_interval))


def _kie_extract_result_urls(payload: Dict[str, Any]) -> List[str]:
    urls: List[str] = []
    result_json = payload.get("resultJson")
    if isinstance(result_json, dict):
        maybe_urls = result_json.get("resultUrls")
        if isinstance(maybe_urls, list):
            urls.extend(maybe_urls)
    elif isinstance(result_json, str):
        try:
            parsed = json.loads(result_json)
            maybe_urls = parsed.get("resultUrls")
            if isinstance(maybe_urls, list):
                urls.extend(maybe_urls)
        except json.JSONDecodeError:
            pass
    result_info = payload.get("resultInfoJson")
    if isinstance(result_info, dict):
        maybe_urls = result_info.get("resultUrls")
        if isinstance(maybe_urls, list):
            for item in maybe_urls:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict):
                    maybe_url = item.get("resultUrl") or item.get("url")
                    if maybe_url:
                        urls.append(maybe_url)
    return urls


def _download_binary_file(url: str) -> bytes:
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:  # type: ignore[attr-defined]
        raise ValueError(f"Не удалось скачать файл по ссылке {url}: {exc}") from exc


def _format_kie_error(response: Optional[httpx.Response]) -> str:
    if not response:
        return ""
    try:
        data = response.json()
        if isinstance(data, dict):
            return json.dumps(data, ensure_ascii=False)
    except Exception:
        pass
    return response.text if response else ""


def _load_service_account_info() -> Dict[str, Any]:
    raw = getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS_JSON", "") or ""
    if raw:
        for candidate in (raw, raw.strip()):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                try:
                    decoder = JSONDecoder(strict=False)
                    return decoder.decode(candidate)
                except json.JSONDecodeError:
                    pass
        # base64 encoded JSON
        try:
            decoded = base64.b64decode(raw).decode()
            return json.loads(decoded)
        except Exception:
            pass
        # treat as path
        if os.path.exists(raw):
            with open(raw, "r", encoding="utf-8") as f:
                return json.load(f)

    path = getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", None)
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise ValueError(
        "GOOGLE_APPLICATION_CREDENTIALS_JSON не содержит валидный JSON. Передайте содержимое файла, "
        "base64 или путь к файлу через GOOGLE_APPLICATION_CREDENTIALS."
    )
_VERTEX_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]


def _authorized_vertex_session() -> AuthorizedSession:
    """Создает авторизованную сессию для Vertex AI с логированием."""
    print("[VERTEX] Loading service account credentials...", flush=True)
    creds_info = _load_service_account_info()
    print(f"[VERTEX] Credentials loaded. Project from creds: {creds_info.get('project_id', 'N/A')}", flush=True)
    print(f"[VERTEX] Service account email: {creds_info.get('client_email', 'N/A')}", flush=True)
    
    credentials = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=_VERTEX_SCOPES,
    )
    print(f"[VERTEX] Credentials initialized with scopes: {_VERTEX_SCOPES}", flush=True)
    return AuthorizedSession(credentials)


def _vertex_auth_headers(api_key: Optional[str]) -> Tuple[Dict[str, str], Optional[Dict[str, Any]]]:
    """
    Готовит заголовки авторизации для Vertex Imagen.
    Приоритет: API Key (x-goog-api-key) -> Service Account (Bearer).
    """
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        print(f"[VERTEX] Using API Key authentication (key starts with {api_key[:6]}...)", flush=True)
        headers["x-goog-api-key"] = api_key
        return headers, None

    print("[VERTEX] Using Service Account authentication for Imagen", flush=True)
    creds_info = _load_service_account_info()
    credentials = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=_VERTEX_SCOPES,
    )
    from google.auth.transport.requests import Request
    credentials.refresh(Request())
    if not credentials.token:
        raise ValueError("Не удалось получить access token для Vertex AI")
    headers["Authorization"] = f"Bearer {credentials.token}"
    return headers, creds_info


def _normalize_imagen_size(raw_size: Optional[Any]) -> Optional[str]:
    """Приводит размер изображения к допустимому формату Imagen."""
    if not raw_size:
        return None
    value = str(raw_size).upper()
    if value in {"1K", "2K"}:
        return value
    if value == "4K":
        # Imagen API поддерживает 1K/2K, 4K маппим на максимально доступный размер.
        print("[VERTEX] 4K не поддерживается Imagen API, используем 2K", flush=True)
        return "2K"
    return None


def _build_imagen_parameters(quantity: int, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Готовит объект parameters для Imagen predict согласно документации."""
    parameters: Dict[str, Any] = {"sampleCount": max(1, min(quantity, 4))}
    params = params or {}

    aspect_ratio = params.get("aspect_ratio") or params.get("aspectRatio")
    allowed_aspects = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9"}
    if aspect_ratio in allowed_aspects:
        parameters["aspectRatio"] = aspect_ratio

    image_size = params.get("image_size") or params.get("imageSize") or params.get("quality")
    normalized_size = _normalize_imagen_size(image_size)
    if normalized_size:
        parameters["sampleImageSize"] = normalized_size

    return parameters


def _decode_imagen_predictions(data: Dict[str, Any]) -> List[bytes]:
    """Декодирует base64 из predictions Imagen predict."""
    predictions = data.get("predictions") or []
    results: List[bytes] = []
    for prediction in predictions:
        b64_data = prediction.get("bytesBase64Encoded") or prediction.get("bytes_base64_encoded")
        if b64_data:
            try:
                results.append(base64.b64decode(b64_data))
            except Exception:
                continue
    return results


def _resolve_imagen_model_name(model_name: Optional[str], default_model: str) -> str:
    """
    Для Nano Banana Pro жёстко уходим на Imagen-модели.
    Любые устаревшие gemini-3.* image ID заменяем на актуальную Imagen.
    """
    if not model_name:
        return default_model
    tail = model_name.rsplit("/", 1)[-1]
    if tail.startswith("gemini-3"):
        return default_model
    return model_name


def _build_imagen_reference_images(
    input_images: List[Dict[str, Any]],
    params: Optional[Dict[str, Any]],
    image_mode: Optional[str],
) -> Tuple[List[Dict[str, Any]], bool]:
    """Формирует referenceImages для Imagen predict (image2image/редактирование)."""
    params = params or {}
    raw_entry = next((img for img in input_images if img.get("role") == "raw"), None)
    mask_entry = next((img for img in input_images if img.get("role") == "mask"), None)

    subject_entries = []
    for img in input_images:
        if img.get("role") in {"raw", "mask"}:
            continue
        if img.get("content"):
            subject_entries.append(img)

    reference_images: List[Dict[str, Any]] = []
    next_id = 1

    def _encode(entry: Dict[str, Any]) -> Optional[str]:
        content = entry.get("content")
        if not content:
            return None
        try:
            return base64.b64encode(content).decode()
        except Exception:
            return None

    if raw_entry:
        raw_b64 = _encode(raw_entry)
        if raw_b64:
            reference_images.append(
                {
                    "referenceType": "REFERENCE_TYPE_RAW",
                    "referenceId": next_id,
                    "referenceImage": {"bytesBase64Encoded": raw_b64},
                }
            )
            next_id += 1

    has_mask = False
    if raw_entry and mask_entry:
        mask_b64 = _encode(mask_entry)
        if mask_b64:
            has_mask = True
            reference_images.append(
                {
                    "referenceType": "REFERENCE_TYPE_MASK",
                    "referenceId": next_id,
                    "referenceImage": {"bytesBase64Encoded": mask_b64},
                    "maskImageConfig": {
                        "maskMode": params.get("mask_mode", "MASK_MODE_USER_PROVIDED"),
                        "dilation": params.get("mask_dilation", 0.01),
                    },
                }
            )
            next_id += 1

    for idx, entry in enumerate(subject_entries, start=next_id):
        encoded = _encode(entry)
        if not encoded:
            continue
        reference_images.append(
            {
                "referenceType": "REFERENCE_TYPE_SUBJECT",
                "referenceId": idx,
                "referenceImage": {"bytesBase64Encoded": encoded},
                "subjectImageConfig": {
                    "subjectDescription": params.get("subject_description", f"reference {idx}"),
                    "subjectType": params.get("subject_type", "SUBJECT_TYPE_DEFAULT"),
                },
            }
        )

    if not reference_images:
        raise ValueError("Не удалось подготовить изображения для Vertex edit.")

    return reference_images, has_mask


def _normalize_image_model_name(model_name: str) -> str:
    """Нормализует название модели (устраняет устаревшие ID без версии)."""
    print(f"[DEBUG] Normalizing image model name: '{model_name}'", flush=True)
    # Принудительно убираем .0, так как оно приходит из конфигурации, но не поддерживается API
    replacements = {
        "gemini-3.0-pro-image-preview": "gemini-3-pro-image-preview",
        "gemini-3.0-pro-image": "gemini-3-pro-image",
    }
    return replacements.get(model_name, model_name)


def _vertex_model_path(model_name: Optional[str]) -> str:
    base = (model_name or DEFAULT_VERTEX_IMAGE_MODEL).strip().lstrip("/")
    tail = base.rsplit("/", 1)[-1]
    tail = _normalize_image_model_name(tail)
    return f"publishers/google/models/{tail}"


def _gemini_model_name(model_path: Optional[str]) -> str:
    """Возвращает короткое имя модели для Generative Language API."""
    tail = (model_path or DEFAULT_VERTEX_IMAGE_MODEL).strip().strip("/")
    tail = tail.rsplit("/", 1)[-1]
    return _normalize_image_model_name(tail)


def _vertex_project_and_location(creds_info: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """Определяет проект/локацию Vertex с приоритетом на переменные окружения."""
    project = (
        getattr(settings, "VERTEX_PROJECT_ID", None)
        or getattr(settings, "GCP_PROJECT_ID", None)
        or (creds_info or {}).get("project_id")
    )
    location = (
        getattr(settings, "VERTEX_LOCATION", None)
        or getattr(settings, "GCP_LOCATION", None)
        or "us-central1"
    )
    if not project:
        # Фоллбек как раньше, чтобы не падать при отсутствии настроек (диагностика через логи)
        project = "gen-lang-client-0838548551"
    return project, location


def gemini_vertex_edit(
    prompt: str,
    quantity: int,
    input_images: List[Dict[str, Any]],
    params: Optional[Dict[str, Any]] = None,
    *,
    model_name: Optional[str] = None,
) -> List[bytes]:
    if not input_images:
        raise ValueError("Для режима image2image необходимо загрузить изображение.")

    params = params or {}
    default_model = getattr(settings, "VERTEX_IMAGE_EDIT_MODEL", "imagen-3.0-capability-001")
    effective_model = _resolve_imagen_model_name(model_name, default_model)
    model_path = _vertex_model_path(effective_model)

    vertex_api_key = getattr(settings, "NANO_BANANA_API_KEY", None)
    headers, creds_info = _vertex_auth_headers(vertex_api_key)
    project_id, location = _vertex_project_and_location(creds_info)

    image_mode = params.get("image_mode")
    reference_images, has_mask = _build_imagen_reference_images(input_images, params, image_mode)
    parameters = _build_imagen_parameters(quantity, params)
    if has_mask:
        parameters["editMode"] = params.get("edit_mode") or "EDIT_MODE_INPAINT_INSERTION"

    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/{model_path}:predict"
    payload = {
        "instances": [
            {
                "prompt": prompt,
                "referenceImages": reference_images,
            }
        ],
        "parameters": parameters,
    }

    print(f"[IMAGE_EDIT] Vertex Imagen edit → model={model_path}, project={project_id}, location={location}", flush=True)
    print(f"[IMAGE_EDIT] Input images: {len(input_images)}, parameters: {json.dumps(parameters, ensure_ascii=False)}", flush=True)

    response = httpx.post(url, headers=headers, json=payload, timeout=120.0)
    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json()
        except ValueError:
            pass
        print(f"[IMAGE_EDIT] ✗ Vertex Imagen error ({response.status_code}): {str(detail)[:500]}", flush=True)
        raise ValueError(f"Vertex Imagen error ({response.status_code}): {detail}")

    data = response.json()
    results = _decode_imagen_predictions(data)

    if not results:
        print(f"[IMAGE_EDIT] ✗ Vertex Imagen вернул пустой результат: {str(data)[:300]}", flush=True)
        raise ValueError("Vertex Imagen не вернул изображений.")

    print(f"[IMAGE_EDIT] ✓ Получено изображений: {len(results)}", flush=True)
    return results


def gemini_vertex_generate(
    prompt: str,
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
    *,
    model_name: Optional[str] = None,
) -> List[bytes]:
    params = params or {}
    default_model = getattr(settings, "VERTEX_IMAGE_GENERATE_MODEL", DEFAULT_VERTEX_IMAGE_MODEL)
    effective_model = _resolve_imagen_model_name(model_name, default_model)
    model_path = _vertex_model_path(effective_model)

    vertex_api_key = getattr(settings, "NANO_BANANA_API_KEY", None)
    headers, creds_info = _vertex_auth_headers(vertex_api_key)
    project_id, location = _vertex_project_and_location(creds_info)

    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/{model_path}:predict"
    parameters = _build_imagen_parameters(quantity, params)
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": parameters,
    }

    print(f"[IMAGE_GEN] Vertex Imagen request → model={model_path}, project={project_id}, location={location}", flush=True)
    print(f"[IMAGE_GEN] Parameters: {json.dumps(parameters, ensure_ascii=False)}", flush=True)

    response = httpx.post(url, headers=headers, json=payload, timeout=120.0)
    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json()
        except ValueError:
            pass
        print(f"[IMAGE_GEN] ✗ Vertex Imagen error ({response.status_code}): {str(detail)[:500]}", flush=True)
        raise ValueError(f"Vertex Imagen error ({response.status_code}): {detail}")

    data = response.json()
    results = _decode_imagen_predictions(data)
    if not results:
        print(f"[IMAGE_GEN] ✗ Vertex Imagen вернул пустой результат: {str(data)[:300]}", flush=True)
        raise ValueError("Vertex Imagen не вернул изображений.")

    print(f"[IMAGE_GEN] ✓ Получено изображений: {len(results)}", flush=True)
    return results
