from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Dict, Optional

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import OperationalError
from django.utils import timezone

from botapp.models import BotErrorEvent, GenRequest, TgUser

try:
    import sentry_sdk
except ImportError:  # pragma: no cover
    sentry_sdk = None


logger = logging.getLogger(__name__)


class ErrorTracker:
    """Центральный сервис логирования ошибок бота."""

    _alert_cache: Dict[str, float] = {}

    @classmethod
    def log(
        cls,
        *,
        origin: str,
        severity: str = BotErrorEvent.Severity.WARNING,
        status: str = BotErrorEvent.Status.NEW,
        user: Optional[TgUser] = None,
        chat_id: Optional[int] = None,
        gen_request: Optional[GenRequest] = None,
        handler: str = "",
        message: str = "",
        error_class: Optional[str] = None,
        payload: Optional[Any] = None,
        extra: Optional[Dict[str, Any]] = None,
        exc: Optional[BaseException] = None,
    ) -> Optional[BotErrorEvent]:
        resolved_user = user
        if resolved_user is None and chat_id:
            resolved_user = TgUser.objects.filter(chat_id=chat_id).first()

        username_snapshot = (resolved_user.username if resolved_user and resolved_user.username else "")
        chat_id_value = chat_id or (resolved_user.chat_id if resolved_user else None)

        if not message and exc:
            message = str(exc)
        error_cls = error_class or (exc.__class__.__name__ if exc else "")
        stacktrace = ""
        if exc:
            stacktrace = "".join(traceback.format_exception(exc.__class__, exc, exc.__traceback__))

        payload_data = cls._to_serializable(payload)
        extra_data = cls._to_serializable(extra)

        try:
            event = BotErrorEvent.objects.create(
                origin=origin,
                severity=severity,
                status=status,
                occurred_at=timezone.now(),
                handler=handler[:255],
                error_class=error_cls[:255],
                message=cls._trim_text(message),
                stacktrace=cls._trim_text(stacktrace),
                payload=payload_data,
                extra=extra_data,
                chat_id=chat_id_value,
                user=resolved_user,
                username_snapshot=username_snapshot,
                gen_request=gen_request,
            )
        except OperationalError:
            logger.exception("Не удалось сохранить BotErrorEvent (OperationalError)")
            event = None
        except Exception:
            logger.exception("Не удалось сохранить BotErrorEvent")
            event = None

        cls._send_to_sentry(event=event, exc=exc, message=message, payload=payload_data)
        if severity == BotErrorEvent.Severity.CRITICAL:
            cls._notify_telegram(event, message)

        return event

    @classmethod
    async def alog(cls, **kwargs) -> Optional[BotErrorEvent]:
        return await sync_to_async(cls.log, thread_sensitive=True)(**kwargs)

    @staticmethod
    def _to_serializable(data: Any) -> Any:
        if data is None:
            return {}
        try:
            if isinstance(data, dict):
                return {str(k): ErrorTracker._to_serializable(v) for k, v in data.items()}
            if isinstance(data, (list, tuple, set)):
                return [ErrorTracker._to_serializable(v) for v in data]
            if isinstance(data, (str, int, float, bool)) or data is None:
                return data
            if hasattr(data, "model_dump"):
                return data.model_dump(mode="json")
            return repr(data)
        except Exception:
            return repr(data)

    @staticmethod
    def _trim_text(value: str, limit: int = 8000) -> str:
        if not value:
            return ""
        if len(value) <= limit:
            return value
        return value[: limit - 1] + "…"

    @classmethod
    def _send_to_sentry(cls, *, event: Optional[BotErrorEvent], exc: Optional[BaseException], message: str, payload: Any) -> None:
        if not sentry_sdk:
            return
        if not getattr(settings, "SENTRY_DSN", None):
            return

        payload_repr = payload if isinstance(payload, dict) else {"payload": payload}

        def _with_scope(callback):
            with sentry_sdk.push_scope() as scope:
                if event and event.chat_id:
                    scope.set_user({"id": str(event.chat_id), "username": event.username_snapshot})
                if event:
                    scope.set_tag("origin", event.origin)
                    if event.gen_request_id:
                        scope.set_tag("gen_request_id", event.gen_request_id)
                for key, value in payload_repr.items():
                    scope.set_extra(key, value)
                callback()

        if exc:
            _with_scope(lambda: sentry_sdk.capture_exception(exc))
        elif message:
            _with_scope(lambda: sentry_sdk.capture_message(message))

    @classmethod
    def _notify_telegram(cls, event: Optional[BotErrorEvent], fallback_message: str) -> None:
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        target_chat = getattr(settings, "ERROR_ALERT_CHAT_ID", None)
        if not token or not target_chat:
            return

        key = cls._build_alert_key(event, fallback_message)
        if not cls._should_alert(key):
            return

        summary = fallback_message or (event.message if event else "Critical error")
        origin = event.origin if event else "unknown"
        handler = event.handler if event else "-"
        chat_info = f"chat_id={event.chat_id}" if event and event.chat_id else "chat_id=—"
        text = (
            "⚠️ Критическая ошибка бота\n"
            f"Источник: {origin}\n"
            f"Хендлер: {handler or '-'}\n"
            f"{chat_info}\n"
            f"Сообщение: {summary[:400]}"
        )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": target_chat, "text": text}
        try:
            httpx.post(url, json=data, timeout=10.0)
        except Exception:
            logger.exception("Не удалось отправить критическое уведомление в Telegram")

    @classmethod
    def _build_alert_key(cls, event: Optional[BotErrorEvent], fallback_message: str) -> str:
        if event:
            return f"{event.origin}:{event.handler}:{event.error_class or event.message}"
        return f"fallback:{fallback_message}"

    @classmethod
    def _should_alert(cls, key: str) -> bool:
        cooldown = getattr(settings, "ERROR_ALERT_COOLDOWN", 300)
        now = time.monotonic()
        last = cls._alert_cache.get(key)
        if last and (now - last) < cooldown:
            return False
        cls._alert_cache[key] = now
        return True
