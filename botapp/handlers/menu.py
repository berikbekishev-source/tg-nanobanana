"""
Обработчики главного меню и команд
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from django.conf import settings

from botapp.states import BotStates
from botapp.keyboards import (
    get_main_menu_keyboard,
    get_back_to_menu_keyboard,
    get_balance_keyboard,
    format_balance,
    get_prices_info
)
from botapp.models import TgUser, UserSettings
from botapp.business.balance import BalanceService
from asgiref.sync import sync_to_async

router = Router()

# URL для Mini App (будет браться из настроек)
PAYMENT_URL = getattr(settings, 'PAYMENT_MINI_APP_URL', 'https://example.com/payment')


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
            "Я помогу вам создавать потрясающие изображения и видео с помощью AI.\n\n"
            "🎁 Вам начислен приветственный бонус: 5 токенов!\n\n"
            "Выберите, что хотите создать:"
        )
    else:
        welcome_text = f"👋 С возвращением, {message.from_user.first_name}!\n\nЧто будем создавать сегодня?"

    # Отправляем приветственное сообщение с главным меню
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )

    # Устанавливаем состояние главного меню
    await state.set_state(BotStates.main_menu)


@router.message(F.text == "🏠 Главное меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await state.set_state(BotStates.main_menu)

    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )


@router.message(F.text == "💰 Мой баланс (цены)")
async def show_balance(message: Message, state: FSMContext):
    """
    Обработчик кнопки 'Мой баланс (цены)'
    Отправляет сообщение с текущим балансом пользователя и ценами
    """
    # Получаем пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)

    # Получаем баланс пользователя
    balance = await sync_to_async(BalanceService.get_balance)(user)

    # Формируем сообщение с балансом и ценами
    balance_message = (
        f"💰 **Ваш текущий баланс:**\n"
        f"{format_balance(balance)}\n\n"
        f"{get_prices_info()}"
    )

    # Отправляем сообщение с балансом + inline кнопка "Пополнить баланс"
    await message.answer(
        balance_message,
        reply_markup=get_balance_keyboard(),
        parse_mode="Markdown"
    )

    # Меняем клавиатуру на кнопку "Главное меню"
    await message.answer(
        "Выберите действие:",
        reply_markup=get_back_to_menu_keyboard()
    )

    # Устанавливаем состояние просмотра баланса
    await state.set_state(BotStates.balance_view)


@router.callback_query(F.data == "deposit")
async def deposit_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик inline кнопки "Пополнить баланс" из раздела баланса
    Сразу отправляет ссылку на Mini App
    """
    await callback.answer()

    # Формируем URL с параметрами пользователя
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    payment_url_with_params = f"{PAYMENT_URL}?user_id={user_id}&username={username}"

    # Создаем inline кнопку для открытия Mini App
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import WebAppInfo

    builder = InlineKeyboardBuilder()
    builder.button(
        text="💳 Открыть страницу оплаты",
        web_app=WebAppInfo(url=payment_url_with_params)
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


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки отмены"""
    await callback.answer("Действие отменено")
    await callback.message.delete()

    await state.clear()

    # Возвращаем в главное меню
    await callback.message.answer(
        "Главное меню:",
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


@router.message(Command("balance"))
async def cmd_balance(message: Message, state: FSMContext):
    """Быстрая команда для проверки баланса"""
    # Вызываем тот же обработчик, что и для кнопки
    await show_balance(message, state)
