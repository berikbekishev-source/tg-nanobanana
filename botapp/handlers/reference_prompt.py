"""Обработчики для создания JSON-промтов по пользовательскому референсу."""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from botapp.error_tracker import ErrorTracker
from botapp.keyboards import (
    get_cancel_keyboard,
    get_reference_prompt_mods_keyboard,
    get_reference_prompt_models_keyboard,
)
from botapp.models import BotErrorEvent
from botapp.reference_prompt import (
    REFERENCE_PROMPT_MODELS,
    ReferenceInputPayload,
    ReferencePromptService,
    get_reference_prompt_model,
)
from botapp.states import BotStates


logger = logging.getLogger(__name__)

router = Router()
service = ReferencePromptService()

URL_RE = re.compile(r"(https?://[^\s]+|www\.[^\s]+)", re.IGNORECASE)


def _extract_urls(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return list({match.group(0) for match in URL_RE.finditer(text)})


def _collect_reference_payload(message: Message) -> Optional[ReferenceInputPayload]:
    """Формирует структуру метаданных для дальнейшей генерации промта."""

    if message.photo:
        photo = message.photo[-1]
        return ReferenceInputPayload(
            input_type="photo",
            text=message.caption,
            caption=message.caption,
            urls=_extract_urls(message.caption),
            file_id=photo.file_id,
            file_unique_id=photo.file_unique_id,
            mime_type="image/jpeg",
            file_size=photo.file_size,
            width=photo.width,
            height=photo.height,
        )

    if message.video:
        video = message.video
        return ReferenceInputPayload(
            input_type="video",
            text=message.caption,
            caption=message.caption,
            urls=_extract_urls(message.caption),
            file_id=video.file_id,
            file_unique_id=video.file_unique_id,
            mime_type=video.mime_type or "video/mp4",
            file_size=video.file_size,
            width=video.width,
            height=video.height,
            duration=video.duration,
        )

    if message.animation:
        animation = message.animation
        return ReferenceInputPayload(
            input_type="video",
            text=message.caption,
            caption=message.caption,
            urls=_extract_urls(message.caption),
            file_id=animation.file_id,
            file_unique_id=animation.file_unique_id,
            mime_type=animation.mime_type or "video/mp4",
            file_size=animation.file_size,
            width=animation.width,
            height=animation.height,
            duration=animation.duration,
        )

    if message.document:
        document = message.document
        mime = document.mime_type or ""
        if mime.startswith("image/"):
            input_type = "photo"
        elif mime.startswith("video/"):
            input_type = "video"
        else:
            return None

        return ReferenceInputPayload(
            input_type=input_type,
            text=message.caption,
            caption=message.caption,
            urls=_extract_urls(message.caption),
            file_id=document.file_id,
            file_unique_id=document.file_unique_id,
            file_name=document.file_name,
            mime_type=mime,
            file_size=document.file_size,
        )

    if message.text:
        text = message.text.strip()
        urls = _extract_urls(text)
        input_type = "url" if urls else "text"
        return ReferenceInputPayload(
            input_type=input_type,
            text=text,
            caption=text,
            urls=urls,
            source_url=urls[0] if urls else None,
        )

    return None


@router.message(F.text == "📲Промт по рефференсу")
async def prompt_by_reference_entry(message: Message, state: FSMContext):
    """Точка входа в сценарий генерации промта по референсу."""

    await state.clear()

    if not REFERENCE_PROMPT_MODELS:
        await message.answer(
            "😔 Сейчас нет доступных моделей для создания промта по референсу.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    default_model = next(iter(REFERENCE_PROMPT_MODELS.values()), None)
    if not default_model:
        await message.answer(
            "😔 Сейчас нет доступных моделей для создания промта по референсу.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(reference_prompt_model=default_model.slug)

    await message.answer(
        "🔍 Скиньте в бота ссылку на любой Reels, Shorts, TikTok или загрузите в чат видео/изображениеи и получите промт для генерации точно такого же видео!",
        reply_markup=get_cancel_keyboard(),
    )
    await state.set_state(BotStates.reference_prompt_wait_reference)


@router.callback_query(BotStates.reference_prompt_select_model, F.data.startswith("ref_prompt_model:"))
async def prompt_by_reference_select_model(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    slug = callback.data.split(":", maxsplit=1)[1]

    try:
        model = get_reference_prompt_model(slug)
    except KeyError:
        options = [(m.slug, m.title) for m in REFERENCE_PROMPT_MODELS.values()]
        await callback.message.answer(
            "❌ Неизвестная модель. Попробуйте выбрать из списка заново.",
            reply_markup=get_reference_prompt_models_keyboard(options),
        )
        return

    await state.update_data(reference_prompt_model=model.slug)

    await callback.message.answer(
        "Отправьте ссылку на рефференс или загрузите в чат видео/изображение и я создам промт для генерации точно такого же видео",
        reply_markup=get_cancel_keyboard(),
    )

    await state.set_state(BotStates.reference_prompt_wait_reference)


@router.message(BotStates.reference_prompt_wait_reference)
async def prompt_by_reference_collect(message: Message, state: FSMContext):
    payload = _collect_reference_payload(message)

    if not payload:
        await message.answer(
            "Не получилось распознать референс. Отправьте ссылку, изображение или видео.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(reference_payload=payload.as_state())

    await message.answer(
        "✅ Референс получен.\n\nХотите внести правки перед сборкой промта?",
        reply_markup=get_reference_prompt_mods_keyboard(),
    )

    await state.set_state(BotStates.reference_prompt_confirm_mods)


@router.callback_query(BotStates.reference_prompt_confirm_mods, F.data == "ref_prompt_mods:edit")
async def prompt_by_reference_mods_yes(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Напиши правки одним сообщением 🔧")
    await state.set_state(BotStates.reference_prompt_wait_mods)


@router.callback_query(BotStates.reference_prompt_confirm_mods, F.data == "ref_prompt_mods:skip")
async def prompt_by_reference_mods_skip(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _start_prompt_generation(callback.message, state, modifications=None)


@router.message(BotStates.reference_prompt_wait_mods)
async def prompt_by_reference_receive_mods(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Отправьте правки текстом одним сообщением 🔧")
        return

    await state.update_data(reference_modifications=message.text.strip())
    await _start_prompt_generation(message, state, modifications=message.text.strip())


async def _start_prompt_generation(message: Message, state: FSMContext, modifications: Optional[str]) -> None:
    data = await state.get_data()

    model_slug = data.get("reference_prompt_model")
    payload_data = data.get("reference_payload")

    if not model_slug or not payload_data:
        await message.answer(
            "Не найдено исходных данных для генерации. Пожалуйста, начните сначала.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    reference_payload = ReferenceInputPayload.from_state(payload_data)

    await message.answer(
        "Создаю промт для генерация видео по указанному рефференсу, ожидайте пару минут ⏳",
        reply_markup=get_cancel_keyboard(),
    )
    await state.set_state(BotStates.reference_prompt_processing)

    try:
        result = await service.generate_prompt(
            bot=message.bot,
            model_slug=model_slug,
            reference=reference_payload,
            modifications=modifications,
            user_context={
                "chat_id": message.chat.id,
                "user_id": message.from_user.id if message.from_user else None,
                "username": message.from_user.username if message.from_user else None,
            },
        )
    except Exception as exc:  # noqa: BLE001 - логируем и отвечаем пользователю
        logger.exception("Failed to build reference prompt: %s", exc)
        error_message = str(exc).strip() or "Не удалось собрать промт. Попробуйте снова или пришлите другой референс."
        await message.answer(
            f"❌ {error_message}",
            reply_markup=get_cancel_keyboard(),
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="reference_prompt._start_prompt_generation",
            chat_id=message.chat.id,
            payload={
                "model_slug": model_slug,
                "has_reference": bool(reference_payload),
                "modifications": modifications,
            },
            exc=exc,
        )
        await state.set_state(BotStates.reference_prompt_wait_reference)
        return

    for chunk in result.chunks:
        await message.answer(chunk, parse_mode="Markdown")

    await state.clear()
    await state.set_state(BotStates.main_menu)
