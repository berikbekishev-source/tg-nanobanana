"""Обработчики для создания JSON-промтов по пользовательскому референсу."""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import List, Optional, Tuple
from urllib.parse import quote_plus

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from asgiref.sync import sync_to_async
from django.conf import settings

from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.error_tracker import ErrorTracker
from botapp.keyboards import (
    get_cancel_keyboard,
    get_reference_prompt_mods_keyboard,
    get_reference_prompt_models_keyboard,
    get_video_models_keyboard,
)
from botapp.models import BotErrorEvent, AIModel, TgUser
from botapp.reference_prompt import (
    REFERENCE_PROMPT_PRICING_SLUG,
    REFERENCE_PROMPT_MODELS,
    ReferenceInputPayload,
    ReferencePromptService,
    get_reference_prompt_model,
)
from botapp.reference_prompt.pricing import (
    build_reference_prompt_price_line,
    get_reference_pricing_model_and_cost,
)
from botapp.states import BotStates
from botapp.business.pricing import get_base_price_tokens


logger = logging.getLogger(__name__)

router = Router()
service = ReferencePromptService()

URL_RE = re.compile(r"(https?://[^\s]+|www\.[^\s]+)", re.IGNORECASE)


def _chunk_plain_text(text: str, limit: int = 3500) -> List[str]:
    """Безопасно режет текст на части для Telegram."""
    if not text:
        return [""]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _escape_html(text: str) -> str:
    """Экранирует HTML-спецсимволы."""
    if not text:
        return ""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def _build_intro_message() -> str:
    price_line = await build_reference_prompt_price_line()
    return (
        "🔗 Скиньте в бота ссылку на любой Reels, Shorts, TikTok или загрузите в чат видео и получите промт "
        "для создания точно такого же видео!\n\n"
        f"{price_line}"
    )


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

    intro_text = await _build_intro_message()
    await callback.message.answer(intro_text, reply_markup=get_cancel_keyboard())

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

    user = None
    try:
        user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)
    except TgUser.DoesNotExist:
        # Фолбек: вдруг chat_id отличается от from_user (группы/каналы)
        try:
            user = await sync_to_async(TgUser.objects.get)(chat_id=message.chat.id)
        except TgUser.DoesNotExist:
            pass

    if not user:
        await message.answer(
            "Не удалось найти пользователя. Нажмите /start в боте, чтобы инициализировать профиль, и попробуйте ещё раз.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    try:
        await sync_to_async(BalanceService.ensure_balance)(user)
    except Exception as exc:  # pragma: no cover - редкий случай проблем с балансом
        logger.exception("reference_prompt: failed to ensure balance: %s", exc)
        await message.answer(
            "Не удалось получить ваш баланс. Попробуйте ещё раз или нажмите /start.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    pricing_model, cost_tokens = await get_reference_pricing_model_and_cost()
    if not pricing_model or cost_tokens is None:
        await message.answer(
            "Стоимость генерации временно недоступна. Попробуйте позже.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    can_generate, error_msg = await sync_to_async(BalanceService.check_can_generate)(
        user,
        pricing_model,
        total_cost_tokens=cost_tokens,
    )
    if not can_generate:
        await message.answer(
            f"❌ {error_msg}",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    charge_tx = None
    try:
        charge_tx = await sync_to_async(BalanceService.charge_for_generation)(
            user,
            pricing_model,
            quantity=1,
            total_cost_tokens=cost_tokens,
        )
    except InsufficientBalanceError as exc:
        await message.answer(str(exc), reply_markup=get_cancel_keyboard())
        await state.clear()
        return

    logger.info(
        "reference_prompt: handler start chat_id=%s user_id=%s model=%s input_type=%s mods=%s",
        message.chat.id,
        message.from_user.id if message.from_user else None,
        model_slug,
        reference_payload.input_type,
        bool(modifications),
    )

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
            try:
                await sync_to_async(BalanceService.refund_generation)(
                    user,
                    charge_tx,
                    reason="reference_prompt_failed",
                )
            except Exception as refund_exc:  # pragma: no cover - логируем сбой возврата
                logger.warning("Не удалось вернуть токены за reference prompt: %s", refund_exc)
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

    spent_label = f"{cost_tokens.quantize(Decimal('0.01')):.2f}" if cost_tokens is not None else "0.00"
    remaining_tokens = (
        Decimal(charge_tx.balance_after).quantize(Decimal("0.01")) if charge_tx else None
    )
    remaining_label = f"{remaining_tokens:.2f}" if remaining_tokens is not None else "—"

    prompt_text = result.prompt_text or ""
    prompt_escaped = _escape_html(prompt_text)
    prompt_formatted = f"<code>{prompt_escaped}</code>" if prompt_escaped else "—"

    result_message = (
        "✅ Готово!\n\n"
        f"<b>Списано:</b> ⚡{spent_label} токенов\n"
        f"<b>Осталось:</b> ⚡{remaining_label} токенов\n\n"
        f"<b>Ваш промт:</b>\n{prompt_formatted}"
    )

    # Если сообщение слишком длинное, разбиваем на части
    if len(result_message) <= 4000:
        await message.answer(result_message, reply_markup=video_keyboard, parse_mode="HTML")
    else:
        # Отправляем заголовок отдельно, затем промт частями
        header = (
            "✅ Готово!\n\n"
            f"<b>Списано:</b> ⚡{spent_label} токенов\n"
            f"<b>Осталось:</b> ⚡{remaining_label} токенов\n\n"
            "<b>Ваш промт:</b>"
        )
        await message.answer(header, reply_markup=video_keyboard, parse_mode="HTML")
        chunks = _chunk_plain_text(prompt_text, limit=3500)
        for chunk in chunks:
            chunk_escaped = _escape_html(chunk)
            await message.answer(f"<code>{chunk_escaped}</code>", parse_mode="HTML")

    await state.clear()
    await state.set_state(BotStates.main_menu)


async def _build_video_models_keyboard() -> Optional[InlineKeyboardMarkup]:
    """Возвращает inline-кнопки выбора модели видео, как в 'Создать видео'."""

    models = await sync_to_async(list)(
        AIModel.objects.filter(type="video", is_active=True)
        .exclude(slug=REFERENCE_PROMPT_PRICING_SLUG)
        .order_by("order")
    )
    if not models:
        return None

    public_base_url = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")

    kling_webapps = {}
    veo_webapps = {}
    sora_webapps = {}
    midjourney_video_webapps = {}
    runway_webapps = {}

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
            if model.provider == "useapi":
                base_duration = None
                if isinstance(model.default_params, dict):
                    try:
                        base_duration = int(model.default_params.get("duration") or 0)
                    except (TypeError, ValueError):
                        base_duration = None
                base_duration = base_duration if base_duration and base_duration > 0 else 5
                api_model_name = model.api_model_name or model.slug
                runway_webapps[model.slug] = (
                    f"{public_base_url}/runway/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                    f"&price_base_duration={quote_plus(str(base_duration))}"
                    f"&api_model={quote_plus(api_model_name)}"
                    f"&max_prompt={quote_plus(str(model.max_prompt_length))}"
                )

    return get_video_models_keyboard(
        models,
        kling_webapps=kling_webapps,
        veo_webapps=veo_webapps,
        sora_webapps=sora_webapps,
        midjourney_video_webapps=midjourney_video_webapps,
        runway_webapps=runway_webapps,
    )
