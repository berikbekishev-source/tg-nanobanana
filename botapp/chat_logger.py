from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from typing import Optional, List

from aiogram.types import (
    Message,
    PhotoSize,
    Document,
    Video,
    Audio,
    Voice,
    Animation,
    Sticker,
    CallbackQuery,
    InlineKeyboardMarkup,
)
from asgiref.sync import sync_to_async
from django.utils import timezone

from botapp.models import ChatMessage, ChatThread, TgUser


@dataclass
class _MediaPayload:
    file_id: str = ""
    unique_id: str = ""
    file_path: str = ""
    file_name: str = ""
    mime_type: str = ""


class ChatLogger:
    """
    Центральное место для логирования переписки между пользователем и ботом.
    """

    @staticmethod
    async def log_incoming(message: Message) -> None:
        await ChatLogger._persist_message(message, ChatMessage.Direction.INCOMING)

    @staticmethod
    async def log_outgoing(message: Message) -> None:
        await ChatLogger._persist_message(message, ChatMessage.Direction.OUTGOING)

    @staticmethod
    def log_outgoing_from_payload(payload: dict) -> None:
        """Синхронный способ логирования (например, после REST вызова Bot API)."""
        if not payload:
            return
        try:
            message = Message.model_validate(payload)
        except Exception:
            return
        ChatLogger._save_message(message, ChatMessage.Direction.OUTGOING)

    @staticmethod
    async def _persist_message(message: Message, direction: str) -> None:
        await sync_to_async(
            ChatLogger._save_message,
            thread_sensitive=True,
        )(message, direction)

    @staticmethod
    def _save_message(message: Message, direction: str) -> None:
        if direction == ChatMessage.Direction.INCOMING:
            tg_entity = message.from_user
        else:
            tg_entity = message.chat

        if tg_entity is None:
            return

        user, thread = ChatLogger._get_or_create_user_and_thread(tg_entity)

        text, message_type = ChatLogger._extract_text_and_type(message)
        media_payload = ChatLogger._extract_media_payload(message, message_type)
        message_date = ChatLogger._extract_message_date(message)
        if direction == ChatMessage.Direction.OUTGOING:
            message_date = timezone.now()

        payload: dict[str, object] = {
            'content_type': message.content_type,
            'has_media': bool(media_payload.file_id),
        }

        inline_keyboard = ChatLogger._extract_inline_keyboard(message)
        if inline_keyboard:
            payload['inline_keyboard'] = inline_keyboard

        web_app_info = ChatLogger._extract_webapp_info(message)
        if web_app_info:
            payload['web_app'] = web_app_info
            if not text:
                text = ChatLogger._render_webapp_text(web_app_info.get("label"))
            if message_type == ChatMessage.MessageType.OTHER:
                message_type = ChatMessage.MessageType.TEXT

        if message.message_id:
            exists = ChatMessage.objects.filter(
                thread=thread,
                telegram_message_id=message.message_id,
                direction=direction,
            ).exists()
            if exists:
                return

        ChatMessage.objects.create(
            thread=thread,
            user=user,
            direction=direction,
            message_type=message_type,
            telegram_message_id=message.message_id,
            text=text,
            media_file_id=media_payload.file_id,
            media_unique_id=media_payload.unique_id,
            media_file_path=media_payload.file_path,
            media_file_name=media_payload.file_name,
            media_mime_type=media_payload.mime_type,
            payload=payload,
            message_date=message_date,
        )

        preview = ChatLogger._build_preview_text(text, message_type)
        thread.last_message_text = preview
        thread.last_message_type = message_type
        thread.last_message_direction = direction
        thread.last_message_at = message_date
        if direction == ChatMessage.Direction.INCOMING:
            thread.unread_count = thread.unread_count + 1
        thread.save(
            update_fields=[
                'last_message_text',
                'last_message_type',
                'last_message_direction',
                'last_message_at',
                'unread_count',
                'updated_at',
            ]
        )

    @staticmethod
    def _extract_text_and_type(message: Message) -> tuple[str, str]:
        text = message.text or message.caption or ""
        content_type = message.content_type or "text"
        known_types = {choice[0] for choice in ChatMessage.MessageType.choices}
        if content_type not in known_types:
            content_type = ChatMessage.MessageType.OTHER
        return text, content_type

    @staticmethod
    def _extract_media_payload(message: Message, message_type: str) -> _MediaPayload:
        payload = _MediaPayload()

        if message_type == ChatMessage.MessageType.PHOTO and message.photo:
            largest: PhotoSize = message.photo[-1]
            payload.file_id = largest.file_id
            payload.unique_id = largest.file_unique_id
            payload.file_name = f"photo_{largest.file_unique_id}.jpg"
            payload.mime_type = "image/jpeg"
        elif message_type == ChatMessage.MessageType.VIDEO and message.video:
            video: Video = message.video
            payload.file_id = video.file_id
            payload.unique_id = video.file_unique_id
            payload.file_name = video.file_name or f"video_{video.file_unique_id}.mp4"
            payload.mime_type = video.mime_type or "video/mp4"
        elif message_type == ChatMessage.MessageType.DOCUMENT and message.document:
            document: Document = message.document
            payload.file_id = document.file_id
            payload.unique_id = document.file_unique_id
            payload.file_name = document.file_name or f"document_{document.file_unique_id}"
            payload.mime_type = document.mime_type or mimetypes.guess_type(payload.file_name)[0] or "application/octet-stream"
        elif message_type == ChatMessage.MessageType.AUDIO and message.audio:
            audio: Audio = message.audio
            payload.file_id = audio.file_id
            payload.unique_id = audio.file_unique_id
            payload.file_name = audio.file_name or f"audio_{audio.file_unique_id}.mp3"
            payload.mime_type = audio.mime_type or "audio/mpeg"
        elif message_type == ChatMessage.MessageType.VOICE and message.voice:
            voice: Voice = message.voice
            payload.file_id = voice.file_id
            payload.unique_id = voice.file_unique_id
            payload.file_name = f"voice_{voice.file_unique_id}.ogg"
            payload.mime_type = "audio/ogg"
        elif message_type == ChatMessage.MessageType.STICKER and message.sticker:
            sticker: Sticker = message.sticker
            payload.file_id = sticker.file_id
            payload.unique_id = sticker.file_unique_id
            payload.file_name = f"sticker_{sticker.file_unique_id}.webp"
            payload.mime_type = "image/webp"
        elif message_type == ChatMessage.MessageType.OTHER:
            # Попытаемся достать файлы из видео/анимаций
            if message.animation:
                animation: Animation = message.animation
                payload.file_id = animation.file_id
                payload.unique_id = animation.file_unique_id
                payload.file_name = animation.file_name or f"animation_{animation.file_unique_id}.mp4"
                payload.mime_type = "video/mp4"

        return payload

    @staticmethod
    def _extract_message_date(message: Message):
        message_dt = message.date
        if message_dt is None:
            return timezone.now()
        if message_dt.tzinfo is None:
            return timezone.make_aware(message_dt, timezone=timezone.utc)
        return message_dt

    @staticmethod
    def _build_preview_text(text: str, message_type: str) -> str:
        if text:
            preview = text.strip()
        else:
            previews = {
                ChatMessage.MessageType.PHOTO: "[Фото]",
                ChatMessage.MessageType.VIDEO: "[Видео]",
                ChatMessage.MessageType.DOCUMENT: "[Документ]",
                ChatMessage.MessageType.AUDIO: "[Аудио]",
                ChatMessage.MessageType.VOICE: "[Голосовое]",
                ChatMessage.MessageType.STICKER: "[Стикер]",
            }
            preview = previews.get(message_type, "[Сообщение]")
        if len(preview) > 160:
            return preview[:157] + "..."
        return preview

    @staticmethod
    def _get_or_create_user_and_thread(tg_entity):
        defaults = {
            'username': getattr(tg_entity, 'username', '') or '',
            'first_name': getattr(tg_entity, 'first_name', '') or '',
            'last_name': getattr(tg_entity, 'last_name', '') or '',
            'language_code': getattr(tg_entity, 'language_code', '') or 'ru',
        }
        user, _ = TgUser.objects.get_or_create(
            chat_id=tg_entity.id,
            defaults=defaults,
        )
        updated = False
        for field in ['username', 'first_name', 'last_name']:
            value = defaults[field]
            if value and getattr(user, field) != value:
                setattr(user, field, value)
                updated = True
        if updated:
            user.save(update_fields=['username', 'first_name', 'last_name'])

        thread, _ = ChatThread.objects.get_or_create(
            user=user,
            defaults={'last_message_at': timezone.now()},
        )
        return user, thread

    @staticmethod
    def _extract_inline_keyboard(message: Message) -> Optional[List[List[dict]]]:
        markup = getattr(message, "reply_markup", None)
        if not isinstance(markup, InlineKeyboardMarkup):
            return None
        keyboard = []
        for row in markup.inline_keyboard or []:
            row_buttons = []
            for button in row:
                row_buttons.append({
                    "text": button.text,
                    "callback_data": button.callback_data,
                    "url": button.url,
                })
            if row_buttons:
                keyboard.append(row_buttons)
        return keyboard or None

    @staticmethod
    async def log_callback(callback: CallbackQuery) -> None:
        await sync_to_async(
            ChatLogger._save_callback,
            thread_sensitive=True,
        )(callback)

    @staticmethod
    def _save_callback(callback: CallbackQuery) -> None:
        tg_user = callback.from_user
        if tg_user is None:
            return
        user, thread = ChatLogger._get_or_create_user_and_thread(tg_user)

        if callback.id:
            exists = ChatMessage.objects.filter(
                thread=thread,
                payload__callback_id=callback.id,
            ).exists()
            if exists:
                return

        button_text = ChatLogger._find_button_text(callback)
        text_part = button_text or callback.data or "неизвестная кнопка"
        message_text = f"Нажал кнопку: «{text_part}»"
        payload = {
            "button_text": button_text,
            "button_data": callback.data,
            "callback_id": callback.id,
            "source_message_id": getattr(callback.message, "message_id", None),
        }

        ChatMessage.objects.create(
            thread=thread,
            user=user,
            direction=ChatMessage.Direction.INCOMING,
            message_type=ChatMessage.MessageType.TEXT,
            text=message_text,
            payload=payload,
            message_date=timezone.now(),
        )

        thread.last_message_text = message_text
        thread.last_message_type = ChatMessage.MessageType.TEXT
        thread.last_message_direction = ChatMessage.Direction.INCOMING
        thread.last_message_at = timezone.now()
        thread.unread_count = thread.unread_count + 1
        thread.save(update_fields=[
            'last_message_text',
            'last_message_type',
            'last_message_direction',
            'last_message_at',
            'unread_count',
            'updated_at',
        ])

    @staticmethod
    def _find_button_text(callback: CallbackQuery) -> Optional[str]:
        message = callback.message
        if not message:
            return None
        markup = getattr(message, "reply_markup", None)
        if not isinstance(markup, InlineKeyboardMarkup):
            return None
        data = callback.data
        for row in markup.inline_keyboard or []:
            for button in row:
                if data and button.callback_data == data:
                    return button.text
        return None

    @staticmethod
    def _parse_webapp_payload(raw: str) -> Optional[dict]:
        if not raw:
            return None
        current = raw
        for _ in range(2):
            try:
                parsed = json.loads(current)
            except Exception:
                return None
            if isinstance(parsed, str):
                current = parsed
                continue
            if isinstance(parsed, dict):
                return parsed
            return None
        return None

    @staticmethod
    def _humanize_webapp(kind: str, model_slug: str) -> str:
        mapping = {
            "midjourney_settings": "Midjourney",
            "gpt_image_settings": "GPT Image",
            "nano_banana_settings": "Nano Banana",
            "kling_settings": "Kling",
            "veo_video_settings": "Veo",
            "sora2_settings": "Sora 2",
            "runway_settings": "Runway",
        }
        if kind and kind in mapping:
            return mapping[kind]
        if model_slug:
            normalized = model_slug.replace("_", " ").replace("-", " ").strip()
            if normalized:
                return normalized.title()
        return "WebApp"

    @staticmethod
    def _extract_webapp_info(message: Message) -> dict:
        web_app = getattr(message, "web_app_data", None)
        data = getattr(web_app, "data", None) if web_app else None
        if not data:
            return {}

        parsed = ChatLogger._parse_webapp_payload(data)
        if not parsed:
            return {"label": "WebApp"}

        kind = (parsed.get("kind") or "").strip()
        model_slug = (
            parsed.get("modelSlug")
            or parsed.get("model")
            or parsed.get("model_slug")
            or ""
        ).strip()
        label = (
            parsed.get("webappName")
            or parsed.get("appName")
            or parsed.get("title")
            or ChatLogger._humanize_webapp(kind, model_slug)
        )

        info = {
            "kind": kind or None,
            "model_slug": model_slug or None,
            "label": label or None,
            "task_type": parsed.get("taskType") or None,
        }
        return {k: v for k, v in info.items() if v}

    @staticmethod
    def _render_webapp_text(label: Optional[str]) -> str:
        readable = (label or "WebApp").strip() or "WebApp"
        return f"Отправлен запрос на генерацию через Webapp {readable}"
