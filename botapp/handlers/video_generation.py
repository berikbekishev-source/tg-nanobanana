"""
Обработчики генерации видео
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from botapp.states import BotStates
from botapp.keyboards import (
    get_video_models_keyboard,
    get_video_format_keyboard,
    get_cancel_keyboard,
    get_main_menu_inline_keyboard,
    get_generation_start_message
)
from botapp.models import TgUser, AIModel, GenRequest
from botapp.business.generation import GenerationService
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.tasks import generate_video_task, extend_video_task
from asgiref.sync import sync_to_async

router = Router()


@router.message(F.text == "🎬 Создать видео")
async def create_video_start(message: Message, state: FSMContext):
    """
    Шаг 1: Выбор модели генерации видео
    """
    # Получаем активные модели для видео
    models = await sync_to_async(list)(
        AIModel.objects.filter(type='video', is_active=True).order_by('order')
    )

    if not models:
        await message.answer(
            "😔 К сожалению, сейчас нет доступных моделей для генерации видео.\n"
            "Попробуйте позже.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    # Отправляем список моделей с inline кнопкой меню
    await message.answer(
        "🎬 **Выберите модель для генерации видео:**",
        reply_markup=get_video_models_keyboard(models),
        parse_mode="Markdown"
    )

    # Устанавливаем состояние выбора модели
    await state.set_state(BotStates.video_select_model)


@router.callback_query(F.data.startswith("vid_model:"))
async def select_video_model(callback: CallbackQuery, state: FSMContext):
    """
    Шаг 2: После выбора модели показываем информацию и ждем промт
    """
    await callback.answer()

    # Получаем slug модели из callback data
    model_slug = callback.data.split(":")[1]

    # Получаем модель из БД
    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        await callback.message.answer(
            "❌ Модель не найдена или недоступна.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    # Сохраняем выбранную модель в состояние
    await state.update_data(selected_model=model_slug, model_id=model.id)

    # Проверяем баланс пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=callback.from_user.id)
    balance = await sync_to_async(BalanceService.get_balance)(user)

    if balance < model.price:
        await callback.message.answer(
            f"❌ **Недостаточно токенов**\n\n"
            f"Ваш баланс: ⚡ {balance:.2f} токенов\n"
            f"Стоимость генерации: ⚡ {model.price} токенов\n\n"
            f"Необходимо пополнить баланс на ⚡ {model.price - balance:.2f} токенов",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    default_params = model.default_params or {}
    default_duration = default_params.get('duration', 8)
    default_resolution = default_params.get('resolution', '720p')
    default_aspect_ratio = default_params.get('aspect_ratio', '16:9')

    info_message = (
        f"Модель: {model.name}.\n"
        f"Стоимость: ⚡{model.price:.2f} токенов.\n"
        f"Генерация видео в качестве {default_resolution} и до {default_duration} секунд.\n"
        "Для генерации в режиме txt2video отправьте текстовый промт.\n"
        "Для генерации в режиме img2video загрузите изображение и в описании напишите текстовый промт."
    )

    await callback.message.answer(
        info_message,
        reply_markup=get_cancel_keyboard()
    )

    await callback.message.answer(
        "Выберите формат видео:",
        reply_markup=get_video_format_keyboard()
    )

    await state.set_state(BotStates.video_select_format)
    await state.update_data(
        model_slug=model_slug,
        model_id=model.id,
        model_name=model.display_name,
        supports_images=model.supports_image_input,
        default_duration=default_duration,
        default_resolution=default_resolution,
        default_aspect_ratio=default_aspect_ratio,
        generation_type='text2video'
    )


@router.message(BotStates.video_select_format)
async def wait_format_selection(message: Message, state: FSMContext):
    """Напоминаем выбрать формат, если пользователь отправил что-то раньше времени."""
    await message.answer(
        "Пожалуйста, выберите формат видео, используя кнопки ниже.",
        reply_markup=get_video_format_keyboard()
    )


@router.callback_query(BotStates.video_select_format, F.data.startswith("video_format:"))
async def set_video_format(callback: CallbackQuery, state: FSMContext):
    """Сохраняем выбранное соотношение сторон и переходим к сбору промта."""
    await callback.answer()

    ratio_raw = callback.data.split(":", maxsplit=1)[1]
    aspect_ratio = ratio_raw.replace("_", ":") if "_" in ratio_raw else ratio_raw

    data = await state.get_data()
    supports_images = data.get('supports_images', False)

    await state.update_data(
        selected_aspect_ratio=aspect_ratio,
        generation_type='text2video',
        input_image_file_id=None,
        input_image_mime_type=None
    )

    intro = [
        f"Формат выбран: {aspect_ratio}",
        "Отправьте текстовое описание для генерации видео.",
    ]
    if supports_images:
        intro.append("Либо загрузите изображение и добавьте описание, чтобы использовать режим img2video.")

    await callback.message.answer(
        "\n".join(intro),
        reply_markup=get_cancel_keyboard()
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

    # Сохраняем изображение в состоянии
    await state.update_data(
        input_image_file_id=photo.file_id,
        input_image_mime_type='image/jpeg'
    )

    # Запрашиваем текстовое описание
    await message.answer(
        "✅ Изображение загружено!\n\n"
        "Теперь отправьте текстовое описание для генерации видео на основе этого изображения.",
        reply_markup=get_cancel_keyboard()
    )

    # Переходим в состояние ожидания промта для image2video
    await state.set_state(BotStates.video_wait_prompt)
    await state.update_data(generation_type='image2video')


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
    default_resolution = data.get('default_resolution') or model.default_params.get('resolution') or '720p'
    default_aspect_ratio = data.get('default_aspect_ratio') or model.default_params.get('aspect_ratio') or '16:9'
    selected_aspect_ratio = data.get('selected_aspect_ratio') or default_aspect_ratio

    generation_params = {
        'duration': default_duration,
        'resolution': default_resolution,
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
            duration=default_duration,
            video_resolution=default_resolution,
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
        await state.clear()
        return

    await message.answer(
        get_generation_start_message(),
        reply_markup=get_main_menu_inline_keyboard()
    )

    generate_video_task.delay(gen_request.id)
    await state.clear()


@router.callback_query(F.data.startswith("extend_video:"))
async def prompt_video_extension(callback: CallbackQuery, state: FSMContext):
    """Подготовить пользователя к продлению видео."""
    await callback.answer()

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
    cost_text = f"⚡ Стоимость продления: {model.price:.2f} токенов."

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
        await state.clear()
        return

    await message.answer(
        get_generation_start_message(),
        reply_markup=get_main_menu_inline_keyboard()
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


@router.callback_query(F.data == "main_menu")
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
