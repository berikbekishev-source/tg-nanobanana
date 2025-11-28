"""
Глобальные обработчики команд и кнопок меню.
Эти обработчики должны работать из ЛЮБОГО состояния.
"""
from typing import List, Tuple
from urllib.parse import quote_plus

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from django.conf import settings
from asgiref.sync import sync_to_async

from botapp.states import BotStates
from botapp.keyboards import (
    get_main_menu_keyboard,
    get_balance_keyboard,
    get_prices_info,
    get_image_models_keyboard,
    get_main_menu_inline_keyboard,
    get_model_info_message,
    get_image_mode_keyboard,
    get_video_models_keyboard,
    get_video_format_keyboard,
    get_cancel_keyboard,
)
from botapp.models import TgUser, AIModel
from botapp.business.balance import BalanceService
from botapp.business.pricing import get_base_price_tokens
from botapp.reference_prompt import REFERENCE_PROMPT_MODELS

router = Router()

# URL для Mini App
PAYMENT_URL = getattr(settings, 'PAYMENT_MINI_APP_URL', 'https://example.com/payment')
PUBLIC_BASE_URL = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")


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

    # Строим ссылку на оплату с параметрами пользователя
    user_id = message.from_user.id
    username = message.from_user.username or ""
    payment_url = PAYMENT_URL if PAYMENT_URL else (f"{PUBLIC_BASE_URL}/miniapp/" if PUBLIC_BASE_URL else "https://example.com/miniapp/")
    payment_url_with_params = f"{payment_url}?user_id={user_id}&username={username}"

    # Отправляем сообщение с балансом + inline кнопка "Пополнить баланс" (WebApp)
    await message.answer(
        balance_message,
        reply_markup=get_balance_keyboard(payment_url_with_params),
        parse_mode=None
    )

    # Устанавливаем состояние просмотра баланса
    await state.set_state(BotStates.balance_view)


@router.message(StateFilter("*"), Command("balance"))
async def global_cmd_balance(message: Message, state: FSMContext):
    """
    Команда /balance для быстрой проверки баланса из любого состояния.
    """
    # Используем ту же логику что и для кнопки
    await global_show_balance(message, state)


@router.message(StateFilter("*"), F.text == "🎨 Создать изображение")
async def global_create_image_start(message: Message, state: FSMContext):
    """
    Обработчик кнопки 'Создать изображение' - работает из любого состояния.
    Перенаправляет к выбору модели для генерации изображений.
    """
    # Очищаем предыдущее состояние
    await state.clear()
    
    # Получаем активные модели для изображений
    models = await sync_to_async(list)(
        AIModel.objects.filter(type='image', is_active=True)
        .exclude(slug="nano-banana")
        .order_by('order')
    )

    if not models:
        await message.answer(
            "😔 К сожалению, сейчас нет доступных моделей для генерации изображений.\n"
            "Попробуйте позже.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    midjourney_webapps = {}
    gpt_image_webapps = {}
    nano_banana_webapps = {}
    if PUBLIC_BASE_URL:
        for model in models:
            if model.provider == "midjourney":
                cost = await sync_to_async(get_base_price_tokens)(model)
                price_label = f"⚡{cost:.2f} токенов"
                midjourney_webapps[model.slug] = (
                    f"{PUBLIC_BASE_URL}/midjourney/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                )
            if model.provider == "openai_image":
                cost = await sync_to_async(get_base_price_tokens)(model)
                price_label = f"⚡{cost:.2f} токенов"
                gpt_image_webapps[model.slug] = (
                    f"{PUBLIC_BASE_URL}/gpt-image/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                )
            if (
                model.provider in {"gemini_vertex", "gemini"}
                and model.slug.startswith("nano-banana")
                and model.slug != "nano-banana"
            ):
                cost = await sync_to_async(get_base_price_tokens)(model)
                price_label = f"⚡{cost:.2f} токенов"
                nano_banana_webapps[model.slug] = (
                    f"{PUBLIC_BASE_URL}/nanobanana/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                )

    # Отправляем список моделей (Midjourney/GPT Image/Nano Banana открываются сразу через WebApp)
    await message.answer(
        "🎨 Выберите модель для генерации изображений:",
        reply_markup=get_image_models_keyboard(
            models,
            midjourney_webapps=midjourney_webapps,
            gpt_image_webapps=gpt_image_webapps,
            nano_banana_webapps=nano_banana_webapps,
        )
    )

    # Переводим в состояние выбора модели
    await state.set_state(BotStates.image_select_model)


@router.message(StateFilter("*"), F.text == "🎬 Создать видео")
async def global_create_video_start(message: Message, state: FSMContext):
    """
    Обработчик кнопки 'Создать видео' - работает из любого состояния.
    Перенаправляет к выбору модели для генерации видео.
    """
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

    kling_webapps = {}
    veo_webapps = {}
    if PUBLIC_BASE_URL:
        for model in models:
            if model.provider == "kling":
                cost = await sync_to_async(get_base_price_tokens)(model)
                price_label = f"⚡{cost:.2f} токенов"
                default_duration = None
                if isinstance(model.default_params, dict):
                    try:
                        default_duration = int(model.default_params.get("duration") or 0)
                    except (TypeError, ValueError):
                        default_duration = None
                base_duration = default_duration if default_duration and default_duration > 0 else 10
                kling_webapps[model.slug] = (
                    f"{PUBLIC_BASE_URL}/kling/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                    f"&price_base_duration={quote_plus(str(base_duration))}"
                )
            if model.provider == "veo" or model.slug.startswith("veo"):
                cost = await sync_to_async(get_base_price_tokens)(model)
                price_label = f"⚡{cost:.2f} токенов"
                veo_webapps[model.slug] = (
                    f"{PUBLIC_BASE_URL}/veo/?"
                    f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
                )


    sora_webapps = {}
    if PUBLIC_BASE_URL:
        for model in models:
            if model.provider != "openai" or not model.slug.startswith("sora"):
                continue
            cost = await sync_to_async(get_base_price_tokens)(model)
            price_label = f"⚡{cost:.2f} токенов"
            sora_webapps[model.slug] = (
                f"{PUBLIC_BASE_URL}/sora2/?"
                f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
            )

    # Отправляем список моделей
    await message.answer(
        "🎬 Выберите модель для генерации видео:",
        reply_markup=get_video_models_keyboard(
            models,
            kling_webapps=kling_webapps,
            veo_webapps=veo_webapps,
            sora_webapps=sora_webapps,
        )
    )

    # Переводим в состояние выбора модели
    await state.set_state(BotStates.video_select_model)


@router.message(
    StateFilter("*"),
    F.text.in_(
        {
            "Промт по референсу",
            "📲 Промт по референсу",
            "📲Промт по референсу",
            "Промт по рефференсу",
            "📲Промт по рефференсу",
        }
    ),
)
async def global_prompt_by_reference_entry(message: Message, state: FSMContext):
    """
    Обработчик кнопки 'Промт по референсу' - работает из любого состояния.
    Автоматически выбирает первую доступную модель.
    """
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
        "🔗 Скиньте в бота ссылку на любой Reels, Shorts, TikTok или загрузите в чат видео и получите промт для создания точно такого же видео!",
        reply_markup=get_cancel_keyboard(),
    )
    await state.set_state(BotStates.reference_prompt_wait_reference)


@router.callback_query(StateFilter("*"), F.data.startswith("img_model:"))
async def global_select_image_model(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик выбора модели для генерации изображений.
    Работает из любого состояния (переопределяет текущее состояние).
    """
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
        midjourney_params=None,
    )

    if model.provider == "midjourney":
        price_label = f"⚡{model_cost:.2f} токенов"
        if not PUBLIC_BASE_URL:
            await callback.message.answer(
                "⚙️ Веб-версия настроек временно недоступна. Повторите попытку позже.",
                reply_markup=get_cancel_keyboard(),
            )
            await callback.answer()
            return

        webapp_url = (
            f"{PUBLIC_BASE_URL}/midjourney/?"
            f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
        )
        await callback.answer(url=webapp_url)
        await state.set_state(BotStates.midjourney_wait_settings)
        return

    if model.provider in {"gemini_vertex", "gemini"} and model.slug.startswith("nano-banana"):
        price_label = f"⚡{model_cost:.2f} токенов"
        if not PUBLIC_BASE_URL:
            await callback.message.answer(
                "⚙️ Веб-версия настроек временно недоступна. Повторите попытку позже.",
                reply_markup=get_cancel_keyboard(),
            )
            await callback.answer()
            return

        webapp_url = (
            f"{PUBLIC_BASE_URL}/nanobanana/?"
            f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
        )
        try:
            await callback.answer(url=webapp_url)
        except Exception:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚙️ Открыть настройки Nano Banana",
                    web_app=WebAppInfo(url=webapp_url)
                )]
            ])
            await callback.message.answer(
                "Если окно не открылось автоматически, нажмите кнопку ниже.",
                reply_markup=keyboard,
            )
        await state.set_state(BotStates.nano_wait_settings)
        return

    remix_max = model.max_input_images or 4
    info_message = (
        get_model_info_message(model, base_price=model_cost)
        + "\n\nРежимы:\n"
        "• Создать из текста — промт без изображений\n"
        "• Отредактировать — одно изображение + промт\n"
        f"• Ремикс — 2-{remix_max} изображений + промт"
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

    if model.provider == "kling":
        price_label = f"⚡{model_cost:.2f} токенов"
        base = PUBLIC_BASE_URL or "https://example.com"
        default_duration = None
        if isinstance(model.default_params, dict):
            try:
                default_duration = int(model.default_params.get("duration") or 0)
            except (TypeError, ValueError):
                default_duration = None
        base_duration = default_duration if default_duration and default_duration > 0 else 10
        webapp_url = (
            f"{base}/kling/?price={quote_plus(price_label)}"
            f"&price_base_duration={quote_plus(str(base_duration))}"
        )
        try:
            await callback.answer(url=webapp_url)
        except Exception:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚙️ Открыть настройки Kling",
                    web_app=WebAppInfo(url=webapp_url)
                )]
            ])
            await callback.message.answer(
                "Если окно не открылось автоматически, нажмите кнопку ниже.",
                reply_markup=keyboard,
            )
        await state.set_state(BotStates.kling_wait_settings)
        return

    if model.provider == "openai" and model.slug.startswith("sora"):
        price_label = f"⚡{model_cost:.2f} токенов"
        base = PUBLIC_BASE_URL or "https://example.com"
        webapp_url = (
            f"{base}/sora2/?"
            f"model={quote_plus(model.slug)}&price={quote_plus(price_label)}"
        )
        try:
            await callback.answer(url=webapp_url)
        except Exception:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚙️ Открыть настройки Sora 2",
                    web_app=WebAppInfo(url=webapp_url)
                )]
            ])
            await callback.message.answer(
                "Если окно не открылось автоматически, нажмите кнопку ниже.",
                reply_markup=keyboard,
            )
        await state.set_state(BotStates.sora_wait_settings)
        return

    info_message = get_model_info_message(model, base_price=model_cost)

    await callback.message.answer(
        info_message,
        reply_markup=get_video_format_keyboard(),
        parse_mode="Markdown"
    )

    # Переходим к выбору формата
    await state.set_state(BotStates.video_select_format)
