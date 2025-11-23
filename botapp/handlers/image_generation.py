"""
Обработчики генерации изображений
"""
import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
import base64

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from asgiref.sync import sync_to_async

from botapp.states import BotStates
from botapp.keyboards import (
    get_image_models_keyboard,
    get_model_info_message,
    get_cancel_keyboard,
    get_main_menu_inline_keyboard,
    get_image_mode_keyboard,
)
from botapp.models import TgUser, AIModel, BotErrorEvent
from botapp.business.generation import GenerationService
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.business.pricing import get_base_price_tokens
from botapp.tasks import generate_image_task
from botapp.error_tracker import ErrorTracker

router = Router()
logger = logging.getLogger(__name__)


# Обработчик кнопки "🎨 Создать изображение" перенесен в global_commands.py
# чтобы работать из любого состояния

# Обработчик выбора модели "img_model:" также перенесен в global_commands.py
# чтобы работать из любого состояния


@router.message(
    StateFilter("*"),
    F.web_app_data.data.contains("midjourney_settings"),
)
async def handle_midjourney_webapp_data(message: Message, state: FSMContext):
    """
    Принимаем данные из WebApp настроек Midjourney и запускаем/готовим генерацию.
    Поддерживает работу как с предварительно выбранной моделью, так и без неё.
    """
    user_id = message.from_user.id

    # Детальное логирование начала обработки
    logging.info(f"[MIDJOURNEY_WEBAPP] Начало обработки данных от пользователя {user_id}")
    print(f"[MIDJOURNEY_WEBAPP] web_app_data received from user={user_id}", flush=True)

    try:
        payload = json.loads(message.web_app_data.data or '{}')
        logging.info(f"[MIDJOURNEY_WEBAPP] Получен payload: {json.dumps(payload, ensure_ascii=False)[:500]}")
        print(f"[MIDJOURNEY_WEBAPP] payload raw: {message.web_app_data.data[:200]}", flush=True)
    except Exception as e:
        logging.error(f"[MIDJOURNEY_WEBAPP] Ошибка парсинга данных от {user_id}: {e}")
        await message.answer(
            "❌ Не удалось прочитать данные из окна настроек. Попробуйте открыть снова.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    if payload.get("kind") != "midjourney_settings":
        logging.warning(f"[MIDJOURNEY_WEBAPP] Неверный тип данных: {payload.get('kind')}")
        return

    # Получаем текущее состояние FSM
    data = await state.get_data()

    # Получаем slug модели из payload с fallback на состояние и дефолт
    model_slug = payload.get("modelSlug") or data.get("model_slug") or data.get("selected_model") or "midjourney-v6"
    logging.info(f"[MIDJOURNEY_WEBAPP] Model slug: {model_slug} (source: {'payload' if payload.get('modelSlug') else 'state/default'})")

    # Проверяем, что не пытаемся использовать не-midjourney провайдера
    if data and data.get("model_provider") not in {None, "midjourney"}:
        logging.warning(f"[MIDJOURNEY_WEBAPP] Неверный провайдер: {data.get('model_provider')}")
        await message.answer(
            "⚠️ WebApp настройки доступны только для моделей Midjourney.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    # Загружаем модель по slug
    try:
        logging.info(f"[MIDJOURNEY_WEBAPP] Загружаем модель по slug: {model_slug}")
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
        logging.info(f"[MIDJOURNEY_WEBAPP] Модель загружена: {model.name} (ID: {model.id})")
    except AIModel.DoesNotExist:
        logging.error(f"[MIDJOURNEY_WEBAPP] Модель не найдена: {model_slug}")
        await message.answer(
            f"⚠️ Модель {model_slug} недоступна. Выберите её заново из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    # Обновляем FSM данными модели
    from botapp.business.pricing import get_base_price_tokens
    cost = await sync_to_async(get_base_price_tokens)(model)
    max_images_supported = getattr(model, "max_input_images", 0) or 0
    if max_images_supported <= 0:
        max_images_supported = 4
    await state.update_data(
        model_id=model.id,
        model_slug=model.slug,
        selected_model=model.name,
        model_name=model.name,  # Добавляем для совместимости
        model_provider=model.provider,
        model_price=cost,
        max_images=max_images_supported,
    )
    logging.info(f"[MIDJOURNEY_WEBAPP] FSM обновлен для модели {model.name}, цена: {cost}")

    # Проверяем промт
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        logging.warning(f"[MIDJOURNEY_WEBAPP] Промт отсутствует от {user_id}")
        await message.answer("Введите промт в окне настроек и отправьте ещё раз.", reply_markup=get_cancel_keyboard())
        return

    logging.info(f"[MIDJOURNEY_WEBAPP] Промт: {prompt[:100]}...")

    # Проверяем баланс пользователя
    try:
        user = await sync_to_async(TgUser.objects.get)(chat_id=user_id)
        balance_service = BalanceService()
        await sync_to_async(balance_service.check_balance)(user, cost)
        logging.info(f"[MIDJOURNEY_WEBAPP] Баланс проверен: пользователь {user_id}, стоимость {cost}")
    except InsufficientBalanceError as e:
        logging.warning(f"[MIDJOURNEY_WEBAPP] Недостаточно средств: {user_id}, нужно {cost}")
        await message.answer(
            f"❌ Недостаточно токенов.\n"
            f"Необходимо: ⚡{cost:.2f}\n"
            f"Ваш баланс: ⚡{e.current_balance:.2f}\n\n"
            f"Пополните баланс и попробуйте снова.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return
    except Exception as e:
        logging.error(f"[MIDJOURNEY_WEBAPP] Ошибка проверки баланса: {e}")
        await message.answer(
            "❌ Произошла ошибка при проверке баланса. Попробуйте позже.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    task_type = payload.get("taskType") or "mj_txt2img"
    image_mode = "text" if task_type == "mj_txt2img" else "edit"

    logging.info(f"[MIDJOURNEY_WEBAPP] Task type: {task_type}, Image mode: {image_mode}")

    def normalize_int(value, default, min_v, max_v, step=None):
        try:
            num = int(float(value))
        except (TypeError, ValueError):
            num = default
        num = max(min_v, min(max_v, num))
        if step and step > 0:
            num = int(round(num / step) * step)
        return num

    midjourney_params = {
        "speed": payload.get("speed") or "fast",
        "aspectRatio": payload.get("aspectRatio") or "1:1",
        "version": str(payload.get("version") or "7"),
        "stylization": normalize_int(payload.get("stylization"), 200, 0, 1000, 10),
        "weirdness": normalize_int(payload.get("weirdness"), 0, 0, 3000, 50),
        "variety": normalize_int(payload.get("variety"), 10, 0, 100, 5),
    }

    logging.info(f"[MIDJOURNEY_WEBAPP] Параметры MJ: {midjourney_params}")

    inline_images: List[Dict[str, Any]] = []
    image_data = payload.get("imageData")
    image_mime = payload.get("imageMime") or "image/png"
    image_name = payload.get("imageName") or "image.png"

    if task_type == "mj_img2img":
        if image_data:
            try:
                raw = base64.b64decode(image_data)
                inline_images.append({"content": raw, "mime": image_mime, "name": image_name})
                logging.info(f"[MIDJOURNEY_WEBAPP] Изображение декодировано: {len(raw)} байт")
            except Exception as e:
                logging.error(f"[MIDJOURNEY_WEBAPP] Ошибка декодирования изображения: {e}")
                await message.answer("Не удалось прочитать изображение из WebApp. Загрузите файл ещё раз.", reply_markup=get_cancel_keyboard())
                return
        else:
            logging.warning(f"[MIDJOURNEY_WEBAPP] Изображение отсутствует для img2img")
            await message.answer("Для режима «Изображение → Изображение» нужно загрузить картинку в WebApp.", reply_markup=get_cancel_keyboard())
            return

    # Обновляем состояние всеми необходимыми данными
    await state.update_data(
        image_mode=image_mode,
        remix_images=[],
        edit_base_id=None,
        pending_caption=prompt,
        midjourney_params=midjourney_params,
        midjourney_inline_images=inline_images,
    )

    logging.info(f"[MIDJOURNEY_WEBAPP] FSM обновлен, готов к запуску генерации")

    if image_mode == "text":
        logging.info(f"[MIDJOURNEY_WEBAPP] Запуск text2image генерации для {user_id}")
        try:
            await _start_generation(message, state, prompt)
            logging.info(f"[MIDJOURNEY_WEBAPP] Генерация успешно запущена для {user_id}")
        except Exception as e:
            logging.error(f"[MIDJOURNEY_WEBAPP] Ошибка запуска генерации: {e}", exc_info=True)
            await message.answer(
                "❌ Произошла ошибка при запуске генерации. Попробуйте позже.",
                reply_markup=get_main_menu_inline_keyboard()
            )
            await state.clear()
        return

    # image_mode == edit (image->image)
    logging.info(f"[MIDJOURNEY_WEBAPP] Режим img2img, ожидаем загрузку изображения")
    await message.answer(
        "🖼 Отправьте изображение, я применю настройки и промт из окна Midjourney.",
        reply_markup=get_cancel_keyboard(),
    )
    await state.set_state(BotStates.image_wait_prompt)
    logging.info(f"[MIDJOURNEY_WEBAPP] FSM обновлен, готов к запуску генерации")

    if image_mode == "text":
        logging.info(f"[MIDJOURNEY_WEBAPP] Запуск text2image генерации для {user_id}")
        try:
            await _start_generation(message, state, prompt)
            logging.info(f"[MIDJOURNEY_WEBAPP] Генерация успешно запущена для {user_id}")
        except Exception as e:
            logging.error(f"[MIDJOURNEY_WEBAPP] Ошибка запуска генерации: {e}", exc_info=True)
            await message.answer(
                "❌ Произошла ошибка при запуске генерации. Попробуйте позже.",
                reply_markup=get_main_menu_inline_keyboard()
            )
            await state.clear()
        return

    # image_mode == edit (image->image)
    logging.info(f"[MIDJOURNEY_WEBAPP] Режим img2img, ожидаем загрузку изображения")
    await message.answer(
        "🖼 Отправьте изображение, я применю настройки и промт из окна Midjourney.",
        reply_markup=get_cancel_keyboard(),
    )
    await state.set_state(BotStates.image_wait_prompt)


@router.message(
    StateFilter("*"),
    F.web_app_data.data.contains("gpt_image_settings"),
)
async def handle_gpt_image_webapp_data(message: Message, state: FSMContext):
    """
    Принимаем данные из WebApp настроек GPT Image и запускаем генерацию.
    """
    user_id = message.from_user.id
    logger.info(f"[GPT_IMAGE_WEBAPP] Получены данные от пользователя {user_id}")

    try:
        payload = json.loads(message.web_app_data.data or "{}")
        logger.info(f"[GPT_IMAGE_WEBAPP] Payload: {json.dumps(payload, ensure_ascii=False)[:500]}")
    except Exception as exc:
        logger.error(f"[GPT_IMAGE_WEBAPP] Ошибка парсинга: {exc}")
        await message.answer(
            "❌ Не удалось прочитать данные из окна настроек. Попробуйте открыть снова.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    if payload.get("kind") != "gpt_image_settings":
        logger.warning(f"[GPT_IMAGE_WEBAPP] Неверный тип данных: {payload.get('kind')}")
        return

    data = await state.get_data()
    model_slug = (
        payload.get("modelSlug")
        or data.get("model_slug")
        or data.get("selected_model")
        or "gpt-image-1"
    )

    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        await message.answer(
            f"⚠️ Модель {model_slug} недоступна. Выберите её заново из списка моделей.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    if model.provider != "openai_image":
        await message.answer(
            "⚠️ Этот WebApp работает только с моделью GPT Image.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    cost = await sync_to_async(get_base_price_tokens)(model)
    max_images_supported = getattr(model, "max_input_images", 0) or 4
    await state.update_data(
        model_id=model.id,
        model_slug=model.slug,
        selected_model=model.slug,
        model_name=model.display_name,
        model_provider=model.provider,
        model_price=cost,
        max_images=max_images_supported,
        supports_images=model.supports_image_input,
    )

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        await message.answer(
            "Введите промт в окне настроек и отправьте ещё раз.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    # Проверка баланса
    try:
        user = await sync_to_async(TgUser.objects.get)(chat_id=user_id)
        balance_service = BalanceService()
        await sync_to_async(balance_service.check_balance)(user, cost)
    except InsufficientBalanceError as exc:
        await message.answer(
            f"❌ Недостаточно токенов.\n"
            f"Необходимо: ⚡{cost:.2f}\n"
            f"Ваш баланс: ⚡{exc.current_balance:.2f}\n\n"
            f"Пополните баланс и попробуйте снова.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return
    except Exception as exc:
        logger.error(f"[GPT_IMAGE_WEBAPP] Ошибка проверки баланса: {exc}")
        await message.answer(
            "❌ Произошла ошибка при проверке баланса. Попробуйте позже.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()
        return

    task_type = payload.get("taskType") or "gpt_txt2img"
    mode = "text" if task_type == "gpt_txt2img" else "edit"

    def normalize_size(value: Any) -> str:
        allowed = {
            "512x512",
            "768x1024",
            "1024x768",
            "1024x1024",
            "1024x1536",
            "1536x1024",
            "auto",
        }
        text_value = str(value or "1024x1024").lower()
        return text_value if text_value in allowed else "1024x1024"

    def normalize_quality(value: Any) -> str:
        allowed = {"low", "medium", "high", "auto"}
        text_value = str(value or "auto").lower()
        return text_value if text_value in allowed else "auto"

    raw_params = payload.get("params") or {}
    gpt_params = {
        "size": normalize_size(raw_params.get("size")),
        "quality": normalize_quality(raw_params.get("quality")),
    }

    inline_images: List[Dict[str, Any]] = []
    for item in payload.get("images") or []:
        base = item.get("data")
        if not base:
            continue
        try:
            raw_bytes = base64.b64decode(base)
        except Exception as exc:
            logger.error(f"[GPT_IMAGE_WEBAPP] Ошибка декодирования изображения: {exc}")
            await message.answer(
                "Не удалось прочитать одно из изображений. Загрузите файл снова.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        mime = item.get("mime") or "image/png"
        name = item.get("name") or "image.png"
        inline_images.append({"content": raw_bytes, "mime": mime, "name": name})

    if mode == "edit" and not inline_images:
        await message.answer(
            "Для режима «Изображение → Изображение» нужно загрузить хотя бы одну картинку в WebApp.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    if inline_images and len(inline_images) > max_images_supported:
        inline_images = inline_images[:max_images_supported]

    await state.update_data(
        image_mode=mode,
        remix_images=[],
        edit_base_id=None,
        pending_caption=prompt,
        midjourney_inline_images=inline_images,
        midjourney_params=gpt_params,
        generation_params=gpt_params,
    )

    try:
        await _start_generation(message, state, prompt)
    except Exception as exc:
        logger.error(f"[GPT_IMAGE_WEBAPP] Ошибка запуска генерации: {exc}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при запуске генерации. Попробуйте позже.",
            reply_markup=get_main_menu_inline_keyboard(),
        )
        await state.clear()



async def _start_generation(message: Message, state: FSMContext, prompt: str):
    """
    Internal helper to start generation process.
    Used by both text prompt handler and auto-start from caption.
    """
    user_id = message.from_user.id
    logging.info(f"[_START_GENERATION] Начало генерации для пользователя {user_id}, промт: {prompt[:100]}...")

    data = await state.get_data()
    mode = data.get("image_mode") or "text"
    remix_images = data.get("remix_images") or []
    edit_base_id = data.get("edit_base_id")
    inline_images = data.get("midjourney_inline_images") or []

    logging.info(f"[_START_GENERATION] Режим: {mode}, remix_images: {len(remix_images)}, edit_base_id: {edit_base_id}, inline_images: {len(inline_images)}")

    # Проверяем длину промта
    try:
        model = await sync_to_async(AIModel.objects.get)(id=data['model_id'])
    except (AIModel.DoesNotExist, KeyError):
        await message.answer("Ошибка: модель не найдена. Начните заново.")
        await state.clear()
        return

    if len(prompt) > model.max_prompt_length:
        await message.answer(
            f"❌ Промт слишком длинный!\n"
            f"Максимальная длина: {model.max_prompt_length} символов\n"
            f"Ваш промт: {len(prompt)} символов",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Получаем пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)

    # Создаем запрос на генерацию через сервис
    generation_type = 'text2image'
    input_entries: List[Dict[str, Any]] = []
    if mode == "edit":
        if inline_images:
            generation_type = 'image2image'
            input_entries = inline_images
        elif not edit_base_id:
            await message.answer(
                "Отправьте изображение для редактирования, затем текстовый промт.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        else:
            generation_type = 'image2image'
            input_entries = [
                {"telegram_file_id": edit_base_id},
            ]
    elif mode == "remix":
        min_required = 2
        # Исправлено: корректная обработка max_images (0 не должен превращаться в min_required)
        max_images = data.get("max_images", min_required)
        if max_images is None or max_images <= 0:
            max_images = min_required
        max_allowed = max(min_required, max_images)
        # Детальное логирование для диагностики
        print(f"[START_GENERATION] Remix mode: remix_images={len(remix_images)}, "
              f"max_allowed={max_allowed}, model_id={data.get('model_id')}, "
              f"max_images={max_images}", flush=True)
        print(f"[START_GENERATION] remix_images file_ids: {remix_images}", flush=True)
        logger.info(
            f"[HANDLER] Remix mode: remix_images={len(remix_images)}, "
            f"max_allowed={max_allowed}, model_id={data.get('model_id')}, "
            f"max_images={max_images}"
        )
        logger.info(f"[HANDLER DEBUG] remix_images file_ids: {remix_images}")
        if len(remix_images) < min_required:
            await message.answer(
                f"Для режима «Ремикс» нужно минимум {min_required} изображений. Загрузите ещё и повторите попытку.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        generation_type = 'image2image'
        input_entries = [
            {"telegram_file_id": file_id, "type": "subject"}
            for file_id in remix_images[:max_allowed]
        ]
        logger.info(f"[HANDLER] Created input_entries with {len(input_entries)} images from {len(remix_images)} available")
    else:
        input_entries = []

    try:
        extra_params = data.get("midjourney_params") or {}
        generation_params = {"image_mode": mode}
        generation_params.update(extra_params)

        logging.info(f"[_START_GENERATION] Создание запроса: generation_type={generation_type}, input_entries={len(input_entries)}, params={generation_params}")

        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,  # По умолчанию 1 изображение
            generation_type=generation_type,
            input_images=input_entries,
            generation_params=generation_params,
        )

        logging.info(f"[_START_GENERATION] Запрос создан: request_id={gen_request.id}")

        # Отправляем информационное сообщение с деталями
        await message.answer(
            f"🎨 **Генерация началась!**\n\n"
            f"Модель: {data['model_name']}\n"
            f"Промт: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n\n"
            f"⏳ Обычно это занимает 10-30 секунд...\n"
            f"Я отправлю вам результат, как только он будет готов!",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline_keyboard()
        )

        # Запускаем задачу генерации
        logging.info(f"[_START_GENERATION] Запуск Celery задачи для request_id={gen_request.id}")
        task_result = generate_image_task.delay(gen_request.id)
        logging.info(f"[_START_GENERATION] Celery задача запущена: task_id={task_result.id}")

        # Очищаем состояние
        await state.clear()
        logging.info(f"[_START_GENERATION] Состояние очищено для пользователя {user_id}")

    except InsufficientBalanceError as e:
        await message.answer(
            f"❌ {str(e)}",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()

    except Exception as e:
        await message.answer(
            f"❌ Произошла ошибка: {str(e)}",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="image_generation._start_generation",
            chat_id=message.chat.id,
            payload={
                "mode": mode,
                "model_id": data.get("model_id"),
                "prompt_length": len(prompt) if prompt else 0,
                "has_remix_images": bool(remix_images),
                "has_edit_base": bool(edit_base_id),
            },
            exc=e,
        )
        await state.clear()


@router.message(BotStates.image_wait_prompt, F.text)
async def receive_image_prompt(message: Message, state: FSMContext):
    """
    Получаем текстовый промт для генерации
    """
    await _start_generation(message, state, message.text)


@router.message(BotStates.image_wait_prompt, F.photo)
async def receive_image_for_prompt(message: Message, state: FSMContext):
    """
    Получаем изображения или маску в зависимости от выбранного режима.
    Поддерживает отправку альбомов (media_group) и авто-старт при наличии подписи (caption).
    """
    data = await state.get_data()
    mode = data.get("image_mode") or "text"
    pending_caption = data.get("pending_caption")

    if not data.get('supports_images'):
        await message.answer(
            "❌ Эта модель не поддерживает входные изображения.\n"
            "Отправьте текстовый промт или выберите другую модель.",
            reply_markup=get_cancel_keyboard()
        )
        return

    if mode == "text":
        await message.answer(
            "Вы выбрали режим «Создать из текста». Отправьте промт без изображений или выберите другой режим.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    photo = message.photo[-1]
    max_images = max(1, data.get('max_images', 4))

    if mode == "edit":
        await state.update_data(edit_base_id=photo.file_id)
        # Если есть подпись, используем её как промт сразу
        if message.caption:
            await _start_generation(message, state, message.caption)
        elif pending_caption:
            # Если вдруг был сохранен промт ранее (маловероятно для edit, но для порядка)
            await _start_generation(message, state, pending_caption)
        else:
            await message.answer(
                "🖼️ Изображение получено. Теперь отправьте текстовый промт.",
                reply_markup=get_cancel_keyboard(),
            )
        return

    # Режим remix
    remix_images = data.get('remix_images', [])
    print(f"[DEBUG] Handler started, mode={mode}, existing_remix_images={len(remix_images)}", flush=True)
    chat_id = message.chat.id

    # Логирование входящего изображения
    print(f"[REMIX INCOMING] New photo received: file_id={photo.file_id[:20]}..., "
          f"media_group_id={message.media_group_id}, caption={bool(message.caption)}, "
          f"current_remix_count={len(remix_images)}", flush=True)
    logger.info(f"[REMIX INCOMING] New photo received: file_id={photo.file_id[:20]}..., "
                f"media_group_id={message.media_group_id}, caption={bool(message.caption)}, "
                f"current_remix_count={len(remix_images)}")

    # Если есть подпись в текущем сообщении, запоминаем её в локальную переменную
    # (но сохранять в стейт будем только в блоке обработки, чтобы избежать гонки)
    current_caption = message.caption

    # Универсальная буферизация для режима Remix
    # Используем chat_id как ключ группировки, чтобы ловить и альбомы, и быстрые одиночные отправки
    print(f"[DEBUG] Starting Redis buffer operations for chat_id={chat_id}", flush=True)
    redis = state.storage.redis
    key_images = f"remix_buffer_imgs:{chat_id}"
    key_caption = f"remix_buffer_cap:{chat_id}"

    # Сохраняем file_id в Redis-список
    await redis.rpush(key_images, photo.file_id)
    await redis.expire(key_images, 60)
    logger.info(f"[REMIX_BUFFER] Added photo to Redis buffer: chat_id={chat_id}, file_id={photo.file_id[:20]}..., media_group_id={message.media_group_id}")

    # Если пришла подпись - сохраняем её в Redis (перезаписываем, считаем актуальной последнюю/любую)
    if current_caption:
        await redis.set(key_caption, current_caption, ex=60)
        logger.info(f"[REMIX_BUFFER] Saved caption to Redis: chat_id={chat_id}, caption_len={len(current_caption)}")

    # Оптимизированная задержка:
    # - Альбом (с подписью или без): 2.0 c — гарантированно соберёт 3+ фото, отправленных одним батчем
    # - Одиночные фото: 0.5 c
    if message.media_group_id:
        delay = 2.0
    else:
        # Одиночное фото
        delay = 0.5
    logger.info(
        f"[REMIX_BUFFER] Delay before flush: delay={delay}, media_group={bool(message.media_group_id)}, "
        f"has_caption={bool(current_caption)}"
    )
    await asyncio.sleep(delay)

    # Используем Lua-скрипт для атомарного получения и удаления списка
    lua_script = """
    local list = redis.call('LRANGE', KEYS[1], 0, -1)
    if #list > 0 then
        redis.call('DEL', KEYS[1])
    end
    return list
    """
    
    try:
        stored_images = await redis.eval(lua_script, 1, key_images)
    except Exception as e:
        logger.error(f"Redis eval error: {e}")
        stored_images = []

    if not stored_images:
        # Значит другой обработчик (воркер) уже забрал данные и обрабатывает их
        logger.info(f"[REMIX_BUFFER] No images in buffer (already processed by another worker): chat_id={chat_id}")
        return

    # Этот воркер - "победитель", он обрабатывает всю пачку
    logger.info(f"[REMIX_BUFFER] Processing buffer: chat_id={chat_id}, stored_images_count={len(stored_images)}")

    # 1. Забираем caption из Redis (если был)
    stored_caption = await redis.get(key_caption)
    if stored_caption:
        stored_caption = stored_caption.decode('utf-8')
        await redis.delete(key_caption)
        # Обновляем pending_caption, если нашли новый
        pending_caption = stored_caption
        logger.info(f"[REMIX_BUFFER] Got caption from Redis: caption_len={len(stored_caption)}")

    # 2. Декодируем image ids
    new_images = [img_id.decode('utf-8') if isinstance(img_id, bytes) else img_id for img_id in stored_images]
    logger.info(f"[REMIX_BUFFER] Decoded {len(new_images)} images from Redis")
    logger.info(f"[REMIX_BUFFER DEBUG] new_images from Redis: {new_images}")

    # 3. Получаем АКТУАЛЬНЫЙ стейт заново, так как за время sleep он мог измениться (маловероятно при такой схеме, но надежнее)
    # Но так как мы единственные кто пишет в remix_images через этот буфер, можно брать из data,
    # но лучше перестраховаться, если вдруг были какие-то другие операции.
    # data = await state.get_data() -> уже есть.
    # remix_images = data.get('remix_images', []) -> уже есть.
    # Просто добавляем.

    logger.info(f"[REMIX_BUFFER DEBUG] remix_images before extend: {remix_images}")
    remix_images.extend(new_images)
    remix_images = list(dict.fromkeys(remix_images)) # Уник
    logger.info(f"[REMIX_BUFFER] Updated remix_images list: count={len(remix_images)}, has_caption={bool(pending_caption)}")
    logger.info(f"[REMIX_BUFFER DEBUG] remix_images after unique: {remix_images}")

    # 4. Сохраняем обновленный список и pending_caption в стейт
    await state.update_data(remix_images=remix_images, pending_caption=pending_caption)
    logger.info(f"[REMIX_BUFFER] Saved to FSM state: remix_images_count={len(remix_images)}")
    
    # 5. Проверяем условия авто-старта
    # Для ремикса всегда нужно минимум 2 изображения
    min_needed = 2

    print(f"[REMIX AUTO-START CHECK] remix_images={len(remix_images)}, "
          f"min_needed={min_needed}, has_caption={bool(pending_caption)}", flush=True)
    logger.info(f"[REMIX AUTO-START CHECK] remix_images={len(remix_images)}, "
                f"min_needed={min_needed}, has_caption={bool(pending_caption)}")

    # После сбора через Redis буфер проверяем автостарт
    # Важно: на этом этапе мы УЖЕ собрали все изображения из буфера (после задержки)
    # Поэтому можем запускать генерацию для альбомов с подписью
    if len(remix_images) >= min_needed and pending_caption:
        # Запускаем генерацию: у нас есть достаточно изображений и текст
        print(f"[REMIX AUTO-START] Triggering generation with {len(remix_images)} images after buffer collection", flush=True)
        logger.info(f"[REMIX AUTO-START] Triggering generation with {len(remix_images)} images after buffer collection")
        await _start_generation(message, state, pending_caption)
        return

    # 6. Если автостарт не сработал - отправляем статус (ОДИН РАЗ на пачку)
    # Показываем статус только если НЕТ промта или не хватает изображений
    # НЕ показываем промежуточные статусы для альбомов с caption (они обрабатываются после задержки)
    msg_text = ""
    if len(remix_images) >= max_images:
        msg_text = f"✅ Загружено {len(remix_images)} изображений (максимум). Отправьте текстовый промт."
    elif len(remix_images) < min_needed:
        # Для альбомов с caption не показываем "Загружено 1" - ждём сбора всех фото
        if not (message.media_group_id and current_caption):
            msg_text = f"✅ Загружено {len(remix_images)} изображений. Нужно минимум {min_needed}. Загрузите ещё."
    else:
        # 2 или больше изображений, но нет промта
        msg_text = f"✅ Загружено {len(remix_images)} изображений. Можно добавить ещё или отправить промт."

    if msg_text:
        await message.answer(msg_text, reply_markup=get_cancel_keyboard())
    return


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
        "Главное меню:",
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )


@router.callback_query(StateFilter("*"), F.data.startswith("image_mode:"))
async def select_image_mode(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора режима генерации изображений."""
    await callback.answer()
    mode = callback.data.split(":", maxsplit=1)[1]

    data = await state.get_data()
    # Если данных нет (стерся стейт), но кнопку нажали - пытаемся восстановить или просим заново
    if not data:
         await callback.message.answer(
            "⚠️ Сессия устарела. Пожалуйста, выберите модель заново.",
            reply_markup=get_main_menu_inline_keyboard()
        )
         return
         
    supports_images = data.get("supports_images", False)
    max_images = data.get("max_images", 0)

    if mode in {"edit", "remix"} and (not supports_images or max_images <= 0):
        await callback.message.answer(
            "❌ Этот режим доступен только для моделей, поддерживающих загрузку изображений. Выберите «Создать из текста».",
            reply_markup=get_image_mode_keyboard(),
        )
        return

    if mode == "remix" and max_images < 2:
        await callback.message.answer(
            "❌ Для режима «Ремикс» требуется поддержка минимум 2 изображений. Выберите другой режим.",
            reply_markup=get_image_mode_keyboard(),
        )
        return

    await state.update_data(
        image_mode=mode,
        remix_images=[],
        edit_base_id=None,
    )

    if mode == "text":
        await callback.message.answer(
            "✍️ Отправьте текстовый промт для генерации изображения.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return

    if mode == "edit":
        await callback.message.answer(
            "🪄 Режим редактирования.\nОтправьте изображение, затем текстовый промт. Маска не требуется.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return

    if mode == "remix":
        await callback.message.answer(
            f"🎭 Режим ремикса.\nЗагрузите от 2 до {max_images} изображений (одним за другим), затем отправьте текстовый промт.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return
