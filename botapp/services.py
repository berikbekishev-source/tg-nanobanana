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
DEFAULT_VERTEX_IMAGE_MODEL = "gemini-2.5-flash-image"

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

def gemini_generate_images(prompt: str, quantity: int, params: Optional[Dict[str, Any]] = None) -> List[bytes]:
    """Возвращает список байтов изображений (разбираем inlineData или fileUri)."""
    model = settings.GEMINI_IMAGE_MODEL or "gemini-2.5-flash-image"
    url = GEMINI_URL_TMPL.format(model=model)
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if params:
        generation_config = {}
        for key in ("temperature", "top_p", "top_k"):
            if key in params:
                generation_config[key] = params[key]
        if generation_config:
            payload["generationConfig"] = generation_config

    imgs: List[bytes] = []
    with httpx.Client(timeout=120) as client:
        for _ in range(quantity):
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])  # inlineData | fileData
            # 1) inlineData
            inline = next((p.get("inlineData", {}).get("data") for p in parts if p.get("inlineData")), None)
            if inline:
                imgs.append(base64.b64decode(inline))
                continue
            # 2) fileUri
            file_uri = next((p.get("fileData", {}).get("fileUri") for p in parts if p.get("fileData")), None)
            if file_uri:
                fr = client.get(file_uri)
                fr.raise_for_status()
                imgs.append(fr.content)
                continue
            # иначе пустой ответ — пропускаем
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
    if not settings.OPENAI_API_KEY:
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
            raise ValueError(f"OpenAI image generation failed: {detail}") from exc

        data = response.json()
        entries = data.get("data") or []
        results: List[bytes] = []
        for entry in entries:
            if entry.get("b64_json"):
                results.append(base64.b64decode(entry["b64_json"]))
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

        for _ in range(quantity):
            response = client.post(OPENAI_IMAGE_URL, headers=json_headers, json=payload_base)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = _format_openai_error(exc.response)
                raise ValueError(f"OpenAI image generation failed: {detail}") from exc
            data = response.json()
            entries = data.get("data") or []
            if not entries:
                continue
            entry = entries[0]
            if entry.get("b64_json"):
                imgs.append(base64.b64decode(entry["b64_json"]))
                continue
            if entry.get("url"):
                file_resp = client.get(entry["url"])
                file_resp.raise_for_status()
                imgs.append(file_resp.content)
                continue
    return imgs


def midjourney_generate_images(
    prompt: str,
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
    *,
    generation_type: str = "text2image",
    input_images: Optional[List[Dict[str, Any]]] = None,
) -> List[bytes]:
    api_key = getattr(settings, "MIDJOURNEY_KIE_API_KEY", None)
    if not api_key:
        raise ValueError("MIDJOURNEY_KIE_API_KEY не задан.")

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
        raise ValueError("Не задана модель Midjourney (MIDJOURNEY_KIE_TEXT_MODEL/MIDJOURNEY_KIE_IMAGE_MODEL).")

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
        payload["speed"] = payload.get("speed") or params.get("speed") or "relaxed"
        payload["model"] = model_name

        create_resp = _kie_api_request(
            base_url=base_url,
            api_key=api_key,
            method="POST",
            endpoint="/api/v1/mj/generate",
            json_payload=payload,
            timeout=request_timeout,
        )
        if create_resp.get("code") != 200:
            raise ValueError(f"Midjourney (KIE) createTask error: {create_resp}")
        data = create_resp.get("data") or {}
        task_id = data.get("taskId")
        if not task_id:
            raise ValueError("Midjourney (KIE) не вернул идентификатор задачи.")

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
            raise ValueError("Midjourney (KIE) не вернул ссылки на изображения.")

        added = False
        for url in urls:
            try:
                image_bytes = _download_binary_file(url)
            except Exception:
                continue
            results.append(image_bytes)
            added = True

        if not added:
            raise ValueError("Midjourney (KIE) не удалось загрузить изображения по ссылкам.")

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
    elif provider == "vertex":
        if generation_type == "image2image":
            return vertex_edit_images(prompt, quantity, input_images or [], merged_params, image_mode=image_mode)
        return vertex_generate_images(prompt, quantity, params=merged_params)
    elif provider == "gemini":
        if generation_type == "image2image":
            return vertex_edit_images(prompt, quantity, input_images or [], merged_params, image_mode=image_mode)
        return gemini_generate_images(prompt, quantity, params=merged_params)
    elif provider == "gemini_vertex":
        if generation_type == "image2image":
            return gemini_vertex_edit(
                prompt, 
                quantity, 
                input_images or [], 
                merged_params,
                model_name=model.api_model_name,
            )
        return gemini_vertex_generate(
            prompt, 
            quantity, 
            params=merged_params,
            model_name=model.api_model_name,
        )
    elif provider == "midjourney":
        return midjourney_generate_images(
            prompt,
            quantity,
            params=merged_params,
            generation_type=generation_type,
            input_images=input_images or [],
        )

    use_vertex = getattr(settings, 'USE_VERTEX_AI', False)
    if use_vertex:
        if generation_type == "image2image":
            return vertex_edit_images(prompt, quantity, input_images or [], merged_params, image_mode=image_mode)
        return vertex_generate_images(prompt, quantity, params=merged_params)

    if generation_type == "image2image":
        raise ValueError("Выбранная модель не поддерживает режим image2image.")
    return gemini_generate_images(prompt, quantity, params=merged_params)


def generate_images(prompt: str, quantity: int) -> List[bytes]:
    """Старый интерфейс для обратной совместимости (использует глобальные настройки)."""
    use_vertex = getattr(settings, 'USE_VERTEX_AI', False)
    if use_vertex:
        return vertex_generate_images(prompt, quantity)
    return gemini_generate_images(prompt, quantity)

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
        raise ValueError(f"KIE.AI error: {detail}") from exc
    except httpx.HTTPError as exc:  # type: ignore[attr-defined]
        raise ValueError(f"Ошибка обращения к KIE.AI: {exc}") from exc

    try:
        return response.json()
    except ValueError as exc:  # pragma: no cover
        raise ValueError(f"KIE.AI вернул некорректный JSON: {response.text}") from exc


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
            raise ValueError(f"KIE.AI recordInfo error: {response}")
        data = response.get("data") or {}
        if "state" in data:
            state = (data.get("state") or "").lower()
            if state == "success":
                return data
            if state == "fail":
                fail_msg = data.get("failMsg") or data.get("msg") or "KIE.AI task failed."
                raise ValueError(f"Задача KIE.AI завершилась с ошибкой: {fail_msg}")
        elif "successFlag" in data:
            flag = data.get("successFlag")
            if flag == 1:
                return data
            if flag in (2, 3):
                fail_msg = data.get("errorMessage") or data.get("msg") or "KIE.AI task failed."
                raise ValueError(f"Задача KIE.AI завершилась с ошибкой: {fail_msg}")
        if time.monotonic() - started > poll_timeout:
            raise ValueError("Ожидание результата KIE.AI превысило установленный таймаут.")
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


def _normalize_image_model_name(model_name: str) -> str:
    """Нормализует название модели (устраняет устаревшие ID без версии)."""
    replacements = {
        "gemini-3-pro-image-preview": "gemini-3.0-pro-image-preview",
        "gemini-3-pro-image": "gemini-3.0-pro-image",
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


def _build_gemini_payload(parts: List[Dict[str, Any]], quantity: int, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # Собираем contents в формате, рекомендованном Gemini: отдельные сообщения пользователя,
    # чтобы корректно передавать несколько референсов (в т.ч. больше двух).
    contents: List[Dict[str, Any]] = []
    current_parts: List[Dict[str, Any]] = []
    for part in parts:
        is_image_part = "inlineData" in part or "inline_data" in part
        if is_image_part:
            if current_parts:
                contents.append({"role": "user", "parts": current_parts})
                current_parts = []
            contents.append({"role": "user", "parts": [part]})
        else:
            current_parts.append(part)

    if current_parts:
        contents.append({"role": "user", "parts": current_parts})
    elif not contents:
        contents.append({"role": "user", "parts": parts})

    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "candidateCount": max(1, min(quantity, 4)),
        },
    }
    if params:
        generation_config = payload["generationConfig"]
        for key in ("temperature", "top_p", "top_k"):
            if key in params:
                generation_config[key] = params[key]
    return payload


def _gemini_google_api_request(
    *,
    model_name: str,
    parts: List[Dict[str, Any]],
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    session: Optional[AuthorizedSession] = None,
) -> Dict[str, Any]:
    """Запрос в Generative Language API с авторизацией через service account."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = _build_gemini_payload(parts, quantity, params)

    # Детальное логирование структуры contents для диагностики
    print(f"[GEMINI_API] Sending request to: {url}", flush=True)
    contents = payload.get("contents", [])
    if contents:
        for idx, content in enumerate(contents):
            parts_list = content.get("parts", [])
            print(f"[GEMINI_API] Content[{idx}] has {len(parts_list)} parts", flush=True)
            for part_idx, part in enumerate(parts_list):
                if "text" in part:
                    print(f"[GEMINI_API]   Part[{part_idx}]: text ({len(part['text'])} chars)", flush=True)
                elif "inlineData" in part:
                    mime = part["inlineData"].get("mimeType", "unknown")
                    data_len = len(part["inlineData"].get("data", ""))
                    print(f"[GEMINI_API]   Part[{part_idx}]: inlineData ({mime}, {data_len} bytes base64)", flush=True)
                else:
                    print(f"[GEMINI_API]   Part[{part_idx}]: {list(part.keys())}", flush=True)

    if api_key:
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        response = httpx.post(url, headers=headers, json=payload, timeout=120)
    else:
        client = session or _authorized_vertex_session()
        response = client.post(url, json=payload, timeout=120)
    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json()
        except ValueError:
            pass
        raise ValueError(f"Gemini Image API error ({response.status_code}): {detail}")
    return response.json()


def _gemini_vertex_request(
    *,
    project_id: str,
    location: str,
    model_path: str,
    parts: List[Dict[str, Any]],
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Запрос к Vertex AI Imagen/Gemini с поддержкой API Key или Service Account."""
    print(f"[VERTEX] Preparing request to Vertex AI", flush=True)
    print(f"[VERTEX] Project: {project_id}, Location: {location}, Model: {model_path}", flush=True)
    
    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/{model_path}:generateContent"
    payload = _build_gemini_payload(parts, quantity, params)
    
    headers = {"Content-Type": "application/json"}
    
    # Приоритет: API Key > Service Account
    if api_key:
        print(f"[VERTEX] Using API Key authentication (key: {api_key[:20]}...)", flush=True)
        headers["x-goog-api-key"] = api_key
    else:
        print("[VERTEX] Using Service Account authentication", flush=True)
        print("[VERTEX] Loading service account credentials...", flush=True)
        creds_info = _load_service_account_info()
        print(f"[VERTEX] Credentials loaded. Project: {creds_info.get('project_id', 'N/A')}", flush=True)
        print(f"[VERTEX] Service account email: {creds_info.get('client_email', 'N/A')}", flush=True)
        
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=_VERTEX_SCOPES,
        )
        print(f"[VERTEX] Credentials initialized with scopes: {_VERTEX_SCOPES}", flush=True)
        
        # Явно refresh для получения access_token
        from google.auth.transport.requests import Request
        credentials.refresh(Request())
        access_token = credentials.token
        
        print(f"[VERTEX] Access token obtained: {access_token[:50]}..." if access_token else "[VERTEX] ERROR: No access token!", flush=True)
        
        if not access_token:
            raise ValueError("Failed to obtain access token from Google OAuth")
        
        headers["Authorization"] = f"Bearer {access_token}"
    
    print(f"[VERTEX] Sending POST request to: {url}", flush=True)
    print(f"[VERTEX] Payload keys: {list(payload.keys())}", flush=True)

    # Детальное логирование структуры contents для диагностики
    contents = payload.get("contents", [])
    if contents:
        for idx, content in enumerate(contents):
            parts = content.get("parts", [])
            print(f"[VERTEX] Content[{idx}] has {len(parts)} parts", flush=True)
            for part_idx, part in enumerate(parts):
                if "text" in part:
                    print(f"[VERTEX]   Part[{part_idx}]: text ({len(part['text'])} chars)", flush=True)
                elif "inlineData" in part:
                    mime = part["inlineData"].get("mimeType", "unknown")
                    data_len = len(part["inlineData"].get("data", ""))
                    print(f"[VERTEX]   Part[{part_idx}]: inlineData ({mime}, {data_len} bytes base64)", flush=True)
                else:
                    print(f"[VERTEX]   Part[{part_idx}]: {list(part.keys())}", flush=True)

    timeout = httpx.Timeout(120.0, connect=30.0)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload, headers=headers)
    
    print(f"[VERTEX] Response status: {response.status_code}", flush=True)
    
    # Если ошибка - кидаем исключение, чтобы верхний уровень (gemini_vertex_generate) мог его поймать и решить что делать
    if response.status_code != 200:
        detail = response.text
        try:
            detail = response.json()
        except ValueError:
            pass
        print(f"[VERTEX] ERROR Response: {str(detail)[:500]}", flush=True)
        raise ValueError(f"Vertex AI error ({response.status_code}): {detail}")
    
    print(f"[VERTEX] Request successful!", flush=True)
    return response.json()

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

    # Используем переданный model_name или дефолтный из настроек
    model_path = _vertex_model_path(model_name or getattr(settings, "NANO_BANANA_GEMINI_MODEL", None))
    
    # Разделяем ключи:
    vertex_api_key = getattr(settings, "NANO_BANANA_API_KEY", None)
    gemini_api_key = getattr(settings, "GEMINI_API_KEY", None)

    parts: List[Dict[str, Any]] = [{"text": prompt}]
    for image in input_images:
        content = image.get("content")
        if not content:
            continue
        b64_img = base64.b64encode(content).decode()
        parts.append(
            {
                "inlineData": {
                    "mimeType": image.get("mime_type", "image/png"),
                    "data": b64_img,
                }
            }
        )

    # Логируем промт и количество изображений
    print(f"[IMAGE_EDIT] Prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}", flush=True)
    print(f"[IMAGE_EDIT] Input images: {len(input_images)}", flush=True)

    data = None
    vertex_error = None
    creds_info: Optional[Dict[str, Any]] = None
    # Пробуем Vertex по умолчанию
    try:
        print(f"[IMAGE_EDIT] Attempting Vertex AI edit for model {model_path}...", flush=True)
        
        # Если есть Vertex API key, используем его для Vertex AI
        if vertex_api_key:
            print(f"[IMAGE_EDIT] Using Vertex AI API Key", flush=True)
        else:
            print(f"[IMAGE_EDIT] Using Service Account for Vertex AI", flush=True)
            creds_info = _load_service_account_info()
        
        project_id, location = _vertex_project_and_location(creds_info)
        print(f"[IMAGE_EDIT] Using Project: {project_id}, Location: {location}", flush=True)
        
        data = _gemini_vertex_request(
            project_id=project_id,
            location=location,
            model_path=model_path,
            parts=parts,
            quantity=quantity,
            params=params,
            api_key=vertex_api_key,
        )
        print("[IMAGE_EDIT] ✓ Vertex AI edit successful.", flush=True)
    except Exception as e:
        vertex_error = e
        print(f"[IMAGE_EDIT] ✗ Vertex AI edit failed: {e}", flush=True)
        print(f"[IMAGE_EDIT] Falling back to Gemini API...", flush=True)
        data = None

    if not data:
        if gemini_api_key:
            print(f"[IMAGE_EDIT] Attempting Gemini API fallback for model {_gemini_model_name(model_path)}...", flush=True)
            print(f"[IMAGE_EDIT] Using GEMINI_API_KEY for fallback", flush=True)
            try:
                data = _gemini_google_api_request(
                    model_name=_gemini_model_name(model_path),
                    parts=parts,
                    quantity=quantity,
                    params=params,
                    api_key=gemini_api_key,
                )
                print("[IMAGE_EDIT] ✓ Gemini API edit successful (fallback).", flush=True)
            except Exception as e:
                print(f"[IMAGE_EDIT] ✗ Gemini API failed: {e}", flush=True)
                raise ValueError(f"Edit generation failed. Vertex error: {vertex_error}. Gemini error: {e}")
        else:
            print(f"[IMAGE_EDIT] ✗ No Gemini API key available for fallback", flush=True)
            raise ValueError(f"Vertex AI edit failed and no Gemini API key provided. Error: {vertex_error}")

    outputs = data.get("candidates") or []
    results: List[bytes] = []

    # Проверяем finishReason для обнаружения отказов модели
    for candidate in outputs:
        finish_reason = candidate.get("finishReason", "")
        finish_message = candidate.get("finishMessage", "")

        # IMAGE_OTHER означает что модель отказалась генерировать (контент-политика, некорректный промт и т.д.)
        if finish_reason in ["IMAGE_OTHER", "SAFETY", "PROHIBITED_CONTENT"]:
            error_msg = f"Модель отказалась генерировать изображение. Причина: {finish_reason}"
            if finish_message:
                error_msg += f". Сообщение: {finish_message[:200]}"
            print(f"[IMAGE_EDIT] ✗ {error_msg}", flush=True)
            raise ValueError(error_msg)

        content_parts = candidate.get("content", {}).get("parts", [])
        for part in content_parts:
            inline = part.get("inlineData")
            if inline and inline.get("data"):
                results.append(base64.b64decode(inline["data"]))

    # Проверка на пустой результат (критично для режима ремикс!)
    if not results:
        print(f"[IMAGE_EDIT] ✗ No images returned from edit. Response: {str(data)[:300]}", flush=True)
        raise ValueError(f"No images returned from edit generation. Response: {str(data)[:200]}")

    print(f"[IMAGE_EDIT] ✓ Successfully decoded {len(results)} image(s)", flush=True)
    return results


def gemini_vertex_generate(
    prompt: str,
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
    *,
    model_name: Optional[str] = None,
) -> List[bytes]:
    """
    Генерация изображений через Vertex AI (Imagen 3 / Gemini 3) с автоматическим фоллбэком на Gemini API.
    Логика:
    1. Всегда пробуем Vertex AI первым.
    2. Если Vertex упал (любая ошибка) -> пробуем Gemini API (если есть ключ).
    """
    # Используем переданный model_name или дефолтный из настроек
    model_path = _vertex_model_path(model_name or getattr(settings, "NANO_BANANA_GEMINI_MODEL", None))
    
    # Разделяем ключи:
    # - NANO_BANANA_API_KEY (Vertex AI key, формат AQ.xxx) - только для Vertex AI
    # - GEMINI_API_KEY (Gemini API key, формат AIza...) - для Gemini API fallback
    vertex_api_key = getattr(settings, "NANO_BANANA_API_KEY", None)
    gemini_api_key = getattr(settings, "GEMINI_API_KEY", None)
    
    parts = [{"text": prompt}]
    
    data = None
    vertex_error = None
    creds_info: Optional[Dict[str, Any]] = None

    # 1. Попытка через Vertex AI
    try:
        print(f"[IMAGE_GEN] Attempting Vertex AI generation for model {model_path}...", flush=True)
        print(f"[IMAGE_GEN] Prompt: {prompt[:100]}...", flush=True)
        
        # Если есть Vertex API key, используем его для Vertex AI (через x-goog-api-key)
        # Иначе используем Service Account
        if vertex_api_key:
            print(f"[IMAGE_GEN] Using Vertex AI API Key", flush=True)
        else:
            print(f"[IMAGE_GEN] Using Service Account for Vertex AI", flush=True)
            creds_info = _load_service_account_info()
        
        project_id, location = _vertex_project_and_location(creds_info)
        print(f"[IMAGE_GEN] Using Project: {project_id}, Location: {location}", flush=True)
        
        data = _gemini_vertex_request(
            project_id=project_id,
            location=location,
            model_path=model_path,
            parts=parts,
            quantity=quantity,
            params=params,
            api_key=vertex_api_key,
        )
        print("[IMAGE_GEN] ✓ Vertex AI generation successful.", flush=True)
    except Exception as e:
        vertex_error = e
        print(f"[IMAGE_GEN] ✗ Vertex AI failed: {e}", flush=True)
        print(f"[IMAGE_GEN] Falling back to Gemini API...", flush=True)
        data = None

    # 2. Fallback на Gemini API
    if not data:
        if gemini_api_key:
            print(f"[IMAGE_GEN] Attempting Gemini API fallback for model {_gemini_model_name(model_path)}...", flush=True)
            print(f"[IMAGE_GEN] Using GEMINI_API_KEY for fallback", flush=True)
            try:
                data = _gemini_google_api_request(
                    model_name=_gemini_model_name(model_path),
                    parts=parts,
                    quantity=quantity,
                    params=params,
                    api_key=gemini_api_key,
                )
                print("[IMAGE_GEN] ✓ Gemini API generation successful (fallback).", flush=True)
            except Exception as e:
                print(f"[IMAGE_GEN] ✗ Gemini API failed: {e}", flush=True)
                raise ValueError(f"Generation failed. Vertex error: {vertex_error}. Gemini error: {e}")
        else:
            # Если ключа нет, а Vertex упал
            print(f"[IMAGE_GEN] ✗ No Gemini API key available for fallback", flush=True)
            raise ValueError(f"Vertex AI generation failed and no Gemini API key provided. Error: {vertex_error}")

    # Обработка ответа (одинаковая для обоих)
    outputs = data.get("candidates") or []
    results: List[bytes] = []

    # Проверяем finishReason для обнаружения отказов модели
    for candidate in outputs:
        finish_reason = candidate.get("finishReason", "")
        finish_message = candidate.get("finishMessage", "")

        # IMAGE_OTHER означает что модель отказалась генерировать (контент-политика, некорректный промт и т.д.)
        if finish_reason in ["IMAGE_OTHER", "SAFETY", "PROHIBITED_CONTENT"]:
            error_msg = f"Модель отказалась генерировать изображение. Причина: {finish_reason}"
            if finish_message:
                error_msg += f". Сообщение: {finish_message[:200]}"
            print(f"[IMAGE_GEN] ✗ {error_msg}", flush=True)
            raise ValueError(error_msg)

        content_parts = candidate.get("content", {}).get("parts", [])
        for part in content_parts:
            inline = part.get("inlineData")
            if inline and inline.get("data"):
                results.append(base64.b64decode(inline["data"]))

    if not results:
        print(f"[IMAGE_GEN] ✗ No images returned. Response: {str(data)[:300]}", flush=True)
        raise ValueError(f"No images returned from generation. Response: {str(data)[:200]}")

    print(f"[IMAGE_GEN] ✓ Successfully decoded {len(results)} image(s)", flush=True)
    return results
