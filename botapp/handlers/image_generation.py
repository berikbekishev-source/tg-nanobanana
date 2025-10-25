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
    get_generation_complete_message
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

    # Устанавливаем состояние ожидания промта
    await state.set_state(BotStates.image_wait_prompt)

    # Сохраняем данные для генерации
    await state.update_data(
        model_slug=model_slug,
        model_id=model.id,
        model_name=model.display_name,
        model_price=float(model.price),
        max_images=model.max_input_images,
        supports_images=model.supports_image_input
    )


@router.message(BotStates.image_wait_prompt, F.text)
async def receive_image_prompt(message: Message, state: FSMContext):
    """
    Получаем текстовый промт для генерации
    """
    data = await state.get_data()
    prompt = message.text

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
    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,  # По умолчанию 1 изображение
            generation_type='text2image'
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
async def receive_image_for_remix(message: Message, state: FSMContext):
    """
    Получаем изображения для режима Remix
    """
    data = await state.get_data()

    # Проверяем, поддерживает ли модель изображения
    if not data.get('supports_images'):
        await message.answer(
            "❌ Эта модель не поддерживает входные изображения.\n"
            "Отправьте текстовое описание.",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Получаем список уже загруженных изображений
    images = data.get('input_images', [])

    # Получаем file_id самого большого размера фото
    photo = message.photo[-1]
    images.append(photo.file_id)

    # Проверяем лимит изображений
    max_images = data.get('max_images', 4)
    if len(images) > max_images:
        await message.answer(
            f"❌ Максимальное количество изображений: {max_images}\n"
            f"Вы загрузили: {len(images)}",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Сохраняем изображения в состоянии
    await state.update_data(input_images=images)

    if len(images) < max_images:
        await message.answer(
            f"✅ Изображение {len(images)} из {max_images} загружено.\n\n"
            f"Можете загрузить еще {max_images - len(images)} изображений или отправить текстовое описание для начала генерации.",
            reply_markup=get_cancel_keyboard()
        )
    else:
        await message.answer(
            f"✅ Все {max_images} изображения загружены!\n\n"
            f"Теперь отправьте текстовое описание того, что нужно сделать с изображениями.",
            reply_markup=get_cancel_keyboard()
        )

    # Переходим в состояние ожидания промта для Remix
    await state.set_state(BotStates.image_wait_images)


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