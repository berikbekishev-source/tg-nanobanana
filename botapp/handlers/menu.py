"""
Обработчики главного меню и команд
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from django.conf import settings

from botapp.states import BotStates
from botapp.keyboards import (
    get_main_menu_keyboard,
    get_balance_keyboard,
    get_prices_info,
    get_support_keyboard,
)
from botapp.models import TgUser, UserSettings
from botapp.business.balance import BalanceService
from asgiref.sync import sync_to_async

router = Router()
MAIN_MENU_ACTIONS = {
    "🎨 Создать изображение",
    "🎬 Создать видео",
    "📲 Промт по референсу",
    "💰 Мой баланс (цены)",
    "💳 Пополнить баланс",
    "🎁 Ввести промокод",
    "🧡 Поддержка",
    "🏠Главное меню",
    "🏠 Главное меню",
}

# URL для Mini App (будет браться из настроек)
_configured_payment_url = getattr(settings, 'PAYMENT_MINI_APP_URL', None)
_public_base_url = getattr(settings, 'PUBLIC_BASE_URL', '')
if _configured_payment_url:
    PAYMENT_URL = _configured_payment_url
elif _public_base_url:
    PAYMENT_URL = f"{_public_base_url.rstrip('/')}/miniapp/"
else:
    PAYMENT_URL = 'https://example.com/miniapp/'


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    # Очищаем состояние
    await state.clear()

    # Получаем или создаем пользователя
    user, created = await sync_to_async(TgUser.objects.get_or_create)(
        chat_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or '',
            'first_name': message.from_user.first_name or '',
            'last_name': message.from_user.last_name or '',
            'language_code': message.from_user.language_code or 'ru'
        }
    )
    await sync_to_async(UserSettings.objects.get_or_create)(user=user)

    # Создаем баланс для нового пользователя
    if created:
        await sync_to_async(BalanceService.ensure_balance)(user)
    welcome_text = (
        f"👋 Добро пожаловать, {message.from_user.first_name}!\n\n"
        "Меня зовут INTEGER и вот что я умею:\n\n"
        "🖼 Генерация картинок в NanoBanana и GPT\n\n"
        "📹 Генерация видео через Sora2, VEO 3, Kling\n\n"
        "🔍 Промт по референсу. Скинь в бота ссылку на любой Reels, Shorts, TikTok и получи промт для генерации точно такого же видео!\n\n"
        "Нажмите на кнопку в меню и выберите что хотите создать 👇"
    )

    # Отправляем приветственное сообщение с главным меню
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )

    # Устанавливаем состояние главного меню
    await state.set_state(BotStates.main_menu)


# Обработчик кнопки "🏠 Главное меню" перенесен в global_commands.py
# чтобы работать из любого состояния

# Обработчик кнопки "💰 Мой баланс (цены)" перенесен в global_commands.py
# чтобы работать из любого состояния


@router.message(StateFilter("*"), F.text == "🧡 Поддержка")
async def support_contact(message: Message):
    """Контакт с админом"""
    await message.answer(
        "Если нужна помощь, напишите админу. Нажмите кнопку ниже, чтобы открыть чат.",
        reply_markup=get_support_keyboard()
    )


@router.callback_query(StateFilter("*"), F.data == "deposit")
async def deposit_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик inline кнопки "Пополнить баланс" из раздела баланса
    Сразу отправляет ссылку на Mini App
    """
    await callback.answer()

    # Формируем URL с параметрами пользователя
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    configured_payment_url = PAYMENT_URL
    if configured_payment_url:
        payment_url = configured_payment_url
    else:
        public_base = getattr(settings, "PUBLIC_BASE_URL", "")
        payment_url = f"{public_base.rstrip('/')}/miniapp/" if public_base else "https://example.com/miniapp/"
    payment_url_with_params = f"{payment_url}?user_id={user_id}&username={username}"

    # Создаем inline кнопку для открытия Mini App
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import WebAppInfo

    builder = InlineKeyboardBuilder()
    builder.button(
        text="💳 Открыть страницу оплаты",
        web_app=WebAppInfo(url=payment_url_with_params)
    )
    # Фолбек: обычная ссылка, если WebApp заблокирован Телеграмом
    builder.button(
        text="🌐 Открыть в браузере",
        url=payment_url_with_params
    )

    await callback.message.answer(
        "💳 **Пополнение баланса**\n\n"
        "Нажмите кнопку ниже, чтобы открыть страницу оплаты.\n\n"
        "Доступные способы оплаты:\n"
        "⭐ Telegram Stars\n"
        "💳 Банковская карта\n\n"
        "После оплаты токены будут зачислены автоматически.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(StateFilter("*"), F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки отмены"""
    await callback.answer("Действие отменено")
    await callback.message.delete()

    current_state = await state.get_state()
    await state.clear()

    reference_flow_states = {
        BotStates.reference_prompt_wait_reference.state,
        BotStates.reference_prompt_confirm_mods.state,
        BotStates.reference_prompt_wait_mods.state,
    }

    reply_text = (
        "Режим промта по референсу отменён. Главное меню ниже."
        if current_state in reference_flow_states
        else "Выберите нужное  действие нажав на кнопку в меню 👇"
    )

    await callback.message.answer(
        reply_text,
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )

    await state.set_state(BotStates.main_menu)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "❓ **Помощь по использованию бота**\n\n"
        "**Основные команды:**\n"
        "/start - Перезапустить бота\n"
        "/help - Показать это сообщение\n\n"
        "**Как пользоваться:**\n"
        "1. Выберите тип контента (изображение или видео)\n"
        "2. Выберите модель для генерации\n"
        "3. Отправьте текстовое описание или загрузите изображение\n"
        "4. Дождитесь результата\n\n"
        "**Баланс:**\n"
        "Для генерации нужны токены. Проверить баланс можно в меню 'Мой баланс (цены)'\n\n"
        "**Оплата:**\n"
        "Доступны два способа оплаты:\n"
        "⭐ Telegram Stars - оплата через встроенную систему Telegram\n"
        "💳 Банковская карта - безопасная оплата через платежный шлюз\n\n"
        "По всем вопросам: @support"
    )

    await message.answer(help_text, parse_mode="Markdown")


# Команда /balance перенесена в global_commands.py
# чтобы работать из любого состояния


@router.message(BotStates.main_menu, ~F.text.in_(MAIN_MENU_ACTIONS))
async def handle_free_text_in_main_menu(message: Message):
    """Ответ на произвольный текст в главном меню"""
    await message.answer(
        "Для начала работы пожалуйста выберите нужное действие нажав на кнопку в меню 👇",
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )
