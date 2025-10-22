from celery import shared_task
from asgiref.sync import async_to_sync
from aiogram.types import BufferedInputFile
from django.conf import settings
from .models import GenRequest
from .telegram import bot
from .services import gemini_generate_images, supabase_upload_png

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_image_task(self, request_id: int):
    req = GenRequest.objects.get(id=request_id)
    try:
        imgs = gemini_generate_images(req.prompt, req.quantity)
        urls = []
        for idx, img in enumerate(imgs, start=1):
            # грузим в Storage
            url_obj = supabase_upload_png(img)
            url = url_obj.get("public_url") if isinstance(url_obj, dict) else url_obj
            urls.append(url)
            # шлём в Telegram (aiogram async из sync-задачи)
            async_to_sync(bot.send_photo)(
                chat_id=req.chat_id,
                photo=BufferedInputFile(img, filename=f"gen_{idx}.png"),
                caption=f"Сгенерировано Gemini ({idx}/{req.quantity})"
            )
        req.status = "done"
        req.result_urls = urls
        req.save(update_fields=["status","result_urls"])
    except Exception as e:
        req.status = "error"
        req.save(update_fields=["status"])
        # оповещение пользователя
        async_to_sync(bot.send_message)(req.chat_id, "❌ Ошибка генерации изображения.")
        raise

