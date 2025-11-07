"""
Обработчики генерации изображений
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from typing import List

from botapp.states import BotStates
from botapp.keyboards import (
    get_image_models_keyboard,
    get_back_to_menu_keyboard,
    get_model_info_message,
    get_cancel_keyboard,
    get_main_menu_inline_keyboard,
    get_generation_start_message,
    get_generation_complete_message,
    get_image_mode_keyboard,
)
from botapp.models import TgUser, AIModel
from botapp.business.generation import GenerationService
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.tasks import generate_image_task
from asgiref.sync import sync_to_async
import uuid

router = Router()


@router.message(F.text == "🎨 Создать изображение")
async def create_image_start(message: Message, state: FSMContext):
    """
    Шаг 1: Выбор модели генерации изображений
    """
    # Получаем активные модели для изображений
    models = await sync_to_async(list)(
        AIModel.objects.filter(type='image', is_active=True).order_by('order')
    )

    if not models:
        await message.answer(
            "😔 К сожалению, сейчас нет доступных моделей для генерации изображений.\n"
            "Попробуйте позже.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    # Отправляем список моделей с inline кнопкой меню
    await message.answer(
        "🎨 **Выберите модель для генерации изображений:**",
        reply_markup=get_image_models_keyboard(models),
        parse_mode="Markdown"
    )

    # Устанавливаем состояние выбора модели
    await state.set_state(BotStates.image_select_model)


@router.callback_query(F.data.startswith("img_model:"))
async def select_image_model(callback: CallbackQuery, state: FSMContext):
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

    # Отправляем информацию о модели (Шаг 2 по ТЗ)
    info_message = get_model_info_message(model)
    await callback.message.answer(
        info_message,
        parse_mode="Markdown"
    )

    # Сохраняем данные для генерации
    await state.update_data(
        model_slug=model_slug,
        model_id=model.id,
        model_name=model.display_name,
        model_price=float(model.price),
        max_images=model.max_input_images,
        supports_images=model.supports_image_input,
        input_images=[],
        image_mode=None,
    )

    # Предлагаем выбрать режим генерации
    await state.set_state(BotStates.image_select_mode)
    await callback.message.answer(
        "Выберите режим генерации:\n"
        "• Создать из текста — классический text2image\n"
        "• Отредактировать — одно изображение + промт\n"
        "• Ремикс — от 2 до 4 изображений + промт",
        reply_markup=get_image_mode_keyboard(),
    )


@router.message(BotStates.image_wait_prompt, F.text)
async def receive_image_prompt(message: Message, state: FSMContext):
    """
    Получаем текстовый промт для генерации
    """
    data = await state.get_data()
    prompt = message.text
    mode = data.get("image_mode") or "text"
    input_images = data.get("input_images") or []

    # Проверяем длину промта
    model = await sync_to_async(AIModel.objects.get)(id=data['model_id'])
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
    if mode == "edit":
        if len(input_images) < 1:
            await message.answer(
                "Отправьте изображение, которое нужно отредактировать, затем текстовый промт.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        generation_type = 'image2image'
    elif mode == "remix":
        min_images = max(2, min(data.get("max_images", 4), 4))
        if len(input_images) < min_images:
            await message.answer(
                f"Для режима «Ремикс» нужно минимум {min_images} изображений. Загрузите ещё и повторите попытку.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        generation_type = 'image2image'
    else:
        input_images = []

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,  # По умолчанию 1 изображение
            generation_type=generation_type,
            input_images=input_images,
        )

        # Отправляем системное сообщение о начале генерации
        await message.answer(
            get_generation_start_message(),
            parse_mode="Markdown"
        )

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
        generate_image_task.delay(gen_request.id)

        # Очищаем состояние
        await state.clear()

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
        await state.clear()


@router.message(BotStates.image_wait_prompt, F.photo)
async def receive_image_for_prompt(message: Message, state: FSMContext):
    """
    Получаем изображения для режимов edit/remix.
    """
    data = await state.get_data()
    mode = data.get("image_mode") or "text"

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

    images = data.get('input_images', [])
    max_images = max(1, data.get('max_images', 4))
    photo = message.photo[-1]

    if mode == "edit":
        images = [photo.file_id]
        await state.update_data(input_images=images)
        await message.answer(
            "🖼️ Изображение получено! Теперь отправьте текстовый промт для редактирования.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    # режим remix
    if len(images) >= max_images:
        await message.answer(
            f"❌ Уже загружено максимальное количество изображений ({max_images}). Теперь отправьте текстовый промт.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    images.append(photo.file_id)
    await state.update_data(input_images=images)

    min_needed = max(2, min(max_images, 4))
    if len(images) < min_needed:
        await message.answer(
            f"✅ Изображение {len(images)} загружено. Нужно минимум {min_needed} изображений."
            f" Загрузите ещё или отмените операцию.",
            reply_markup=get_cancel_keyboard(),
        )
    elif len(images) < max_images:
        await message.answer(
            f"✅ Изображение {len(images)} загружено. Можно добавить ещё {max_images - len(images)} "
            "или отправить текстовый промт.",
            reply_markup=get_cancel_keyboard(),
        )
    else:
        await message.answer(
            "✅ Достаточно изображений! Отправьте текстовый промт для запуска ремикса.",
            reply_markup=get_cancel_keyboard(),
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
@router.callback_query(BotStates.image_select_mode, F.data.startswith("image_mode:"))
async def select_image_mode(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора режима генерации изображений."""
    await callback.answer()
    mode = callback.data.split(":", maxsplit=1)[1]

    data = await state.get_data()
    supports_images = data.get("supports_images", False)
    max_images = data.get("max_images", 0)

    if mode in {"edit", "remix"} and (not supports_images or max_images <= 0):
        await callback.message.answer(
            "❌ Эта модель не поддерживает загрузку изображений. Выберите режим «Создать из текста».",
            reply_markup=get_image_mode_keyboard(),
        )
        return

    if mode == "remix" and max_images < 2:
        await callback.message.answer(
            "❌ Для режима «Ремикс» требуется поддержка минимум 2 изображений. Выберите другой режим.",
            reply_markup=get_image_mode_keyboard(),
        )
        return

    await state.update_data(image_mode=mode, input_images=[])

    if mode == "text":
        await callback.message.answer(
            "✍️ Отправьте текстовый промт для генерации изображения.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return

    if mode == "edit":
        await callback.message.answer(
            "🪄 Отправьте изображение, которое нужно отредактировать, затем пришлите текстовый промт.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return

    if mode == "remix":
        await callback.message.answer(
            f"🎭 Отправьте от 2 до {max_images} изображений. После этого пришлите текстовый промт.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return
