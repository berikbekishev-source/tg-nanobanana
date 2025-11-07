import base64
import httpx
import uuid
import json
import io
import re
from typing import Any, Dict, List, Optional
from django.conf import settings
try:
    from supabase import create_client
except ImportError:  # pragma: no cover
    create_client = None

GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_IMAGE_URL = "https://api.openai.com/v1/images/generations"

def vertex_generate_images(prompt: str, quantity: int, params: Optional[Dict[str, Any]] = None) -> List[bytes]:
    """Генерация изображений через Vertex AI Imagen."""
    from google.cloud import aiplatform
    from google.oauth2 import service_account
    from vertexai.preview.vision_models import ImageGenerationModel

    # Parse credentials from environment
    creds_json = settings.GOOGLE_APPLICATION_CREDENTIALS_JSON
    if not creds_json:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS_JSON not set")

    creds_dict = json.loads(creds_json)
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
        if not value:
            return "1024x1024"
        text = str(value).lower()
        if text == "auto":
            return "auto"
        if re.fullmatch(r"\d+x\d+", text):
            return text
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
        "Content-Type": "application/json",
    }
    if getattr(settings, "OPENAI_ORGANIZATION", None):
        headers["OpenAI-Organization"] = settings.OPENAI_ORGANIZATION
    if getattr(settings, "OPENAI_PROJECT_ID", None):
        headers["OpenAI-Project"] = settings.OPENAI_PROJECT_ID

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

    imgs: List[bytes] = []
    with httpx.Client(timeout=120) as client:
        for _ in range(quantity):
            response = client.post(OPENAI_IMAGE_URL, headers=headers, json=payload_base)
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


def generate_images_for_model(
    model,
    prompt: str,
    quantity: int,
    params: Optional[Dict[str, Any]] = None,
) -> List[bytes]:
    """Вызывает подходящего провайдера генерации на основе модели."""
    provider = getattr(model, "provider", None)
    merged_params: Dict[str, Any] = {}
    if getattr(model, "default_params", None):
        merged_params.update(model.default_params)
    if params:
        merged_params.update(params)

    if provider == "openai_image":
        return openai_generate_images(prompt, quantity, params=merged_params, model_name=model.api_model_name)
    if provider == "vertex":
        return vertex_generate_images(prompt, quantity, params=merged_params)
    if provider == "gemini":
        return gemini_generate_images(prompt, quantity, params=merged_params)

    use_vertex = getattr(settings, 'USE_VERTEX_AI', False)
    if use_vertex:
        return vertex_generate_images(prompt, quantity, params=merged_params)
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
