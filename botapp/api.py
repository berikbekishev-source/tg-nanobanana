import json
import logging
import hashlib
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import HttpResponse, JsonResponse

from botapp.error_tracker import ErrorTracker
from botapp.models import BotErrorEvent
from config.ninja_api import build_ninja_api

api = build_ninja_api()
logger = logging.getLogger(__name__)


# ============================================================================
# Presigned Upload для прямой загрузки изображений в Supabase из браузера
# ============================================================================

try:
    from supabase import create_client
    _supabase_available = True
except ImportError:
    _supabase_available = False


@api.post("/storage/presigned-upload")
def get_presigned_upload_url(request):
    """
    Генерирует presigned URL для прямой загрузки изображения в Supabase Storage.

    Браузер может загрузить файл напрямую по этому URL без аутентификации.
    Это позволяет:
    - Разгрузить backend от обработки больших base64
    - Мгновенно закрывать webapp после отправки
    - Ускорить получение сообщения о старте генерации

    Request body (JSON):
        content_type: str - MIME тип файла (image/png, image/jpeg, image/webp)

    Response:
        upload_url: str - URL для PUT запроса с файлом
        upload_token: str - токен для загрузки (Supabase)
        public_url: str - публичный URL файла после загрузки
        file_path: str - путь к файлу в storage
    """
    if not _supabase_available:
        return JsonResponse(
            {"ok": False, "error": "Supabase не настроен"},
            status=503
        )

    try:
        # Парсим тело запроса
        try:
            body = json.loads(request.body.decode("utf-8")) if request.body else {}
        except json.JSONDecodeError:
            body = {}

        content_type = body.get("content_type", "image/png")

        # Определяем расширение файла
        ext_map = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/webp": "webp",
        }
        extension = ext_map.get(content_type, "png")

        # Генерируем уникальный путь
        file_name = f"webapp-uploads/{uuid.uuid4().hex}.{extension}"

        # Создаём Supabase клиент
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        bucket = settings.SUPABASE_BUCKET

        # Создаём presigned URL для загрузки (действует 10 минут)
        signed_result = supabase.storage.from_(bucket).create_signed_upload_url(file_name)

        # Извлекаем данные из результата
        # Supabase v2 возвращает dict с path, token, signedUrl
        if isinstance(signed_result, dict):
            upload_url = signed_result.get("signedUrl") or signed_result.get("signed_url", "")
            upload_token = signed_result.get("token", "")
        else:
            # Fallback для других версий SDK
            upload_url = str(signed_result)
            upload_token = ""

        # Формируем публичный URL
        public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{file_name}"

        logger.info(f"[PRESIGNED_UPLOAD] Generated URL for {file_name}")

        return JsonResponse({
            "ok": True,
            "upload_url": upload_url,
            "upload_token": upload_token,
            "public_url": public_url,
            "file_path": file_name,
        })

    except Exception as exc:
        logger.error(f"[PRESIGNED_UPLOAD] Error: {exc}", exc_info=True)
        return JsonResponse(
            {"ok": False, "error": f"Не удалось создать URL для загрузки: {str(exc)}"},
            status=500
        )


try:
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
except Exception:  # cryptography может отсутствовать
    load_pem_public_key = None  # type: ignore
    padding = None  # type: ignore
    hashes = None  # type: ignore


def _load_geminigen_public_key_bytes() -> Optional[bytes]:
    pem = getattr(settings, "GEMINIGEN_WEBHOOK_PUBLIC_KEY", None)
    path = getattr(settings, "GEMINIGEN_WEBHOOK_PUBLIC_KEY_PATH", None)
    if pem:
        return pem.encode("utf-8") if isinstance(pem, str) else pem
    if path:
        try:
            return Path(path).read_bytes()
        except OSError:
            logger.warning("Не удалось прочитать GEMINIGEN_WEBHOOK_PUBLIC_KEY_PATH=%s", path)
    return None


def _verify_geminigen_signature(raw_body: bytes, signature_hex: str) -> bool:
    if not signature_hex:
        return True
    if not load_pem_public_key:
        logger.warning("cryptography не установлена, пропускаем проверку подписи Geminigen")
        return True

    public_key_bytes = _load_geminigen_public_key_bytes()
    if not public_key_bytes:
        logger.warning("Публичный ключ Geminigen не настроен, пропускаем проверку подписи")
        return True

    try:
        public_key = load_pem_public_key(public_key_bytes)
        payload = json.loads(raw_body.decode("utf-8", errors="ignore") or "{}") if raw_body else {}
        event_uuid = payload.get("uuid") or (payload.get("data") or {}).get("uuid") or ""
        digest = hashlib.md5(str(event_uuid).encode()).digest()
        public_key.verify(bytes.fromhex(signature_hex), digest, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception as exc:
        logger.warning("Проверка подписи Geminigen не пройдена: %s", exc)
        return False


@api.get("/health")
def health(request):
    # Возвращаем минимальный ответ, чтобы health-check Railway проходил быстро.
    return {"ok": True}


def _submit_webapp_to_celery(user_id: int, data: Dict[str, Any], endpoint_name: str) -> JsonResponse:
    """
    Универсальная функция для отправки WebApp данных в Celery.
    Возвращает мгновенный ответ клиенту.
    """
    from botapp.tasks import process_webapp_submission_task

    try:
        process_webapp_submission_task.delay(user_id, data)
        logger.info(f"[WEBAPP_REST][{endpoint_name}] Task queued for user {user_id}")
        return JsonResponse({"ok": True})
    except Exception as exc:
        logger.error(f"[WEBAPP_REST][{endpoint_name}] Failed to queue task: {exc}", exc_info=True)
        return JsonResponse({"ok": False, "error": "Failed to queue task"}, status=500)


try:
    from aiogram.types import Update
    from botapp.telegram import bot, dp

    async def _feed_webapp_update(user_id: int, data: Dict[str, Any]) -> None:
        """
        Формирует mock Update с WebAppData и передает его в диспетчер.
        """
        from aiogram.types import Message, WebAppData, User, Chat
        from datetime import datetime

        user_obj = User(id=int(user_id), is_bot=False, first_name="User")
        chat_obj = Chat(id=int(user_id), type="private")
        # json.dumps с default=str, чтобы безопасно сериализовать Decimal/UUID и др.
        web_app_data_obj = WebAppData(data=json.dumps(data, ensure_ascii=False, default=str), button_text="Generate")
        message = Message(
            message_id=0,
            date=datetime.now(),
            chat=chat_obj,
            from_user=user_obj,
            web_app_data=web_app_data_obj,
            text=None  # text is Optional
        )
        update = Update(update_id=0, message=message)
        await dp.feed_update(bot, update)

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
            logger.info(f"[WEBHOOK] Получен запрос webhook")
            received_token = request.headers.get("x-telegram-bot-api-secret-token")
            expected_token = settings.TG_WEBHOOK_SECRET

            # Проверка секрета
            if received_token != expected_token:
                logger.warning(
                    f"[WEBHOOK] Неверный токен. Получен: {received_token[:10] if received_token else 'None'}..., Ожидался: {expected_token[:10] if expected_token else 'None'}..."
                )
                return HttpResponse(status=403)

            payload_body = request.body.decode("utf-8", errors="ignore") or ""

            if not payload_body.strip():
                logger.warning("[WEBHOOK] Пустое тело запроса")
                return JsonResponse({"ok": False, "error": "empty body"}, status=200)

            parsed_data = json.loads(payload_body)
            update_obj = Update.model_validate(parsed_data)

            update_type = "unknown"
            if update_obj.message:
                update_type = "message"
                if update_obj.message.web_app_data:
                    update_type = "web_app_data"
                    logger.info(f"[WEBHOOK] Получены данные WebApp: {update_obj.message.web_app_data.data[:100]}")
            elif update_obj.callback_query:
                update_type = "callback_query"

            logger.info(
                f"[WEBHOOK] Тип обновления: {update_type}, User ID: {update_obj.message.from_user.id if update_obj.message else 'N/A'}"
            )

            await dp.feed_update(bot, update_obj)
            logger.info(f"[WEBHOOK] Обновление успешно обработано")
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

    @api.post("/midjourney/webapp/submit")
    def midjourney_webapp_submit(request):
        """
        Endpoint для Midjourney Image WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            logger.info(f"[WEBAPP_REST][MIDJOURNEY] Received submission for user {user_id}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "MIDJOURNEY")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][MIDJOURNEY] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    @api.post("/midjourney_video/webapp/submit")
    def midjourney_video_webapp_submit(request):
        """
        Endpoint для Midjourney Video WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            logger.info(f"[WEBAPP_REST][MIDJOURNEY_VIDEO] Received submission for user {user_id}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "MIDJOURNEY_VIDEO")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][MIDJOURNEY_VIDEO] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    @api.post("/runway/webapp/submit")
    def runway_webapp_submit(request):
        """
        Endpoint для Runway WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            logger.info(f"[WEBAPP_REST][RUNWAY] Received submission for user {user_id}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "RUNWAY")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][RUNWAY] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    @api.post("/runway-aleph/webapp/submit")
    def runway_aleph_webapp_submit(request):
        """
        Endpoint для Runway Aleph WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            logger.info(f"[WEBAPP_REST][RUNWAY_ALEPH] Received submission for user {user_id}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "RUNWAY_ALEPH")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][RUNWAY_ALEPH] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    @api.post("/veo/webapp/submit")
    def veo_webapp_submit(request):
        """
        Endpoint для Veo WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            logger.info(f"[WEBAPP_REST][VEO] Received submission for user {user_id}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "VEO")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][VEO] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    @api.post("/geminigen/webhook")
    async def geminigen_webhook(request):
        """
        Webhook для уведомлений Geminigen (video generation completed/failed).
        """
        raw_body: bytes = request.body or b""
        signature = request.headers.get("x-signature") or request.headers.get("X-Signature") or ""

        if signature and not _verify_geminigen_signature(raw_body, signature):
            return JsonResponse({"ok": False, "error": "invalid signature"}, status=400)

        try:
            payload = json.loads(raw_body.decode("utf-8", errors="ignore") or "{}")
        except Exception:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

        try:
            from botapp.tasks import process_geminigen_webhook

            process_geminigen_webhook.delay(payload)
        except Exception as exc:
            logger.exception("Не удалось поставить вебхук Geminigen в очередь: %s", exc)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

        return JsonResponse({"ok": True})

    @api.post("/gpt-image/webapp/submit")
    def gpt_image_webapp_submit(request):
        """
        Endpoint для GPT Image WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            logger.info(f"[WEBAPP_REST][GPT_IMAGE] Received submission for user {user_id}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "GPT_IMAGE")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][GPT_IMAGE] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)


    @api.post("/sora2/webapp/submit")
    def sora2_webapp_submit(request):
        """
        Endpoint для Sora 2 WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            logger.info(f"[WEBAPP_REST][SORA2] Received submission for user {user_id}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "SORA2")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][SORA2] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    @api.post("/kling/webapp/submit")
    def kling_webapp_submit(request):
        """
        Endpoint для Kling WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            # Логируем для отладки (без image data)
            debug_data = {k: (len(v) if k.endswith("Data") and v else v) for k, v in (data or {}).items()}
            logger.info(f"[WEBAPP_REST][KLING] Received submission for user {user_id}, data keys: {debug_data}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "KLING")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][KLING] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    @api.post("/nano-banana/webapp/submit")
    def nano_banana_webapp_submit(request):
        """
        Endpoint для Nano Banana WebApp.
        Мгновенно возвращает ответ, обработка идёт в Celery.
        """
        try:
            payload = json.loads(request.body.decode("utf-8"))
            user_id = payload.get("user_id")
            data = payload.get("data")

            logger.info(f"[WEBAPP_REST][NANO] Received submission for user {user_id}")

            if not user_id or not data:
                return JsonResponse({"ok": False, "error": "Missing user_id or data"}, status=400)

            return _submit_webapp_to_celery(int(user_id), data, "NANO")
        except Exception as exc:
            logger.error(f"[WEBAPP_REST][NANO] Error: {exc}", exc_info=True)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)
except ImportError:
    # aiogram not installed yet - create placeholder endpoint
    @api.post("/telegram/webhook")
    def telegram_webhook_placeholder(request):
        return JsonResponse({"ok": False, "error": "Telegram bot not configured"}, status=503)
