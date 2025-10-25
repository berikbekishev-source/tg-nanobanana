import base64, httpx, uuid, json, io
from typing import List
from django.conf import settings
from supabase import create_client

GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

def vertex_generate_images(prompt: str, quantity: int) -> List[bytes]:
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

def gemini_generate_images(prompt: str, quantity: int) -> List[bytes]:
    """Возвращает список байтов изображений (разбираем inlineData или fileUri)."""
    model = settings.GEMINI_IMAGE_MODEL or "gemini-2.5-flash-image"
    url = GEMINI_URL_TMPL.format(model=model)
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

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

def generate_images(prompt: str, quantity: int) -> List[bytes]:
    """
    Unified image generation function.
    Chooses between Vertex AI or Gemini API based on settings.
    """
    use_vertex = getattr(settings, 'USE_VERTEX_AI', False)

    if use_vertex:
        return vertex_generate_images(prompt, quantity)
    else:
        return gemini_generate_images(prompt, quantity)

def supabase_upload_png(content: bytes) -> str:
    """Загружает PNG в Supabase Storage и возвращает ПУБЛИЧНЫЙ URL."""
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
