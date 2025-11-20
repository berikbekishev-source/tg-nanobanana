"""
Обработчики платежей и пополнения баланса
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async

from botapp.states import BotStates
from botapp.keyboards import (
    get_cancel_keyboard,
    get_main_menu_inline_keyboard,
    get_main_menu_keyboard,
    format_balance
)
from botapp.models import TgUser, Transaction, Promocode
from botapp.business.balance import BalanceService

router = Router()
PAYMENT_URL = getattr(settings, 'PAYMENT_MINI_APP_URL', 'https://example.com/payment')


def _format_tokens(amount: Decimal) -> str:
    if amount % 1 == 0:
        return str(int(amount))
    return format(amount.normalize(), "f")


async def _process_promocode_activation(
    message: Message,
    *,
    user: TgUser,
    promo_code_raw: str,
    success_markup,
    failure_markup,
) -> bool:
    promo_code = (promo_code_raw or "").strip()

    if not promo_code:
        await message.answer(
            "Извините, такого промокода нет в базе, пожалуйста введите корректный промокод.",
            reply_markup=failure_markup,
        )
        return False

    try:
        promocode = await sync_to_async(Promocode.objects.get)(
            code__iexact=promo_code,
            is_active=True,
        )
    except Promocode.DoesNotExist:
        await message.answer(
            "Извините, такого промокода нет в базе, пожалуйста введите корректный промокод.",
            reply_markup=failure_markup,
        )
        return False

    now = timezone.now()
    if promocode.valid_from > now or promocode.valid_until < now:
        await message.answer(
            "Извините, такого промокода нет в базе, пожалуйста введите корректный промокод.",
            reply_markup=failure_markup,
        )
        return False

    already_used = await sync_to_async(promocode.used_by.filter(id=user.id).exists)()
    if already_used:
        await message.answer(
            f"Данный промокод уже был активирован, вам уже было начислено "
            f"{_format_tokens(promocode.value)} бонусных токенов.",
            reply_markup=failure_markup,
        )
        return False

    if promocode.max_uses and promocode.current_uses >= promocode.max_uses:
        await message.answer(
            "Извините, такого промокода нет в базе, пожалуйста введите корректный промокод.",
            reply_markup=failure_markup,
        )
        return False

    if promocode.is_percentage:
        await message.answer(
            "Извините, такого промокода нет в базе, пожалуйста введите корректный промокод.",
            reply_markup=failure_markup,
        )
        return False

    bonus_amount = promocode.value
    await sync_to_async(BalanceService.add_bonus)(
        user,
        amount=bonus_amount,
        description=f"Промокод {promocode.code}",
        description_en=f"Promocode {promocode.code}",
    )

    await sync_to_async(promocode.used_by.add)(user)
    promocode.current_uses += 1
    promocode.total_activated += 1
    promocode.total_bonus_given += bonus_amount
    await sync_to_async(promocode.save)(
        update_fields=["current_uses", "total_activated", "total_bonus_given", "updated_at"]
    )

    new_balance = await sync_to_async(BalanceService.get_balance)(user)

    await message.answer(
        f"Поздравляю! {_format_tokens(bonus_amount)} бонусных токенов успешно зачислены! "
        f"Ваш баланс: {format_balance(new_balance)}.",
        reply_markup=success_markup,
    )

    return True


@router.message(F.text == "💳 Пополнить баланс")
async def deposit_from_menu(message: Message, state: FSMContext):
    """
    Обработчик кнопки "Пополнить баланс" из главного меню
    Сразу открывает Mini App
    """
    # Формируем URL с параметрами пользователя
    user_id = message.from_user.id
    username = message.from_user.username or ""
    payment_url = getattr(settings, 'PAYMENT_MINI_APP_URL', 'https://example.com/payment')
    payment_url_with_params = f"{payment_url}?user_id={user_id}&username={username}"

    # Создаем inline кнопку для открытия Mini App
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import WebAppInfo

    builder = InlineKeyboardBuilder()
    builder.button(
        text="💳 Открыть страницу оплаты",
        web_app=WebAppInfo(url=payment_url_with_params)
    )

    await message.answer(
        "💳 **Пополнение баланса**\n\n"
        "Нажмите кнопку ниже, чтобы открыть страницу оплаты.\n\n"
        "Доступные способы оплаты:\n"
        "⭐ Telegram Stars\n"
        "💳 Банковская карта\n\n"
        "После оплаты токены будут зачислены автоматически.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

    # Отправляем кнопку главного меню
    await message.answer(
        "Или вернитесь в меню:",
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )


@router.callback_query(F.data.startswith("payment_success:"))
async def handle_payment_success(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик успешной оплаты через Mini App
    Вызывается из Mini App после успешной оплаты
    """
    await callback.answer()

    # Получаем данные из callback
    data_parts = callback.data.split(":")
    if len(data_parts) < 3:
        await callback.message.answer(
            "❌ Ошибка обработки платежа.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    transaction_id = data_parts[1]
    amount = Decimal(data_parts[2])

    # Получаем пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=callback.from_user.id)

    # Проверяем транзакцию
    try:
        transaction = await sync_to_async(Transaction.objects.get)(
            id=transaction_id,
            user=user,
            is_pending=True
        )

        # Подтверждаем транзакцию
        await sync_to_async(BalanceService.complete_transaction)(
            transaction=transaction,
            status='completed'
        )

        # Получаем обновленный баланс
        new_balance = await sync_to_async(BalanceService.get_balance)(user)

        await callback.message.answer(
            f"✅ **Платеж успешно обработан!**\n\n"
            f"Зачислено: ⚡ {amount} токенов\n"
            f"Ваш текущий баланс: {format_balance(new_balance)}\n\n"
            f"Спасибо за пополнение! Теперь вы можете создавать изображения и видео.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline_keyboard()
        )

    except Transaction.DoesNotExist:
        await callback.message.answer(
            "❌ Транзакция не найдена или уже обработана.",
            reply_markup=get_main_menu_inline_keyboard()
        )
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка при обработке платежа: {str(e)}",
            reply_markup=get_main_menu_inline_keyboard()
        )


@router.callback_query(F.data.startswith("payment_failed:"))
async def handle_payment_failed(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик неудачной оплаты через Mini App
    """
    await callback.answer()

    # Получаем причину из callback
    data_parts = callback.data.split(":", 1)
    reason = data_parts[1] if len(data_parts) > 1 else "Неизвестная ошибка"

    await callback.message.answer(
        f"❌ **Платеж не удался**\n\n"
        f"Причина: {reason}\n\n"
        f"Пожалуйста, попробуйте еще раз или обратитесь в поддержку @support",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline_keyboard()
    )


@router.message(F.successful_payment)
async def handle_telegram_stars_payment(message: Message):
    """
    Обработчик успешной оплаты через Telegram Stars
    Вызывается автоматически после оплаты через встроенный механизм Telegram
    """
    payment = message.successful_payment

    # Получаем пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)

    # Создаем и подтверждаем транзакцию
    try:
        # Конвертируем Stars в токены (1 Star = 10 токенов)
        stars_amount = payment.total_amount  # Количество Stars
        tokens_amount = Decimal(str(stars_amount * 10))

        # Создаем транзакцию
        transaction = await sync_to_async(BalanceService.create_transaction)(
            user=user,
            amount=tokens_amount,
            transaction_type='deposit',
            payment_method='telegram_stars',
            description=f"Пополнение через Telegram Stars: {stars_amount} stars",
            payment_data={
                'telegram_payment_charge_id': payment.telegram_payment_charge_id,
                'provider_payment_charge_id': payment.provider_payment_charge_id,
                'invoice_payload': payment.invoice_payload
            }
        )

        # Подтверждаем транзакцию
        await sync_to_async(BalanceService.complete_transaction)(
            transaction=transaction,
            status='completed'
        )

        # Получаем обновленный баланс
        new_balance = await sync_to_async(BalanceService.get_balance)(user)

        await message.answer(
            f"✅ **Оплата через Telegram Stars успешно обработана!**\n\n"
            f"Получено: ⭐ {stars_amount} Stars\n"
            f"Зачислено: ⚡ {tokens_amount} токенов\n"
            f"Ваш текущий баланс: {format_balance(new_balance)}\n\n"
            f"Спасибо за пополнение! Теперь вы можете создавать изображения и видео.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline_keyboard()
        )

    except Exception as e:
        await message.answer(
            f"❌ Ошибка при обработке платежа: {str(e)}\n\n"
            f"Пожалуйста, обратитесь в поддержку @support с скриншотом этого сообщения.",
            reply_markup=get_main_menu_inline_keyboard()
        )


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """
    Обработчик предварительной проверки платежа Telegram Stars
    """
    # Всегда подтверждаем готовность принять платеж
    await pre_checkout_query.answer(ok=True)


@router.message(F.text.startswith("PROMO"))
async def handle_promocode(message: Message, state: FSMContext):
    """
    Обработчик промокодов (формат: PROMOXXXX).
    Промокод может начислить фиксированное количество токенов.
    """
    user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)

    await _process_promocode_activation(
        message,
        user=user,
        promo_code_raw=message.text,
        success_markup=get_main_menu_inline_keyboard(),
        failure_markup=get_main_menu_inline_keyboard(),
    )


@router.callback_query(F.data == "enter_promocode")
async def prompt_promocode_input(callback: CallbackQuery, state: FSMContext):
    """Запрос ввода промокода из раздела баланса."""
    await callback.answer()
    await state.set_state(BotStates.payment_enter_promocode)

    await callback.message.answer(
        "Введите промокод в чат.",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(BotStates.payment_enter_promocode)
async def process_promocode_input(message: Message, state: FSMContext):
    """Обрабатывает промокод, введённый пользователем в режиме ввода промокода."""
    user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)
    success = await _process_promocode_activation(
        message,
        user=user,
        promo_code_raw=message.text or "",
        success_markup=get_main_menu_inline_keyboard(),
        failure_markup=get_cancel_keyboard(),
    )

    if success:
        await state.clear()
        await state.set_state(BotStates.main_menu)


@router.callback_query(F.data == "main_menu")
async def handle_main_menu_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик inline кнопки "Главное меню"
    """
    await callback.answer()

    # Очищаем состояние
    await state.clear()
    await state.set_state(BotStates.main_menu)

    await callback.message.answer(
        "Выберите нужное  действие нажав на кнопку в меню 👇",
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )
