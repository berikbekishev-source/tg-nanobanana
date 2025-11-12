from __future__ import annotations

from typing import Any, Dict, Optional

from aiogram.types import ErrorEvent, Update

from botapp.error_tracker import ErrorTracker
from botapp.models import BotErrorEvent


async def aiogram_error_handler(event: ErrorEvent) -> bool:
    update = getattr(event, "update", None)
    payload = _safe_dump(update)
    chat_id = _extract_chat_id(update)
    handler_name = _resolve_handler_name(getattr(event, "data", None))

    state = None
    data: Optional[Dict[str, Any]] = getattr(event, "data", None)
    if data and data.get("state"):
        state = str(data["state"])

    payload_wrapper: Dict[str, Any] = {"update": payload}
    if state:
        payload_wrapper["state"] = state

    await ErrorTracker.alog(
        origin=BotErrorEvent.Origin.TELEGRAM,
        severity=BotErrorEvent.Severity.CRITICAL,
        handler=handler_name,
        chat_id=chat_id,
        payload=payload_wrapper,
        exc=event.exception,
    )
    return True


def _safe_dump(update: Optional[Update]) -> Dict[str, Any]:
    if not update:
        return {}
    try:
        return update.model_dump(mode="json")
    except Exception:
        return {}


def _extract_chat_id(update: Optional[Update]) -> Optional[int]:
    if not update:
        return None
    message = getattr(update, "message", None)
    if message and message.chat:
        return message.chat.id
    callback = getattr(update, "callback_query", None)
    if callback and callback.message:
        return callback.message.chat.id
    edited = getattr(update, "edited_message", None)
    if edited and edited.chat:
        return edited.chat.id
    my_chat_member = getattr(update, "my_chat_member", None)
    if my_chat_member and my_chat_member.chat:
        return my_chat_member.chat.id
    channel_post = getattr(update, "channel_post", None)
    if channel_post and channel_post.chat:
        return channel_post.chat.id
    return None


def _resolve_handler_name(data: Optional[Dict[str, Any]]) -> str:
    if not data:
        return ""
    handler = data.get("handler")
    if handler:
        return getattr(handler, "__qualname__", repr(handler))
    middleware = data.get("middleware")
    if middleware:
        return getattr(middleware, "__qualname__", repr(middleware))
    return ""
