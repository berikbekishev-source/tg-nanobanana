from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from typing import Optional

from aiogram.types import Message, PhotoSize, Document, Video, Audio, Voice, Animation, Sticker
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

        text, message_type = ChatLogger._extract_text_and_type(message)
        media_payload = ChatLogger._extract_media_payload(message, message_type)
        message_date = ChatLogger._extract_message_date(message)

        payload = {
            'content_type': message.content_type,
            'has_media': bool(media_payload.file_id),
        }

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
