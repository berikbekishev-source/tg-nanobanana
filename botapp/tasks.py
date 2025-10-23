from celery import shared_task
import httpx
from django.conf import settings
from .models import GenRequest
from .services import generate_images, supabase_upload_png

def send_telegram_photo(chat_id: int, photo_bytes: bytes, caption: str):
    """Отправка фото в Telegram через Bot API напрямую (без aiogram)"""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("image.png", photo_bytes, "image/png")}
    data = {"chat_id": chat_id, "caption": caption}
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, files=files, data=data)
        resp.raise_for_status()
        return resp.json()

def send_telegram_message(chat_id: int, text: str):
    """Отправка текстового сообщения в Telegram через Bot API"""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    with httpx.Client(timeout=10) as client:
        resp = client.post(url, json=data)
        resp.raise_for_status()
        return resp.json()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_image_task(self, request_id: int):
    req = GenRequest.objects.get(id=request_id)
    try:
        imgs = generate_images(req.prompt, req.quantity)
        urls = []
        for idx, img in enumerate(imgs, start=1):
            # грузим в Storage
            url_obj = supabase_upload_png(img)
            url = url_obj.get("public_url") if isinstance(url_obj, dict) else url_obj
            urls.append(url)
            # шлём в Telegram через прямой HTTP запрос
            ai_service = "Vertex AI Imagen" if getattr(settings, 'USE_VERTEX_AI', False) else "Gemini"
            send_telegram_photo(
                chat_id=req.chat_id,
                photo_bytes=img,
                caption=f"Сгенерировано {ai_service} ({idx}/{req.quantity})"
            )
        req.status = "done"
        req.result_urls = urls
        req.save(update_fields=["status","result_urls"])
    except Exception as e:
        req.status = "error"
        req.save(update_fields=["status"])
        # оповещение пользователя
        send_telegram_message(req.chat_id, "❌ Ошибка генерации изображения.")
        raise

