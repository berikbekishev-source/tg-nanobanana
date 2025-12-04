"""Обработчики для создания JSON-промтов по пользовательскому референсу."""

from __future__ import annotations

import logging
import re
from html import escape
from typing import List, Optional, Tuple
from urllib.parse import quote_plus

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from asgiref.sync import sync_to_async
from django.conf import settings

from botapp.error_tracker import ErrorTracker
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.keyboards import (
    get_cancel_keyboard,
    get_reference_prompt_mods_keyboard,
    get_reference_prompt_models_keyboard,
    get_video_models_keyboard,
)
from botapp.models import BotErrorEvent, AIModel, TgUser
from botapp.reference_prompt import (
    REFERENCE_PROMPT_MODELS,
    REFERENCE_PROMPT_PRICING_SLUG,
    ReferenceInputPayload,
    ReferencePromptService,
    get_reference_prompt_model,
)
from botapp.reference_prompt.service import chunk_text
from botapp.states import BotStates
from botapp.business.pricing import get_base_price_tokens, calculate_request_cost


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


# Обработчик кнопки "Промт по референсу" перенесен в global_commands.py
# чтобы работать из любого состояния


@router.callback_query(StateFilter("*"), F.data.startswith("ref_prompt_model:"))
async def prompt_by_reference_select_model(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Сбрасываем состояние
    await state.clear()

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

    entry_text = await _reference_prompt_entry_text()

    await callback.message.answer(
        entry_text,
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
        '✅ Референс получен 🙌\n\nЕсли хотите создать точно такое же видео без изменений то нажмите на кнопку "✅ Без правок".\n\nА если хотите внести изменения в видео нажмите на кнопку "✏️ Внести правки".',
        reply_markup=get_reference_prompt_mods_keyboard(),
    )
    await state.set_state(BotStates.reference_prompt_confirm_mods)


@router.callback_query(F.data == "ref_prompt_mods:edit")
async def prompt_by_reference_mods_yes(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Напиши правки одним сообщением 🔧")
    await state.set_state(BotStates.reference_prompt_wait_mods)


@router.callback_query(F.data == "ref_prompt_mods:skip")
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

    logger.info(
        "reference_prompt: handler start chat_id=%s user_id=%s model=%s input_type=%s mods=%s",
        message.chat.id,
        message.from_user.id if message.from_user else None,
        model_slug,
        reference_payload.input_type,
        bool(modifications),
    )

    ai_model = await _get_reference_ai_model()
    if not ai_model:
        await message.answer(
            "❌ Модель для промта не настроена. Попробуйте позже.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        await state.set_state(BotStates.main_menu)
        return

    user = await sync_to_async(
        TgUser.objects.filter(chat_id=message.from_user.id if message.from_user else message.chat.id).first
    )()
    if not user:
        await message.answer(
            "❌ Пользователь не найден. Используйте /start, чтобы начать заново.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        await state.set_state(BotStates.main_menu)
        return

    _, cost_tokens = await sync_to_async(calculate_request_cost)(ai_model, quantity=1, duration=None, params=None)
    charge_tx = None

    can_generate, error_message = await sync_to_async(BalanceService.check_can_generate)(
        user,
        ai_model,
        quantity=1,
        total_cost_tokens=cost_tokens,
    )
    if not can_generate:
        await message.answer(
            f"❌ {error_message}",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        await state.set_state(BotStates.main_menu)
        return

    try:
        charge_tx = await sync_to_async(BalanceService.charge_for_generation)(
            user,
            ai_model,
            quantity=1,
            total_cost_tokens=cost_tokens,
        )
    except InsufficientBalanceError as exc:
        await message.answer(
            f"❌ {exc}",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        await state.set_state(BotStates.main_menu)
        return

    await message.answer(
        "Создаю промт для генерации видео по указанному референсу, ожидайте пару минут ⏳",
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
        video_keyboard = await _build_video_models_keyboard()
    except Exception as exc:  # noqa: BLE001 - логируем и отвечаем пользователю
        logger.exception("Failed to build reference prompt: %s", exc)
        if charge_tx:
            await sync_to_async(BalanceService.refund_generation)(
                user,
                charge_tx,
                reason=str(exc)[:200],
            )
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

    spent_tokens = abs(charge_tx.amount) if charge_tx else None
    balance_after = charge_tx.balance_after if charge_tx else None

    prompt_body = result.prompt_text or result.pretty_json or ""
    safe_prompt = escape(prompt_body) if prompt_body else "—"
    if safe_prompt not in {"", "—"}:
        safe_prompt = f'"{safe_prompt}"'
    prompt_chunks = chunk_text(safe_prompt, 3000) or ["—"]

    header_lines = [
        "✅ Готово!",
        f"Списано ⚡{spent_tokens:.2f} токенов" if spent_tokens is not None else None,
        f"Осталось ⚡{balance_after:.2f} токенов" if balance_after is not None else None,
        "",
        "Ваш промт 👇",
        "",
    ]
    header = "\n".join([line for line in header_lines if line is not None])
    first_message = f"{header}<pre>{prompt_chunks[0]}</pre>"
    await message.answer(first_message, parse_mode="HTML", reply_markup=video_keyboard)
    for chunk in prompt_chunks[1:]:
        await message.answer(f"<pre>{chunk}</pre>", parse_mode="HTML")

    await state.clear()
    await state.set_state(BotStates.main_menu)

async def _build_video_models_keyboard() -> Optional[InlineKeyboardMarkup]:
    """Возвращает inline-кнопки выбора модели видео, как в 'Создать видео'."""

    models = await sync_to_async(list)(
        AIModel.objects.filter(type="video", is_active=True).order_by("order")
    )
    if not models:
        return None

    public_base_url = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")

    kling_webapps = {}
    veo_webapps = {}
    sora_webapps = {}
    midjourney_video_webapps = {}

    if public_base_url:
        for model in models:
            cost = await sync_to_async(get_base_price_tokens)(model)
            price_label = f"⚡{cost:.2f} токенов"

            if model.provider == "kling":
                default_duration = None
                if isinstance(model.default_params, dict):
                    try:
                        default_duration = int(model.default_params.get("duration") or 0)
                    except (TypeError, ValueError):
                        default_duration = None
                base_duration = default_duration if default_duration and default_duration > 0 else 10
                kling_webapps[model.slug] = (
                    f"{public_base_url}/kling/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                    f"&price_base_duration={quote_plus(str(base_duration))}"
                )

            if model.provider == "veo" or model.slug.startswith("veo"):
                veo_webapps[model.slug] = (
                    f"{public_base_url}/veo/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                    f"&max_prompt={quote_plus(str(model.max_prompt_length))}"
                )

            if model.provider == "openai" and model.slug.startswith("sora"):
                sora_webapps[model.slug] = (
                    f"{public_base_url}/sora2/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                )
            if model.provider == "midjourney":
                midjourney_video_webapps[model.slug] = (
                    f"{public_base_url}/midjourney_video/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                    f"&max_prompt={quote_plus(str(model.max_prompt_length))}"
                )

    return get_video_models_keyboard(
        models,
        kling_webapps=kling_webapps,
        veo_webapps=veo_webapps,
        sora_webapps=sora_webapps,
        midjourney_video_webapps=midjourney_video_webapps,
    )
