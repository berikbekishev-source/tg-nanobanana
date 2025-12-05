"""
Обработчики генерации видео
"""
import asyncio
import base64
import json
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from botapp.states import BotStates
from botapp.keyboards import (
    get_video_models_keyboard,
    get_video_format_keyboard,
    get_video_duration_keyboard,
    get_video_resolution_keyboard,
    get_cancel_keyboard,
    get_main_menu_inline_keyboard,
    get_generation_start_message
)
from botapp.models import TgUser, AIModel, GenRequest, BotErrorEvent
from botapp.business.generation import GenerationService
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.business.pricing import calculate_request_cost, get_base_price_tokens
from botapp.tasks import generate_video_task, extend_video_task
from botapp.providers.video.openai_sora import resolve_sora_dimensions
from asgiref.sync import sync_to_async
from botapp.services import supabase_upload_png
from botapp.error_tracker import ErrorTracker

router = Router()
START_MESSAGE_DELAY = 0.6


async def _send_generation_start_message(
    message: Message,
    text: str,
    *,
    delay: float = START_MESSAGE_DELAY,
) -> None:
    """Отправляет стартовое сообщение с задержкой, чтобы успело закрыться WebApp."""
    await asyncio.sleep(delay)
    await message.answer(text, reply_markup=get_main_menu_inline_keyboard())


def _extract_duration_options(model: AIModel) -> Optional[List[int]]:
    """
    Вернуть список поддерживаемых длительностей, если они заданы в allowed_params.
    """
    allowed_params = model.allowed_params or {}
    duration_param = allowed_params.get("duration")

    raw_options: Optional[List[int]] = None
    if isinstance(duration_param, list):
        raw_options = duration_param
    elif isinstance(duration_param, dict):
        options = duration_param.get("options") or duration_param.get("values")
        if isinstance(options, list):
            raw_options = options

    if not raw_options and model.provider == "openai":
        raw_options = [4, 8, 12]

    if not raw_options:
        return None

    cleaned: List[int] = []
    for value in raw_options:
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            continue
        if ivalue > 0:
            cleaned.append(ivalue)

    if not cleaned:
        return None

    cleaned = sorted(set(cleaned))
    return cleaned


def _calculate_image_size_hint(
    *,
    supports_images: bool,
    is_sora: bool,
    resolution: Optional[str],
    aspect_ratio: Optional[str],
) -> Optional[Tuple[int, int]]:
    if not (supports_images and is_sora and resolution and aspect_ratio):
        return None
    return resolve_sora_dimensions(resolution, aspect_ratio)


def _format_image_hint_text(dimensions: Optional[Tuple[int, int]]) -> Optional[str]:
    if not dimensions:
        return None
    width, height = dimensions
    return (
        f"Размер изображения должно быть: {width}x{height}. "
        "Если размер будет другим, мы автоматически обрежем центр под нужный формат."
    )


MAX_KLING_IMAGE_BYTES = 10 * 1024 * 1024


def _convert_to_png_bytes(raw: bytes, mime: Optional[str]) -> bytes:
    mime_value = (mime or "").lower()
    if mime_value == "image/png":
        return raw
    try:
        from PIL import Image
    except ImportError:
        return raw
    try:
        with Image.open(BytesIO(raw)) as img:
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()
    except Exception:
        return raw


def _extract_public_url(upload_obj) -> Optional[str]:
    if isinstance(upload_obj, dict):
        return upload_obj.get("public_url") or upload_obj.get("publicUrl") or upload_obj.get("publicURL")
    return upload_obj

def _extract_allowed_aspect_ratios(model: AIModel) -> List[str]:
    """Возвращает список разрешенных аспектов для модели."""
    allowed: List[str] = []
    params = model.allowed_params or {}
    raw = params.get("aspect_ratio")
    if isinstance(raw, list):
        allowed = [str(v) for v in raw if v]
    elif isinstance(raw, dict):
        opts = raw.get("options") or raw.get("values")
        if isinstance(opts, list):
            allowed = [str(v) for v in opts if v]
    return [r.strip() for r in allowed if isinstance(r, str) and r.strip()]


def _extract_allowed_resolutions(model: AIModel) -> List[str]:
    """Возвращает список разрешенных разрешений для модели."""
    allowed: List[str] = []
    params = model.allowed_params or {}
    raw = params.get("resolution")
    if isinstance(raw, list):
        allowed = [str(v) for v in raw if v]
    elif isinstance(raw, dict):
        opts = raw.get("options") or raw.get("values")
        if isinstance(opts, list):
            allowed = [str(v) for v in opts if v]
    return [r.strip().lower() for r in allowed if isinstance(r, str) and r.strip()]


def _normalize_resolution_value(value: Optional[Any]) -> str:
    """
    Нормализуем разрешение к каноническим значениям:
    - 720p: {'720', '720p', 'small'}
    - 1080p: {'1080', '1080p', 'large'}
    Остальное возвращаем как есть (строкой, lower).
    """
    val = str(value or "").strip().lower()
    if val in {"720", "720p", "small"}:
        return "720p"
    if val in {"1080", "1080p", "large"}:
        return "1080p"
    return val


def _normalize_allowed_resolutions(raw: List[str]) -> List[str]:
    """Расширяем список разрешений с учетом синонимов (small/large, без 'p')."""
    normalized = {_normalize_resolution_value(item) for item in raw}
    return [r for r in normalized if r]


def _order_resolutions(resolutions: List[str]) -> List[str]:
    """Возвращает список разрешений в предсказуемом порядке (720p, 1080p, остальные)."""
    preferred = ["720p", "1080p"]
    result: List[str] = []
    seen = set()
    for res in preferred + resolutions:
        val = _normalize_resolution_value(res)
        if val and val not in seen:
            result.append(val)
            seen.add(val)
    return result


def _normalize_model_name(raw: Optional[str]) -> str:
    """Удаляет служебные суффиксы и приводит имя модели к нижнему регистру."""
    value = (raw or "").strip()
    if not value:
        return ""
    value = value.replace("_", "-").split("@", 1)[0].lower()
    if value.startswith("sora") and not value.startswith("sora-") and len(value) > 4 and value[4].isdigit():
        value = "sora-" + value[4:]
    return value


def _resolve_veo_resolutions(model: AIModel, aspect_ratio: str) -> List[str]:
    """Определяет разрешения Veo с учетом модели и аспектного соотношения."""
    allowed = set(_normalize_allowed_resolutions(_extract_allowed_resolutions(model)))
    api_model = _normalize_model_name(model.api_model_name or model.slug)

    if api_model.startswith("veo-2"):
        allowed = {"720p"}
    else:
        # Veo 3.x поддерживает 720p и 1080p (при 16:9)
        allowed.update({"720p", "1080p"})

    # 9:16 у Veo поддерживает только 720p
    if aspect_ratio.strip() == "9:16":
        allowed = {"720p"}

    return _order_resolutions(list(allowed or {"720p"}))


def _resolve_sora_resolutions(model: AIModel) -> List[str]:
    """Определяет разрешения Sora в зависимости от модели."""
    allowed = set(_normalize_allowed_resolutions(_extract_allowed_resolutions(model)))
    api_model = _normalize_model_name(model.api_model_name or model.slug)

    sora_map = {
        "sora-2": {"720p"},
        "sora-2-pro": {"720p"},
        "sora-2-pro-hd": {"1080p"},
    }
    if api_model in sora_map:
        allowed = sora_map[api_model]
    elif not allowed:
        allowed = {"720p", "1080p"}

    return _order_resolutions(list(allowed or {"720p"}))


MAX_VEO_IMAGE_BYTES = 5 * 1024 * 1024


def _parse_webapp_payload(raw: str) -> Optional[Dict[str, Any]]:
    """
    Аккуратно парсим web_app_data, учитывая экранирование и двойное кодирование.
    """
    decoded = raw or "{}"
    try:
        if isinstance(decoded, bytes):
            decoded = decoded.decode("utf-8", errors="ignore")
        if decoded.startswith('{\"') or decoded.startswith("{\'"):
            try:
                decoded = decoded.encode().decode("unicode_escape")
            except Exception:
                pass
        payload = json.loads(decoded)
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                return None
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


@router.message(StateFilter("*"), F.web_app_data)
async def handle_webapp_data_dispatcher(message: Message, state: FSMContext):
    """Dispatcher for all WebApp data - routes to specific handler based on 'kind' field."""
    # Parse the payload once
    try:
        raw_data = message.web_app_data.data or "{}"
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8", errors="ignore")
        if raw_data.startswith('{\\"') or raw_data.startswith("{\\'"):
            try:
                raw_data = raw_data.encode().decode("unicode_escape")
            except Exception:
                pass
        payload = json.loads(raw_data)
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                pass
    except Exception:
        await message.answer(
            "❌ Не удалось прочитать данные из окна настроек. Откройте его и попробуйте ещё раз.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    # Route based on kind
    kind = payload.get("kind") if isinstance(payload, dict) else None
    if kind == "sora2_settings":
        await _handle_sora_webapp_data_impl(message, state, payload)
    elif kind == "runway_settings":
        await _handle_runway_webapp_data_impl(message, state, payload)
    elif kind == "midjourney_video_settings":
        await _handle_midjourney_video_webapp_data_impl(message, state, payload)
    elif kind == "kling_settings":
        await _handle_kling_webapp_data_impl(message, state, payload)
    elif kind == "veo_video_settings":
        await _handle_veo_webapp_data_impl(message, state, payload)
    # If kind doesn't match, silently ignore (other handlers may process it)


async def _handle_sora_webapp_data_impl(message: Message, state: FSMContext, payload: dict):
    """Принимаем данные Sora 2 WebApp и запускаем генерацию."""
    data = await state.get_data()
    model_slug = payload.get("modelSlug") or data.get("model_slug") or data.get("selected_model") or "sora2"

    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        await message.answer(
            "Модель Sora недоступна. Выберите её заново из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    if model.provider not in {"openai"}:
        await message.answer(
            "Эта WebApp работает только с моделью Sora 2.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    await state.update_data(model_id=int(model.id), model_slug=str(model.slug), model_provider=str(model.provider))

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        await message.answer("Введите промт в окне настроек и отправьте ещё раз.", reply_markup=get_cancel_keyboard())
        return

    generation_type = (payload.get("generationType") or "text2video").lower()
    if generation_type not in {"text2video", "image2video"}:
        generation_type = "text2video"

    try:
        duration_value = int(float(payload.get("duration") or payload.get("seconds") or 10))
    except (TypeError, ValueError):
        duration_value = 10
    allowed_durations = [10, 15]
    if duration_value not in allowed_durations:
        duration_value = allowed_durations[0]

    aspect_ratio = (
        payload.get("aspectRatio")
        or payload.get("aspect_ratio")
        or (model.default_params or {}).get("aspect_ratio")
        or "16:9"
    )
    if aspect_ratio not in {"16:9", "9:16", "1:1"}:
        aspect_ratio = "16:9"

    allowed_resolutions = _resolve_sora_resolutions(model)
    requested_resolution = (
        payload.get("resolution")
        or (model.default_params or {}).get("resolution")
        or allowed_resolutions[0]
    )
    resolution = _normalize_resolution_value(requested_resolution)
    if resolution not in allowed_resolutions:
        resolution = allowed_resolutions[0]

    params = {
        "duration": duration_value,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
    }

    source_media = {}
    if generation_type == "image2video":
        image_b64 = payload.get("imageData")
        if not image_b64:
            await message.answer(
                "Загрузите изображение для режима Image → Video.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        try:
            raw = base64.b64decode(image_b64)
        except Exception:
            await message.answer(
                "Не удалось прочитать изображение. Загрузите файл ещё раз.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        if len(raw) > MAX_KLING_IMAGE_BYTES:
            await message.answer(
                "Изображение слишком большое. Максимум 10 МБ.",
                reply_markup=get_cancel_keyboard(),
            )
            return

        mime = payload.get("imageMime") or "image/png"
        file_name = payload.get("imageName") or "image.png"
        png_bytes = _convert_to_png_bytes(raw, mime)
        try:
            upload_obj = await sync_to_async(supabase_upload_png)(png_bytes)
        except Exception as exc:  # pragma: no cover - сеть/хранилище
            await ErrorTracker.alog(
                origin=BotErrorEvent.Origin.TELEGRAM,
                severity=BotErrorEvent.Severity.WARNING,
                handler="video_generation.handle_sora_webapp_data",
                chat_id=message.chat.id,
                payload={"reason": "supabase_upload_failed"},
                exc=exc,
            )
            await message.answer(
                "Не удалось загрузить изображение в хранилище. Попробуйте другой файл.",
                reply_markup=get_cancel_keyboard(),
            )
            await state.clear()
            return

        image_url = _extract_public_url(upload_obj)
        if not image_url:
            await message.answer(
                "Не удалось получить ссылку на изображение. Попробуйте снова.",
                reply_markup=get_cancel_keyboard(),
            )
            await state.clear()
            return

        params["image_url"] = image_url
        params["input_image_mime_type"] = mime
        source_media = {
            "file_name": file_name,
            "mime_type": mime,
            "storage_url": image_url,
            "size_bytes": len(raw),
            "source": "sora_webapp",
        }

    try:
        user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)
    except TgUser.DoesNotExist:
        await message.answer(
            "Не удалось найти пользователя. Начните заново.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            duration=duration_value,
            video_resolution=resolution,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except Exception as exc:
        await message.answer(
            "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.ERROR,
            handler="video_generation.handle_sora_webapp_data",
            chat_id=message.chat.id,
            payload={
                "generation_type": generation_type,
                "duration": duration_value,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
            },
            exc=exc,
        )
        await state.clear()
        return

    await _send_generation_start_message(
        message,
        get_generation_start_message(
            model=model.display_name,
            mode=generation_type,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            duration=duration_value,
            prompt=prompt,
        ),
    )

    generate_video_task.delay(gen_request.id)
    await state.clear()


async def _handle_runway_webapp_data_impl(message: Message, state: FSMContext, payload: dict):
    """Принимаем данные Runway WebApp и запускаем генерацию (только image2video)."""
    data = await state.get_data()
    model_slug = payload.get("modelSlug") or data.get("model_slug") or data.get("selected_model") or "runway_gen4"

    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        await message.answer(
            "Модель Runway недоступна. Выберите её заново из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    if model.provider != "useapi":
        await message.answer(
            "Эта WebApp работает только с моделью Runway.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    if model.type != "video":
        await message.answer(
            "Эта WebApp работает только с видео-моделью Runway.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    await state.update_data(model_id=int(model.id), model_slug=str(model.slug), model_provider=str(model.provider))

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        await message.answer("Введите промт в окне Runway и отправьте ещё раз.", reply_markup=get_cancel_keyboard())
        return
    if len(prompt) > model.max_prompt_length:
        await message.answer(
            f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    allowed_durations = _extract_duration_options(model) or [5, 10]
    try:
        duration_value = int(float(payload.get("duration") or payload.get("seconds") or allowed_durations[0]))
    except (TypeError, ValueError):
        duration_value = allowed_durations[0]
    if duration_value not in allowed_durations:
        duration_value = allowed_durations[0]

    allowed_aspects = _extract_allowed_aspect_ratios(model) or ["16:9", "9:16", "1:1", "3:4", "4:3"]
    requested_aspect = (
        payload.get("aspectRatio")
        or payload.get("aspect_ratio")
        or (model.default_params or {}).get("aspect_ratio")
        or allowed_aspects[0]
    )
    aspect_ratio = requested_aspect if requested_aspect in allowed_aspects else allowed_aspects[0]

    allowed_resolutions = _order_resolutions(
        _normalize_allowed_resolutions(_extract_allowed_resolutions(model)) or ["720p", "1080p"]
    )
    requested_resolution = _normalize_resolution_value(
        payload.get("resolution") or (model.default_params or {}).get("resolution") or allowed_resolutions[0]
    )
    resolution = requested_resolution if requested_resolution in allowed_resolutions else allowed_resolutions[0]

    image_b64 = payload.get("imageData")
    if not image_b64:
        await message.answer("Загрузите изображение для режима Изображение → Видео.", reply_markup=get_cancel_keyboard())
        return
    try:
        raw = base64.b64decode(image_b64)
    except Exception:
        await message.answer(
            "Не удалось прочитать изображение. Загрузите файл ещё раз.",
            reply_markup=get_cancel_keyboard(),
        )
        return
    if len(raw) > MAX_KLING_IMAGE_BYTES:
        await message.answer(
            "Изображение слишком большое. Максимум 10 МБ.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    mime = payload.get("imageMime") or "image/png"
    file_name = payload.get("imageName") or "image.png"
    png_bytes = _convert_to_png_bytes(raw, mime)
    try:
        upload_obj = await sync_to_async(supabase_upload_png)(png_bytes)
    except Exception as exc:  # pragma: no cover - сеть/хранилище
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="video_generation.handle_runway_webapp_data",
            chat_id=message.chat.id,
            payload={"reason": "supabase_upload_failed"},
            exc=exc,
        )
        await message.answer(
            "Не удалось загрузить изображение в хранилище. Попробуйте другой файл.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    image_url = _extract_public_url(upload_obj)
    if not image_url:
        await message.answer(
            "Не удалось получить ссылку на изображение. Попробуйте снова.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    params = {
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration": duration_value,
        "seconds": duration_value,
        "image_url": image_url,
        "input_image_mime_type": mime,
    }
    if model.api_model_name:
        params.setdefault("api_model", model.api_model_name)

    source_media = {
        "file_name": file_name,
        "mime_type": mime,
        "storage_url": image_url,
        "size_bytes": len(raw),
        "source": "runway_webapp",
    }

    try:
        user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)
    except TgUser.DoesNotExist:
        await message.answer(
            "Не удалось найти пользователя. Начните заново.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type="image2video",
            generation_params=params,
            duration=duration_value,
            video_resolution=resolution,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except Exception as exc:
        await message.answer(
            "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.ERROR,
            handler="video_generation.handle_runway_webapp_data",
            chat_id=message.chat.id,
            payload={
                "duration": duration_value,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
            },
            exc=exc,
        )
        await state.clear()
        return

    await _send_generation_start_message(
        message,
        get_generation_start_message(
            model=model.display_name,
            mode="image2video",
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            duration=duration_value,
            prompt=prompt,
        ),
    )

    generate_video_task.delay(gen_request.id)
    await state.clear()


async def _handle_midjourney_video_webapp_data_impl(message: Message, state: FSMContext, payload: dict):
    """Принимаем данные Midjourney Video WebApp и запускаем генерацию (только image2video)."""
    data = await state.get_data()
    model_slug = payload.get("modelSlug") or data.get("model_slug") or data.get("selected_model") or "midjourney-video"

    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        await message.answer(
            "Модель Midjourney недоступна. Выберите её заново из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    if model.provider != "midjourney" or model.type != "video":
        await message.answer(
            "Эта WebApp работает только с моделью Midjourney для видео.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    await state.update_data(
        model_id=int(model.id),
        model_slug=str(model.slug),
        model_provider=str(model.provider),
        selected_model=str(model.slug),
    )

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        await message.answer("Введите промт в окне Midjourney Video и отправьте ещё раз.", reply_markup=get_cancel_keyboard())
        return
    if len(prompt) > model.max_prompt_length:
        await message.answer(
            f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    try:
        user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)
    except TgUser.DoesNotExist:
        await message.answer(
            "Не удалось найти пользователя. Начните заново.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    defaults = model.default_params or {}
    try:
        duration_value = int(defaults.get("duration") or 10)
    except (TypeError, ValueError):
        duration_value = 10

    allowed_aspects = _extract_allowed_aspect_ratios(model) or ["16:9", "9:16", "1:1", "2:1", "1:2", "4:3", "3:4"]
    requested_aspect = (
        payload.get("aspectRatio")
        or payload.get("aspect_ratio")
        or defaults.get("aspect_ratio")
        or "16:9"
    )
    aspect_ratio = requested_aspect if requested_aspect in allowed_aspects else (defaults.get("aspect_ratio") or allowed_aspects[0])

    version_value = payload.get("version") or payload.get("modelVersion") or defaults.get("version") or "7"

    image_b64 = payload.get("imageData")
    if not image_b64:
        await message.answer("Загрузите изображение в WebApp для Midjourney Video.", reply_markup=get_cancel_keyboard())
        return
    try:
        raw = base64.b64decode(image_b64)
    except Exception:
        await message.answer(
            "Не удалось прочитать изображение. Загрузите файл ещё раз.",
            reply_markup=get_cancel_keyboard(),
        )
        return
    if len(raw) > MAX_KLING_IMAGE_BYTES:
        await message.answer(
            "Изображение слишком большое. Максимум 10 МБ.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    mime = payload.get("imageMime") or "image/png"
    file_name = payload.get("imageName") or "image.png"
    png_bytes = _convert_to_png_bytes(raw, mime)
    try:
        upload_obj = await sync_to_async(supabase_upload_png)(png_bytes)
    except Exception as exc:  # pragma: no cover - сеть/хранилище
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="video_generation.handle_midjourney_video_webapp_data",
            chat_id=message.chat.id,
            payload={"reason": "supabase_upload_failed"},
            exc=exc,
        )
        await message.answer(
            "Не удалось загрузить изображение в хранилище. Попробуйте другой файл.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    image_url = _extract_public_url(upload_obj)
    if not image_url:
        await message.answer(
            "Не удалось получить ссылку на изображение. Попробуйте снова.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.clear()
        return

    params = {
        "aspect_ratio": aspect_ratio,
        "version": version_value,
        "image_url": image_url,
    }
    source_media = {
        "file_name": file_name,
        "mime_type": mime,
        "storage_url": image_url,
        "size_bytes": len(raw),
        "source": "midjourney_video_webapp",
    }

    try:
        _, cost_tokens = await sync_to_async(calculate_request_cost)(
            model, quantity=1, duration=duration_value, params=params
        )
        can_generate, error_msg = await sync_to_async(BalanceService.check_can_generate)(
            user,
            model,
            quantity=1,
            total_cost_tokens=cost_tokens,
        )
        if not can_generate:
            await message.answer(
                f"❌ {error_msg}",
                reply_markup=get_main_menu_inline_keyboard(),
            )
            await state.clear()
            return
    except Exception as exc:
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="video_generation.handle_midjourney_video_webapp_data.balance_check",
            chat_id=message.chat.id,
            payload={"model": model.slug},
            exc=exc,
        )
        # При ошибке продолжаем — сервис проверит баланс перед запуском

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type="image2video",
            generation_params=params,
            duration=duration_value,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except Exception as exc:
        await message.answer(
            "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.ERROR,
            handler="video_generation.handle_midjourney_video_webapp_data",
            chat_id=message.chat.id,
            payload={"aspect_ratio": aspect_ratio},
            exc=exc,
        )
        await state.clear()
        return

    await _send_generation_start_message(
        message,
        get_generation_start_message(
            model=model.display_name,
            mode="image2video",
            aspect_ratio=aspect_ratio,
            resolution=None,
            duration=duration_value,
            prompt=prompt,
        ),
    )

    generate_video_task.delay(gen_request.id)
    await state.clear()

async def _handle_kling_webapp_data_impl(message: Message, state: FSMContext, payload: dict):
    """Принимаем данные Kling WebApp и запускаем генерацию."""
    data = await state.get_data()
    model_slug = payload.get("modelSlug") or data.get("model_slug") or data.get("selected_model") or "kling-v2-5-turbo"
    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        await message.answer(
            "Модель Kling недоступна. Выберите её заново из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return
    if model.provider != "kling":
        await message.answer(
            "Эта WebApp работает только с моделью Kling. Выберите её из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return
    await state.update_data(
        model_id=int(model.id),
        model_slug=str(model.slug),
        model_provider=str(model.provider),
        selected_model=str(model.slug),
    )

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        await message.answer("Введите промт в окне Kling и отправьте ещё раз.", reply_markup=get_cancel_keyboard())
        return
    if len(prompt) > model.max_prompt_length:
        await message.answer(
            f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    try:
        user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)
    except TgUser.DoesNotExist:
        await message.answer(
            "Не удалось найти пользователя. Начните заново.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    try:
        cost_tokens = await sync_to_async(get_base_price_tokens)(model)
        can_generate, error_msg = await sync_to_async(BalanceService.check_can_generate)(
            user,
            model,
            total_cost_tokens=cost_tokens,
        )
        if not can_generate:
            await message.answer(
                f"❌ {error_msg}",
                reply_markup=get_main_menu_inline_keyboard(),
            )
            await state.clear()
            return
    except Exception:
        # Проверку баланса пропускаем при ошибке — сервис проверит перед запуском задачи
        pass

    generation_type = (payload.get("generationType") or "text2video").lower()
    if generation_type not in {"text2video", "image2video"}:
        generation_type = "text2video"

    try:
        duration_raw = payload.get("duration")
        duration_value = int(float(duration_raw))
    except (TypeError, ValueError):
        duration_value = 5
    if duration_value not in {5, 10}:
        duration_value = 5

    cfg_scale_value = payload.get("cfgScale")
    try:
        cfg_scale_value = max(0.0, min(1.0, round(float(cfg_scale_value), 1)))
    except (TypeError, ValueError):
        cfg_scale_value = 0.5

    defaults = model.default_params or {}
    allowed_aspects = _extract_allowed_aspect_ratios(model) or ["16:9", "9:16", "1:1"]
    requested_aspect = (
        payload.get("aspectRatio")
        or payload.get("aspect_ratio")
        or defaults.get("aspect_ratio")
        or "16:9"
    )
    fallback_aspect = defaults.get("aspect_ratio")
    if fallback_aspect not in allowed_aspects:
        fallback_aspect = allowed_aspects[0]
    aspect_ratio = requested_aspect if requested_aspect in allowed_aspects else fallback_aspect

    params = {
        "duration": duration_value,
        "cfg_scale": cfg_scale_value,
        "aspect_ratio": aspect_ratio,
    }

    source_media = None

    if generation_type == "image2video":
        image_b64 = payload.get("imageData")
        if not image_b64:
            await message.answer(
                "Загрузите изображение в WebApp для режима Image → Video.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        try:
            raw = base64.b64decode(image_b64)
        except Exception:
            await message.answer(
                "Не удалось прочитать изображение. Загрузите файл ещё раз.",
                reply_markup=get_cancel_keyboard(),
            )
            return

        if len(raw) > MAX_KLING_IMAGE_BYTES:
            await message.answer(
                "Изображение слишком большое. Максимум 10 МБ.",
                reply_markup=get_cancel_keyboard(),
            )
            return

        mime = payload.get("imageMime") or "image/png"
        file_name = payload.get("imageName") or "image.png"

        png_bytes = _convert_to_png_bytes(raw, mime)
        try:
            upload_obj = await sync_to_async(supabase_upload_png)(png_bytes)
        except Exception as exc:  # pragma: no cover - сеть/хранилище
            await ErrorTracker.alog(
                origin=BotErrorEvent.Origin.TELEGRAM,
                severity=BotErrorEvent.Severity.WARNING,
                handler="video_generation.handle_kling_webapp_data",
                chat_id=message.chat.id,
                payload={"reason": "supabase_upload_failed"},
                exc=exc,
            )
            await message.answer(
                "Не удалось загрузить изображение в хранилище. Попробуйте другой файл.",
                reply_markup=get_cancel_keyboard(),
            )
            await state.clear()
            return

        image_url = _extract_public_url(upload_obj)
        if not image_url:
            await message.answer(
                "Не удалось получить ссылку на изображение. Попробуйте снова.",
                reply_markup=get_cancel_keyboard(),
            )
            await state.clear()
            return

        params["image_url"] = image_url
        source_media = {
            "file_name": file_name,
            "mime_type": mime,
            "storage_url": image_url,
            "size_bytes": len(raw),
            "source": "kling_webapp",
        }

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            duration=duration_value,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except Exception as exc:
        await message.answer(
            "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.ERROR,
            handler="video_generation.handle_kling_webapp_data",
            chat_id=message.chat.id,
            payload={
                "generation_type": generation_type,
                "duration": duration_value,
                "aspect_ratio": aspect_ratio,
            },
            exc=exc,
        )
        await state.clear()
        return

    await _send_generation_start_message(
        message,
        get_generation_start_message(
            model=model.display_name,
            mode=generation_type,
            aspect_ratio=aspect_ratio,
            resolution=None,
            duration=duration_value,
            prompt=prompt,
        ),
    )

    generate_video_task.delay(gen_request.id)
    await state.clear()


async def _handle_veo_webapp_data_impl(message: Message, state: FSMContext, payload: dict):
    """Принимаем данные Veo WebApp и запускаем генерацию."""
    data = await state.get_data()
    model_slug = payload.get("modelSlug") or data.get("model_slug") or data.get("selected_model") or "veo3-fast"

    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        await message.answer(
            "Модель Veo недоступна. Выберите её заново из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    if model.provider != "veo":
        await message.answer(
            "Эта WebApp работает только с моделью Veo. Выберите её из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    await state.update_data(model_id=int(model.id), model_slug=str(model.slug), model_provider=str(model.provider))

    params_payload = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    prompt = (payload.get("prompt") or params_payload.get("prompt") or "").strip()
    if not prompt:
        await message.answer("Введите промт в окне Veo и отправьте ещё раз.", reply_markup=get_cancel_keyboard())
        return
    if len(prompt) > model.max_prompt_length:
        await message.answer(
            f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    mode_value = (payload.get("mode") or params_payload.get("mode") or "text2video").lower()
    generation_type = "image2video" if mode_value == "image2video" else "text2video"

    defaults = model.default_params or {}
    aspect_ratio = (
        params_payload.get("aspectRatio")
        or params_payload.get("aspect_ratio")
        or payload.get("aspectRatio")
        or payload.get("aspect_ratio")
        or data.get("default_aspect_ratio")
        or defaults.get("aspect_ratio")
        or "9:16"
    )
    allowed_ratios = _extract_allowed_aspect_ratios(model) or ["9:16", "16:9", "1:1"]
    if aspect_ratio not in allowed_ratios:
        aspect_ratio = allowed_ratios[0]

    duration = data.get("default_duration") or defaults.get("duration") or 8
    allowed_resolutions = _resolve_veo_resolutions(model, aspect_ratio)
    requested_resolution = (
        params_payload.get("resolution")
        or payload.get("resolution")
        or data.get("default_resolution")
        or defaults.get("resolution")
        or allowed_resolutions[0]
    )
    resolution = _normalize_resolution_value(requested_resolution)
    if resolution not in allowed_resolutions:
        resolution = allowed_resolutions[0]

    input_images = []
    final_frame = None

    def _prepare_inline_image(raw_b64, mime, name):
        if not raw_b64:
            raise ValueError("missing")
        try:
            decoded = base64.b64decode(raw_b64)
        except Exception as exc:
            raise ValueError("decode") from exc
        if len(decoded) > MAX_VEO_IMAGE_BYTES:
            raise ValueError("too_large")
        normalized = base64.b64encode(decoded).decode("ascii")
        return {
            "content_base64": normalized,
            "mime_type": mime or "image/png",
            "filename": name or "image.png",
        }

    if generation_type == "image2video":
        start_raw = (
            params_payload.get("startImage")
            or params_payload.get("start_image")
            or payload.get("startImage")
            or payload.get("start_image")
        )
        start_mime = (
            params_payload.get("startImageMime")
            or params_payload.get("start_image_mime")
            or payload.get("startImageMime")
            or payload.get("start_image_mime")
        )
        start_name = (
            params_payload.get("startImageName")
            or params_payload.get("start_image_name")
            or payload.get("startImageName")
            or payload.get("start_image_name")
        )

        if not start_raw:
            await message.answer("Загрузите начальный кадр (до 5 МБ).", reply_markup=get_cancel_keyboard())
            return

        try:
            start_image = _prepare_inline_image(start_raw, start_mime, start_name)
        except ValueError as exc:
            reason = str(exc)
            if reason == "too_large":
                await message.answer(
                    "Начальный кадр превышает 5 МБ. Загрузите файл поменьше.",
                    reply_markup=get_cancel_keyboard(),
                )
            else:
                await message.answer(
                    "Не удалось прочитать начальный кадр. Попробуйте загрузить другое изображение.",
                    reply_markup=get_cancel_keyboard(),
                )
            return

        input_images.append(start_image)

        end_raw = (
            params_payload.get("endImage")
            or params_payload.get("end_image")
            or payload.get("endImage")
            or payload.get("end_image")
        )
        if end_raw:
            end_mime = (
                params_payload.get("endImageMime")
                or params_payload.get("end_image_mime")
                or payload.get("endImageMime")
                or payload.get("end_image_mime")
            )
            end_name = (
                params_payload.get("endImageName")
                or params_payload.get("end_image_name")
                or payload.get("endImageName")
                or payload.get("end_image_name")
            )

            try:
                final_frame = _prepare_inline_image(end_raw, end_mime, end_name)
            except ValueError as exc:
                reason = str(exc)
                if reason == "too_large":
                    await message.answer(
                        "Конечный кадр превышает 5 МБ. Загрузите файл поменьше или оставьте поле пустым.",
                        reply_markup=get_cancel_keyboard(),
                    )
                else:
                    await message.answer(
                        "Не удалось прочитать конечный кадр. Попробуйте другой файл или оставьте поле пустым.",
                        reply_markup=get_cancel_keyboard(),
                    )
                return

    generation_params = {
        "duration": duration,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
    }
    if final_frame:
        generation_params["final_frame"] = final_frame

    try:
        user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)
    except TgUser.DoesNotExist:
        await message.answer(
            "Не удалось найти пользователя. Начните заново.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    try:
        _, cost_tokens = await sync_to_async(calculate_request_cost)(
            model, quantity=1, duration=duration, params=generation_params
        )
        can_generate, error_msg = await sync_to_async(BalanceService.check_can_generate)(
            user, model, quantity=1, total_cost_tokens=cost_tokens
        )
        if not can_generate:
            await message.answer(
                f"❌ {error_msg}",
                reply_markup=get_main_menu_inline_keyboard(),
            )
            await state.clear()
            return
    except Exception as exc:
        await message.answer(
            "❌ Произошла ошибка при проверке баланса. Попробуйте позже.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="video_generation.handle_veo_webapp_data.balance_check",
            chat_id=message.chat.id,
            payload={"model": model.slug},
            exc=exc,
        )
        await state.clear()
        return

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            input_images=input_images,
            generation_params=generation_params,
            duration=duration,
            video_resolution=resolution,
            aspect_ratio=aspect_ratio,
        )
    except InsufficientBalanceError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except Exception as exc:
        await message.answer(
            "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.ERROR,
            handler="video_generation.handle_veo_webapp_data",
            chat_id=message.chat.id,
            payload={
                "generation_type": generation_type,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
            },
            exc=exc,
        )
        await state.clear()
        return

    await _send_generation_start_message(
        message,
        get_generation_start_message(
            model=model.display_name,
            mode=generation_type,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            duration=duration,
            prompt=prompt,
        ),
    )

    generate_video_task.delay(gen_request.id)
    await state.clear()


async def _prompt_user_for_description(
    message: Message,
    *,
    supports_images: bool,
    aspect_ratio: str,
    duration: Optional[int],
    resolution: Optional[str] = None,
    is_sora: bool = False,
) -> None:
    """Отправить пользователю инструкции по вводу промта."""
    image_hint = _calculate_image_size_hint(
        supports_images=supports_images,
        is_sora=is_sora,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
    )
    size_hint = _format_image_hint_text(image_hint) if supports_images else ""

    segments = [
        "✍️  Напиши в чат промт для генерации видео из текста.",
        "🖼 Если хотите сгенерировать видео из изображения, отправьте в чат одно изображение + текстовый промт."
        f" {size_hint}".strip(),
        f"Формат выбран: {aspect_ratio}",
    ]
    if duration:
        segments.append(f"Длительность: {duration} сек.")
    if resolution:
        segments.append(f"Качество: {resolution.lower()}")

    intro = ["\n\n".join(segments)]

    await message.answer(
        "\n".join(intro),
        reply_markup=get_cancel_keyboard()
    )


async def _maybe_prompt_resolution(message: Message, state: FSMContext) -> bool:
    """
    Попросить выбрать разрешение, если требуется (Sora).
    Возвращает True, если показали клавиатуру выбора разрешения.
    """
    data = await state.get_data()
    if not data.get('is_sora'):
        return False
    options = data.get('resolution_options') or []
    selected_resolution = data.get('selected_resolution')
    if not options or selected_resolution:
        return False

    await state.set_state(BotStates.video_select_resolution)
    await message.answer(
        "Выберите качество видео:\n"
        "• 720p — быстрее и дешевле\n"
        "• 1080p — выше детализация",
        reply_markup=get_video_resolution_keyboard(options),
    )
    return True


# Обработчик кнопки "🎬 Создать видео" перенесен в global_commands.py
# чтобы работать из любого состояния

# Обработчик выбора модели "vid_model:" также перенесен в global_commands.py
# чтобы работать из любого состояния


@router.message(BotStates.video_select_format)
async def wait_format_selection(message: Message, state: FSMContext):
    """Напоминаем выбрать формат, если пользователь отправил что-то раньше времени."""
    await message.answer(
        "Пожалуйста, выберите формат видео, используя кнопки ниже.",
        reply_markup=get_video_format_keyboard()
    )


@router.message(BotStates.video_select_duration)
async def wait_duration_selection(message: Message, state: FSMContext):
    """Напоминаем выбрать длительность, если пользователь отправил что-то раньше времени."""
    data = await state.get_data()
    duration_options = data.get('duration_options') or []
    if not duration_options:
        duration_options = [data.get('default_duration', 8)]
    await message.answer(
        "Выберите длительность ролика, используя кнопки ниже.",
        reply_markup=get_video_duration_keyboard(duration_options),
    )


@router.message(BotStates.video_select_resolution)
async def wait_resolution_selection(message: Message, state: FSMContext):
    """Напоминаем выбрать качество, если пользователь пишет вместо кнопок."""
    data = await state.get_data()
    options = data.get('resolution_options') or ["720p", "1080p"]
    await message.answer(
        "Выберите качество видео с помощью кнопок ниже.",
        reply_markup=get_video_resolution_keyboard(options),
    )


@router.callback_query(
    StateFilter("*"),
    F.data.startswith("video_format:"),
)
async def set_video_format(callback: CallbackQuery, state: FSMContext):
    """Сохраняем выбранное соотношение сторон и переходим к сбору промта."""
    await callback.answer()

    ratio_raw = callback.data.split(":", maxsplit=1)[1]
    aspect_ratio = ratio_raw.replace("_", ":") if "_" in ratio_raw else ratio_raw

    data = await state.get_data()
    # Если стейт пустой (потерян), а пользователь нажал кнопку формата
    if not data:
        await callback.message.answer(
            "⚠️ Сессия устарела. Пожалуйста, начните создание видео заново.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    supports_images = data.get('supports_images', False)
    duration_options = data.get('duration_options') or []
    default_duration = data.get('default_duration')

    await state.update_data(
        selected_aspect_ratio=aspect_ratio,
        generation_type='text2video',
        input_image_file_id=None,
        input_image_mime_type=None,
        selected_duration=None,
    )

    if duration_options:
        await state.set_state(BotStates.video_select_duration)
        await callback.message.answer(
            "Выберите длительность ролика:",
            reply_markup=get_video_duration_keyboard(duration_options),
        )
        return

    selected_duration = data.get('selected_duration') or default_duration
    await state.update_data(selected_duration=selected_duration)

    if await _maybe_prompt_resolution(callback.message, state):
        return

    resolution_value = data.get('selected_resolution') or data.get('default_resolution')
    await _prompt_user_for_description(
        callback.message,
        supports_images=supports_images,
        aspect_ratio=aspect_ratio,
        duration=selected_duration,
        resolution=resolution_value,
        is_sora=data.get('is_sora', False),
    )
    await state.set_state(BotStates.video_wait_prompt)


@router.callback_query(
    StateFilter("*"),
    F.data.startswith("video_duration:"),
)
async def set_video_duration(callback: CallbackQuery, state: FSMContext):
    """Сохраняем выбранную длительность и переходим к сбору промта."""
    await callback.answer()

    data = await state.get_data()
    if not data:
        await callback.message.answer(
            "⚠️ Сессия устарела. Пожалуйста, начните создание видео заново.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    duration_options = data.get('duration_options') or []
    keyboard_options = duration_options or [data.get('default_duration', 8)]

    try:
        duration_value = int(callback.data.split(":", maxsplit=1)[1])
    except (ValueError, IndexError):
        await callback.message.answer(
            "Не удалось распознать выбранную длительность. Попробуйте снова.",
            reply_markup=get_video_duration_keyboard(keyboard_options),
        )
        return

    if duration_options and duration_value not in duration_options:
        await callback.message.answer(
            "Эта длительность недоступна для выбранной модели. Пожалуйста, выберите из списка ниже.",
            reply_markup=get_video_duration_keyboard(duration_options),
        )
        return

    supports_images = data.get('supports_images', False)
    aspect_ratio = data.get('selected_aspect_ratio', '16:9')

    await state.update_data(selected_duration=duration_value)

    if await _maybe_prompt_resolution(callback.message, state):
        return

    resolution_value = data.get('selected_resolution') or data.get('default_resolution')
    await _prompt_user_for_description(
        callback.message,
        supports_images=supports_images,
        aspect_ratio=aspect_ratio,
        duration=duration_value,
        resolution=resolution_value,
        is_sora=data.get('is_sora', False),
    )

    await state.set_state(BotStates.video_wait_prompt)


@router.callback_query(
    StateFilter("*"),
    F.data.startswith("video_resolution:"),
)
async def set_video_resolution(callback: CallbackQuery, state: FSMContext):
    """Сохраняем выбранное качество и переходим к сбору промта."""
    await callback.answer()

    data = await state.get_data()
    if not data:
         await callback.message.answer(
            "⚠️ Сессия устарела. Пожалуйста, начните создание видео заново.",
            reply_markup=get_main_menu_inline_keyboard()
        )
         return
         
    options = [opt.lower() for opt in (data.get('resolution_options') or [])]

    try:
        value = callback.data.split(":", maxsplit=1)[1].lower()
    except (ValueError, IndexError):
        await callback.message.answer(
            "Не удалось распознать выбранное качество. Попробуйте снова.",
            reply_markup=get_video_resolution_keyboard(data.get('resolution_options') or ["720p", "1080p"]),
        )
        return

    if options and value not in options:
        await callback.message.answer(
            "Это качество недоступно. Выберите вариант из списка.",
            reply_markup=get_video_resolution_keyboard(data.get('resolution_options') or ["720p", "1080p"]),
        )
        return

    await state.update_data(selected_resolution=value)

    supports_images = data.get('supports_images', False)
    aspect_ratio = data.get('selected_aspect_ratio', '16:9')
    duration = data.get('selected_duration') or data.get('default_duration')
    resolution_value = value

    await _prompt_user_for_description(
        callback.message,
        supports_images=supports_images,
        aspect_ratio=aspect_ratio,
        duration=duration,
        resolution=resolution_value,
        is_sora=data.get('is_sora', False),
    )
    await state.set_state(BotStates.video_wait_prompt)


@router.message(BotStates.video_wait_prompt, F.photo)
async def receive_image_for_video(message: Message, state: FSMContext):
    """
    Получаем изображение для генерации видео (image2video)
    """
    data = await state.get_data()

    # Проверяем, поддерживает ли модель изображения
    if not data.get('supports_images'):
        await message.answer(
            "❌ Эта модель не поддерживает входные изображения.\n"
            "Отправьте текстовое описание.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    # Получаем file_id самого большого размера фото
    photo = message.photo[-1]

    resolution_value = data.get('selected_resolution') or data.get('default_resolution')
    aspect_ratio = data.get('selected_aspect_ratio') or data.get('default_aspect_ratio')
    hint_text = _format_image_hint_text(
        _calculate_image_size_hint(
            supports_images=True,
            is_sora=data.get('is_sora', False),
            resolution=resolution_value,
            aspect_ratio=aspect_ratio,
        )
    )

    # Сохраняем изображение в состоянии
    await state.update_data(
        input_image_file_id=photo.file_id,
        input_image_mime_type='image/jpeg'
    )

    # Запрашиваем текстовое описание
    text = (
        "✅ Изображение загружено!\n\n"
        "Теперь отправьте текстовое описание для генерации видео на основе этого изображения."
    )
    if hint_text:
        text += f"\n\nℹ️ {hint_text}"

    await message.answer(text, reply_markup=get_cancel_keyboard())

    # Переходим в состояние ожидания промта для image2video
    await state.set_state(BotStates.video_wait_prompt)
    await state.update_data(generation_type='image2video')


@router.message(BotStates.video_wait_prompt, F.document)
async def receive_document_for_video(message: Message, state: FSMContext):
    """Обрабатываем документ (изображение/видео) как источник для image2video."""
    data = await state.get_data()
    if not data.get('supports_images'):
        await message.answer(
            "❌ Эта модель не поддерживает входные файлы.\n"
            "Отправьте текстовое описание.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    document = message.document
    if not document:
        await message.answer(
            "Не удалось получить файл. Попробуйте снова.",
            reply_markup=get_cancel_keyboard()
        )
        return

    allowed_types = {"image/jpeg", "image/png", "image/webp", "video/mp4"}
    mime_type = (document.mime_type or "").lower()
    if mime_type not in allowed_types:
        await message.answer(
            "⚠️ Поддерживаются только файлы JPG, PNG, WEBP или MP4.\n"
            "Отправьте другое изображение или фото.",
            reply_markup=get_cancel_keyboard()
        )
        return

    await state.update_data(
        input_image_file_id=document.file_id,
        input_image_mime_type=mime_type,
        generation_type='image2video',
    )

    resolution_value = data.get('selected_resolution') or data.get('default_resolution')
    aspect_ratio = data.get('selected_aspect_ratio') or data.get('default_aspect_ratio')
    hint_text = _format_image_hint_text(
        _calculate_image_size_hint(
            supports_images=True,
            is_sora=data.get('is_sora', False),
            resolution=resolution_value,
            aspect_ratio=aspect_ratio,
        )
    )

    text = (
        "✅ Файл загружен!\n\n"
        "Теперь отправьте текстовое описание, чтобы запустить генерацию."
    )
    if hint_text:
        text += f"\n\nℹ️ {hint_text}"

    await message.answer(text, reply_markup=get_cancel_keyboard())


@router.message(BotStates.video_wait_prompt, F.text)
async def handle_video_prompt(message: Message, state: FSMContext):
    """Обрабатываем текстовый промт для генерации видео (txt2video / img2video)."""
    data = await state.get_data()
    prompt = message.text.strip()

    try:
        model = await sync_to_async(AIModel.objects.get)(id=data['model_id'])
    except (KeyError, AIModel.DoesNotExist):
        await message.answer(
            "❌ Не удалось найти модель. Начните заново с /start.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    if len(prompt) > model.max_prompt_length:
        await message.answer(
            f"❌ Промт слишком длинный!\n"
            f"Максимальная длина: {model.max_prompt_length} символов\n"
            f"Ваш промт: {len(prompt)} символов",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    generation_type = data.get('generation_type', 'text2video')
    default_duration = data.get('default_duration') or model.default_params.get('duration') or 8
    selected_duration = data.get('selected_duration') or default_duration
    default_resolution = data.get('default_resolution') or model.default_params.get('resolution') or '720p'
    default_aspect_ratio = data.get('default_aspect_ratio') or model.default_params.get('aspect_ratio') or '16:9'
    selected_aspect_ratio = data.get('selected_aspect_ratio') or default_aspect_ratio
    selected_resolution = data.get('selected_resolution') or default_resolution

    generation_params = {
        'duration': selected_duration,
        'resolution': selected_resolution,
        'aspect_ratio': selected_aspect_ratio,
    }

    input_image_file_id = data.get('input_image_file_id')
    input_image_mime_type = data.get('input_image_mime_type', 'image/jpeg')
    source_media = {}

    if generation_type == 'image2video' and input_image_file_id:
        generation_params['input_image_file_id'] = input_image_file_id
        generation_params['input_image_mime_type'] = input_image_mime_type
        source_media['telegram_file_id'] = input_image_file_id
        source_media['mime_type'] = input_image_mime_type
    else:
        generation_type = 'text2video'

    user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=generation_params,
            duration=selected_duration,
            video_resolution=selected_resolution,
            aspect_ratio=selected_aspect_ratio,
            input_image_file_id=input_image_file_id,
            source_media=source_media
        )
    except InsufficientBalanceError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except Exception as exc:
        await message.answer(
            f"❌ Произошла ошибка: {exc}",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="video_generation.receive_video_prompt",
            chat_id=message.chat.id,
            payload={
                "generation_type": generation_type,
                "model_id": data.get("model_id"),
                "duration": selected_duration,
                "resolution": selected_resolution,
                "aspect_ratio": selected_aspect_ratio,
            },
            exc=exc,
        )
        await state.clear()
        return

    await _send_generation_start_message(
        message,
        get_generation_start_message(
            model=model.display_name,
            mode=generation_type,
            aspect_ratio=selected_aspect_ratio,
            resolution=selected_resolution,
            duration=selected_duration,
            prompt=prompt,
        ),
    )

    generate_video_task.delay(gen_request.id)
    await state.clear()


@router.callback_query(StateFilter("*"), F.data.startswith("extend_video:"))
async def prompt_video_extension(callback: CallbackQuery, state: FSMContext):
    """Подготовить пользователя к продлению видео."""
    await callback.answer()
    
    # Очищаем стейт, так как это начало нового флоу (продления)
    await state.clear()

    try:
        request_id = int(callback.data.split(":", maxsplit=1)[1])
    except (ValueError, IndexError):
        await callback.message.answer(
            "Не удалось определить, какое видео продлить.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    try:
        gen_request = await sync_to_async(
            GenRequest.objects.select_related("ai_model", "user").get
        )(id=request_id)
    except GenRequest.DoesNotExist:
        await callback.message.answer(
            "Эта генерация больше недоступна.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    if gen_request.chat_id != callback.from_user.id:
        await callback.answer("Можно продлить только свои видео.", show_alert=True)
        return

    if gen_request.status != "done" or not gen_request.result_urls:
        await callback.message.answer(
            "Видео ещё обрабатывается. Попробуйте чуть позже.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    model = gen_request.ai_model
    if not model:
        await callback.message.answer(
            "Не удалось найти информацию о модели. Попробуйте сгенерировать новое видео.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return
    if model.provider != "veo":
        await callback.answer("Продление доступно только для Veo.", show_alert=True)
        return

    aspect_ratio = gen_request.aspect_ratio or gen_request.generation_params.get("aspect_ratio") or "не указан"
    base_price = await sync_to_async(get_base_price_tokens)(model)
    cost_text = f"⚡ Стоимость продления: {base_price:.2f} токенов."

    await state.update_data(
        extend_parent_request_id=gen_request.id,
    )
    await state.set_state(BotStates.video_extend_prompt)

    prompt_text = (
        "Можно продлить ваш ролик ещё на 8 секунд.\n\n"
        f"Модель: {model.display_name}\n"
        f"Аспект: {aspect_ratio}\n"
        f"{cost_text}\n\n"
        "Отправьте новый текст запроса или нажмите «Отмена»."
    )

    await callback.message.answer(prompt_text, reply_markup=get_cancel_keyboard())


@router.message(BotStates.video_extend_prompt, F.text)
async def handle_video_extension_prompt(message: Message, state: FSMContext):
    """Получаем текст для продления видео и запускаем задачу."""
    text = message.text.strip()
    if text.lower() in {"отмена", "cancel"}:
        await state.clear()
        await message.answer(
            "Продление отменено.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    data = await state.get_data()
    parent_request_id = data.get("extend_parent_request_id")

    if not parent_request_id:
        await message.answer(
            "Не удалось найти исходное видео. Попробуйте снова.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    try:
        parent_request = await sync_to_async(
            GenRequest.objects.select_related("ai_model", "user").get
        )(id=parent_request_id)
    except GenRequest.DoesNotExist:
        await message.answer(
            "Это видео больше недоступно для продления.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    if parent_request.chat_id != message.from_user.id:
        await message.answer(
            "Можно продлить только свои видео.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    model = parent_request.ai_model
    if not model:
        await message.answer(
            "Не удалось определить модель генерации. Попробуйте начать новую генерацию.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    if len(text) > model.max_prompt_length:
        await message.answer(
            f"❌ Промт слишком длинный! Максимальная длина: {model.max_prompt_length} символов.",
            reply_markup=get_cancel_keyboard()
        )
        return

    if not parent_request.result_urls:
        await message.answer(
            "Исходное видео ещё не готово. Попробуйте чуть позже.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    aspect_ratio = (
        parent_request.aspect_ratio
        or parent_request.generation_params.get("aspect_ratio")
        or (model.default_params or {}).get("aspect_ratio")
        or "16:9"
    )
    resolution = (
        parent_request.video_resolution
        or parent_request.generation_params.get("resolution")
        or (model.default_params or {}).get("resolution")
        or "720p"
    )

    generation_params = {
        "duration": 8,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "extend_parent_request_id": parent_request.id,
    }
    source_media = {
        "parent_request_id": parent_request.id,
        "parent_result_url": parent_request.result_urls[0],
    }

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=parent_request.user,
            ai_model=model,
            prompt=text,
            quantity=1,
            generation_type='image2video',
            generation_params=generation_params,
            duration=8,
            video_resolution=resolution,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
            parent_request=parent_request,
        )
    except InsufficientBalanceError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_main_menu_inline_keyboard())
        await state.clear()
        return
    except Exception as exc:
        await message.answer(
            f"❌ Произошла ошибка: {exc}",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="video_generation.extend_video_prompt",
            chat_id=message.chat.id,
            payload={
                "parent_request_id": parent_request.id if parent_request else None,
                "model_id": model.id if model else None,
                "prompt_length": len(text) if text else 0,
            },
            exc=exc,
        )
        await state.clear()
        return

    await _send_generation_start_message(
        message,
        get_generation_start_message(
            model=model.display_name if model else "—",
            mode="image2video",
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            duration=8,
            prompt=text,
        ),
    )

    extend_video_task.delay(gen_request.id)
    await state.clear()


@router.message(BotStates.video_extend_prompt)
async def remind_extension_prompt(message: Message):
    """Если прилетело что-то кроме текста во время ожидания промта."""
    await message.answer(
        "Отправьте текстовый промт для продления видео или нажмите «Отмена».",
        reply_markup=get_cancel_keyboard()
    )


@router.callback_query(StateFilter("*"), F.data == "main_menu")
async def handle_main_menu_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик inline кнопки "Главное меню"
    """
    await callback.answer()

    # Очищаем состояние
    await state.clear()
    await state.set_state(BotStates.main_menu)

    # Импортируем функцию главного меню из menu.py
    from django.conf import settings
    from botapp.keyboards import get_main_menu_keyboard

    PAYMENT_URL = getattr(settings, 'PAYMENT_MINI_APP_URL', 'https://example.com/payment')

    await callback.message.answer(
        "Выберите нужное  действие нажав на кнопку в меню 👇",
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )
