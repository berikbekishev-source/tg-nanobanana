from django.conf import settings
from django.http import HttpResponse, JsonResponse
from ninja import NinjaAPI
from aiogram.types import Update
from botapp.telegram import bot, dp
import json

api = NinjaAPI(csrf=False)


@api.get("/health")
def health(request):
    return {"ok": True}


@api.post("/telegram/webhook")
async def telegram_webhook(request):
    """
    Обработчик апдейтов Telegram.
    """
    try:
        # Проверяем секретный токен
        if request.headers.get("x-telegram-bot-api-secret-token") != settings.TG_WEBHOOK_SECRET:
            return HttpResponse(status=403)

        # ✅ Django-способ получить тело запроса
        data = json.loads(request.body)
        update = Update.model_validate(data)

        # Отправляем апдейт в aiogram-диспетчер
        await dp.feed_update(bot, update)

        return JsonResponse({"ok": True})  # Telegram требует именно 200 + JSON
    except Exception as e:
        print("❌ Webhook error:", e)
        return JsonResponse({"ok": False, "error": str(e)}, status=200)
