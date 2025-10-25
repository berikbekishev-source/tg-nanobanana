"""
Вспомогательные декораторы для хендлеров.

Сейчас реализован один базовый сценарий:
`check_balance_and_charge` — проверяет, что у пользователя есть средства
для выбранной модели, и выполняет списание перед запуском обработчика.
"""
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional

from asgiref.sync import sync_to_async
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.keyboards import get_main_menu_inline_keyboard
from botapp.models import AIModel, TgUser


def check_balance_and_charge(
    *,
    model_slug: Optional[str] = None,
    state_model_key: str = "model_id",
) -> Callable:
    """
    Проверяет баланс пользователя и выполняет списание через BalanceService.

    Использование:

    ```
    @check_balance_and_charge(model_slug="nano-banana")
    async def handler(message: Message, state: FSMContext):
        ...
    ```
    Или если модель лежит в состоянии FSM (`state.update_data(model_id=...)`):
    ```
    @check_balance_and_charge()
    async def handler(message: Message, state: FSMContext):
        ...
    ```
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            message: Optional[Message] = None
            callback: Optional[CallbackQuery] = None
            state: Optional[FSMContext] = None

            for arg in args:
                if isinstance(arg, Message):
                    message = arg
                elif isinstance(arg, CallbackQuery):
                    callback = arg
                    message = arg.message
                elif isinstance(arg, FSMContext):
                    state = arg

            if not message:
                raise ValueError("Декоратор check_balance_and_charge ожидает Message или CallbackQuery")

            user_id = callback.from_user.id if callback else message.from_user.id

            try:
                user = await sync_to_async(TgUser.objects.get)(chat_id=user_id)
            except TgUser.DoesNotExist:
                await message.answer(
                    "❌ Пользователь не найден. Используйте /start, чтобы начать заново.",
                    reply_markup=get_main_menu_inline_keyboard(),
                )
                return

            ai_model: Optional[AIModel] = None
            if model_slug:
                ai_model = await sync_to_async(AIModel.objects.filter(slug=model_slug, is_active=True).first)()
            elif state:
                data = await state.get_data()
                model_id = data.get(state_model_key)
                if model_id:
                    ai_model = await sync_to_async(
                        AIModel.objects.filter(id=model_id, is_active=True).first
                    )()

            if not ai_model:
                await message.answer(
                    "❌ Модель не найдена или временно недоступна.",
                    reply_markup=get_main_menu_inline_keyboard(),
                )
                return

            try:
                transaction = await sync_to_async(BalanceService.charge_for_generation)(user, ai_model)
            except InsufficientBalanceError as exc:
                await message.answer(
                    f"❌ {exc}",
                    reply_markup=get_main_menu_inline_keyboard(),
                )
                if state:
                    await state.clear()
                return

            if state:
                await state.update_data(transaction_id=transaction.id, model_id=ai_model.id)

            return await func(*args, **kwargs)

        return wrapper

    return decorator

