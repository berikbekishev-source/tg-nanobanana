"""
Глобальные обработчики команд и кнопок меню.
Эти обработчики должны работать из ЛЮБОГО состояния.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from django.conf import settings

from botapp.states import BotStates
from botapp.keyboards import (
    get_main_menu_keyboard,
    get_back_to_menu_keyboard,
    get_balance_keyboard,
    get_prices_info
)
from botapp.models import TgUser
from botapp.business.balance import BalanceService
from asgiref.sync import sync_to_async

router = Router()

# URL для Mini App
PAYMENT_URL = getattr(settings, 'PAYMENT_MINI_APP_URL', 'https://example.com/payment')


@router.message(StateFilter("*"), F.text.in_({"🏠 Главное меню", "🏠Главное меню"}))
async def global_back_to_main_menu(message: Message, state: FSMContext):
    """
    Возврат в главное меню из любого состояния.
    Этот обработчик работает независимо от текущего состояния FSM.
    Поддерживает оба варианта написания (с пробелом и без).
    """
    await state.clear()
    await state.set_state(BotStates.main_menu)

    await message.answer(
        "Выберите нужное действие нажав на кнопку в меню 👇",
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )


@router.message(StateFilter("*"), F.text == "💰 Мой баланс (цены)")
async def global_show_balance(message: Message, state: FSMContext):
    """
    Обработчик кнопки 'Мой баланс (цены)' - работает из любого состояния.
    """
    # Получаем пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)

    # Получаем баланс пользователя
    balance = await sync_to_async(BalanceService.get_balance)(user)

    # Формируем сообщение с балансом и ценами
    balance_message = await sync_to_async(get_prices_info)(balance)

    # Отправляем сообщение с балансом + inline кнопка "Пополнить баланс"
    await message.answer(
        balance_message,
        reply_markup=get_balance_keyboard(),
        parse_mode=None
    )

    # Меняем клавиатуру на кнопку "Главное меню"
    await message.answer(
        "Выберите действие:",
        reply_markup=get_back_to_menu_keyboard()
    )

    # Устанавливаем состояние просмотра баланса
    await state.set_state(BotStates.balance_view)


@router.message(StateFilter("*"), F.text == "🎨 Создать изображение")
async def global_create_image_start(message: Message, state: FSMContext):
    """
    Обработчик кнопки 'Создать изображение' - работает из любого состояния.
    Перенаправляет к выбору модели для генерации изображений.
    """
    from botapp.models import AIModel
    from botapp.keyboards import get_image_models_keyboard, get_main_menu_inline_keyboard
    
    # Очищаем предыдущее состояние
    await state.clear()
    
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

    # Отправляем список моделей
    await message.answer(
        "🎨 Выберите модель для генерации изображений:",
        reply_markup=get_image_models_keyboard(models)
    )

    # Переводим в состояние выбора модели
    await state.set_state(BotStates.image_select_model)


@router.message(StateFilter("*"), F.text == "🎬 Создать видео")
async def global_create_video_start(message: Message, state: FSMContext):
    """
    Обработчик кнопки 'Создать видео' - работает из любого состояния.
    Перенаправляет к выбору модели для генерации видео.
    """
    from botapp.models import AIModel
    from botapp.keyboards import get_video_models_keyboard, get_main_menu_inline_keyboard
    
    # Очищаем предыдущее состояние
    await state.clear()
    
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

    # Отправляем список моделей
    await message.answer(
        "🎬 Выберите модель для генерации видео:",
        reply_markup=get_video_models_keyboard(models)
    )

    # Переводим в состояние выбора модели
    await state.set_state(BotStates.video_select_model)


@router.message(StateFilter("*"), F.text.in_({"Промт по рефференсу", "📲Промт по рефференсу"}))
async def global_prompt_by_reference_entry(message: Message, state: FSMContext):
    """
    Обработчик кнопки 'Промт по рефференсу' - работает из любого состояния.
    Автоматически выбирает первую доступную модель.
    """
    from botapp.reference_prompt import REFERENCE_PROMPT_MODELS
    from botapp.keyboards import get_cancel_keyboard
    
    await state.clear()

    if not REFERENCE_PROMPT_MODELS:
        await message.answer(
            "😔 Сейчас нет доступных моделей для создания промта по референсу.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    # Автоматически выбираем первую доступную модель
    default_model = next(iter(REFERENCE_PROMPT_MODELS.values()), None)
    if not default_model:
        await message.answer(
            "😔 Сейчас нет доступных моделей для создания промта по референсу.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(reference_prompt_model=default_model.slug)

    await message.answer(
        "🔍 Скиньте в бота ссылку на любой Reels, Shorts, TikTok или загрузите в чат видео/изображение и получите промт для генерации точно такого же видео!",
        reply_markup=get_cancel_keyboard(),
    )
    await state.set_state(BotStates.reference_prompt_wait_reference)


@router.callback_query(StateFilter("*"), F.data.startswith("img_model:"))
async def global_select_image_model(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик выбора модели для генерации изображений.
    Работает из любого состояния (переопределяет текущее состояние).
    """
    from botapp.models import AIModel
    from botapp.keyboards import (
        get_main_menu_inline_keyboard,
        get_model_info_message,
        get_image_mode_keyboard
    )
    from botapp.business.pricing import get_base_price_tokens
    
    await callback.answer()

    # Получаем slug модели из callback data
    model_slug = callback.data.split(":")[1]

    # Получаем модель из БД
    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except:
        await callback.message.answer(
            "❌ Модель не найдена или недоступна.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    # Очищаем предыдущее состояние
    await state.clear()
    
    # Сохраняем выбранную модель в состояние
    await state.update_data(selected_model=model_slug, model_id=model.id)

    # Проверяем баланс пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=callback.from_user.id)
    balance = await sync_to_async(BalanceService.get_balance)(user)
    model_cost = await sync_to_async(get_base_price_tokens)(model)

    if balance < model_cost:
        await callback.message.answer(
            f"❌ **Недостаточно токенов**\n\n"
            f"Ваш баланс: ⚡ {balance:.2f} токенов\n"
            f"Стоимость генерации: ⚡ {model_cost:.2f} токенов\n\n"
            f"Необходимо пополнить баланс на ⚡ {model_cost - balance:.2f} токенов",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    # Сохраняем данные для генерации
    await state.update_data(
        model_slug=model_slug,
        model_id=model.id,
        model_name=model.display_name,
        model_provider=model.provider,
        model_price=float(model_cost),
        max_images=model.max_input_images,
        supports_images=model.supports_image_input,
        image_mode=None,
        remix_images=[],
        edit_base_id=None,
    )

    info_message = (
        get_model_info_message(model, base_price=model_cost)
        + "\n\nРежимы:\n"
        "• Создать из текста — промт без изображений\n"
        "• Отредактировать — одно изображение + промт\n"
        "• Ремикс — 2-4 изображения + промт"
    )

    await callback.message.answer(
        info_message,
        reply_markup=get_image_mode_keyboard(),
        parse_mode="Markdown"
    )

    # Переходим к выбору режима
    await state.set_state(BotStates.image_select_mode)


@router.callback_query(StateFilter("*"), F.data.startswith("vid_model:"))
async def global_select_video_model(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик выбора модели для генерации видео.
    Работает из любого состояния (переопределяет текущее состояние).
    """
    from botapp.models import AIModel
    from botapp.keyboards import (
        get_main_menu_inline_keyboard,
        get_model_info_message,
        get_video_format_keyboard
    )
    from botapp.business.pricing import get_base_price_tokens
    
    await callback.answer()

    # Получаем slug модели из callback data
    model_slug = callback.data.split(":")[1]

    # Получаем модель из БД
    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except:
        await callback.message.answer(
            "❌ Модель не найдена или недоступна.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    # Очищаем предыдущее состояние
    await state.clear()
    
    # Сохраняем выбранную модель в состояние
    await state.update_data(selected_model=model_slug, model_id=model.id)

    # Проверяем баланс пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=callback.from_user.id)
    balance = await sync_to_async(BalanceService.get_balance)(user)
    model_cost = await sync_to_async(get_base_price_tokens)(model)

    if balance < model_cost:
        await callback.message.answer(
            f"❌ **Недостаточно токенов**\n\n"
            f"Ваш баланс: ⚡ {balance:.2f} токенов\n"
            f"Стоимость генерации: ⚡ {model_cost:.2f} токенов\n\n"
            f"Необходимо пополнить баланс на ⚡ {model_cost - balance:.2f} токенов",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    # Сохраняем данные для генерации
    await state.update_data(
        model_slug=model_slug,
        model_id=model.id,
        model_name=model.display_name,
        model_provider=model.provider,
        model_price=float(model_cost),
        supports_images=model.supports_image_input,
        generation_type='text2video',
    )

    info_message = get_model_info_message(model, base_price=model_cost)

    await callback.message.answer(
        info_message,
        reply_markup=get_video_format_keyboard(),
        parse_mode="Markdown"
    )

    # Переходим к выбору формата
    await state.set_state(BotStates.video_select_format)
