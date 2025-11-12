import json
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from ninja import NinjaAPI

from botapp.error_tracker import ErrorTracker
from botapp.models import BotErrorEvent

api = NinjaAPI(csrf=False)
logger = logging.getLogger(__name__)


@api.get("/health")
def health(request):
    # Возвращаем минимальный ответ, чтобы health-check Railway проходил быстро.
    return {"ok": True}


try:
    from aiogram.types import Update
    from botapp.telegram import bot, dp

    def _extract_chat_id(update: Optional[Update]) -> Optional[int]:
        if not update:
            return None
        if getattr(update, "message", None) and update.message.chat:
            return update.message.chat.id
        if getattr(update, "callback_query", None) and update.callback_query.message:
            return update.callback_query.message.chat.id
        if getattr(update, "my_chat_member", None) and update.my_chat_member.chat:
            return update.my_chat_member.chat.id
        return None

    @api.post("/telegram/webhook")
    async def telegram_webhook(request):
        """
        Обработчик апдейтов Telegram.
        """
        update_obj: Optional[Update] = None
        payload_body: Optional[str] = None
        parsed_data: Optional[Dict[str, Any]] = None
        try:
            if request.headers.get("x-telegram-bot-api-secret-token") != settings.TG_WEBHOOK_SECRET:
                return HttpResponse(status=403)

            payload_body = request.body.decode("utf-8", errors="ignore")
            parsed_data = json.loads(payload_body)
            update_obj = Update.model_validate(parsed_data)

            await dp.feed_update(bot, update_obj)
            return JsonResponse({"ok": True})
        except Exception as exc:
            logger.exception("Telegram webhook error")
            headers_payload = {k: v for k, v in request.headers.items()}
            update_payload = {}
            if update_obj:
                try:
                    update_payload = update_obj.model_dump(mode="json")
                except Exception:
                    update_payload = {}
            await ErrorTracker.alog(
                origin=BotErrorEvent.Origin.WEBHOOK,
                severity=BotErrorEvent.Severity.CRITICAL,
                handler="telegram_webhook",
                chat_id=_extract_chat_id(update_obj),
                payload={
                    "update": update_payload,
                    "body": parsed_data or payload_body,
                    "headers": headers_payload,
                },
                exc=exc,
            )
            return JsonResponse({"ok": False, "error": str(exc)}, status=200)

except ImportError:
    # aiogram not installed yet - create placeholder endpoint
    @api.post("/telegram/webhook")
    def telegram_webhook_placeholder(request):
        return JsonResponse({"ok": False, "error": "Telegram bot not configured"}, status=503)
