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
from botapp.models import TgUser, AIModel
from botapp.business.generation import GenerationService
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.tasks import generate_video_task
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
