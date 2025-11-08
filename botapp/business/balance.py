"""
Сервис для работы с балансом пользователей и транзакциями.

Функциональность уровня 3:
* хранение и выдача текущего баланса пользователя;
* атомарное списание средств за генерацию;
* начисление депозитов и бонусов;
* обработка возвратов;
* создание/подтверждение отложенных транзакций для платежных шлюзов.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Tuple, Union

from django.db import transaction as db_transaction
from django.utils import timezone

from botapp.models import AIModel, TgUser, Transaction, UserBalance

ZERO = Decimal("0.00")


class InsufficientBalanceError(Exception):
    """Недостаточно средств на балансе пользователя."""


class BalanceService:
    """Бизнес-логика для работы с балансами пользователей."""

    # --------------------------------------------------------------------- #
    # Вспомогательные методы
    # --------------------------------------------------------------------- #

    @staticmethod
    def ensure_balance(user: TgUser, *, for_update: bool = False) -> UserBalance:
        """
        Гарантированно возвращает объект баланса пользователя.

        Args:
            user: инстанс TgUser
            for_update: нужно ли блокировать запись в БД
        """
        manager = UserBalance.objects.select_for_update() if for_update else UserBalance.objects
        balance, created = manager.get_or_create(
            user=user,
            defaults={
                "balance": ZERO,
                "total_spent": ZERO,
                "total_deposited": ZERO,
                "bonus_balance": ZERO,
            },
        )

        if created:
            BalanceService.add_welcome_bonus(user)
            balance.refresh_from_db()

        return balance

    @staticmethod
    def get_balance(user: TgUser) -> Decimal:
        """Текущий баланс пользователя."""
        return BalanceService.ensure_balance(user).balance

    @staticmethod
    def _apply_positive_amount(balance: UserBalance, amount: Decimal, transaction_type: str) -> None:
        """
        Применяет положительную сумму к балансу, обновляя агрегаты.

        Args:
            balance: запись баланса (уже заблокированная select_for_update)
            amount: сумма операции (> 0)
            transaction_type: тип транзакции
        """
        if amount <= ZERO:
            raise ValueError("Положительная операция должна иметь сумму больше 0")

        balance.balance += amount
        update_fields = ["balance", "updated_at"]

        if transaction_type == "deposit":
            balance.total_deposited += amount
            update_fields.append("total_deposited")
        elif transaction_type in {"bonus", "referral"}:
            balance.bonus_balance += amount
            update_fields.append("bonus_balance")
        elif transaction_type == "refund":
            # Возврат уменьшает суммарные списания
            balance.total_spent = max(balance.total_spent - amount, ZERO)
            update_fields.append("total_spent")

        balance.save(update_fields=update_fields)

    @staticmethod
    def _build_transaction_kwargs(
        *,
        user: TgUser,
        amount: Decimal,
        transaction_type: str,
        description: str,
        description_en: Optional[str] = None,
        payment_method: Optional[str] = None,
        payment_id: Optional[str] = None,
        payment_data: Optional[Dict[str, Any]] = None,
        related_transaction: Optional[Transaction] = None,
        generation_request=None,
    ) -> Dict[str, Any]:
        """Формирует kwargs для Transaction.objects.create()."""
        return {
            "user": user,
            "type": transaction_type,
            "amount": amount,
            "description": description,
            "description_en": description_en or description,
            "payment_method": payment_method,
            "payment_id": payment_id,
            "payment_data": payment_data or {},
            "generation_request": generation_request,
            "related_transaction": related_transaction,
        }

    # --------------------------------------------------------------------- #
    # Транзакции (депозиты, бонусы, pending-операции)
    # --------------------------------------------------------------------- #

    @staticmethod
    @db_transaction.atomic
    def create_transaction(
        user: TgUser,
        *,
        amount: Decimal,
        transaction_type: str,
        description: str,
        description_en: Optional[str] = None,
        payment_method: Optional[str] = None,
        payment_id: Optional[str] = None,
        payment_data: Optional[Dict[str, Any]] = None,
        generation_request=None,
        pending: bool = True,
    ) -> Transaction:
        """
        Создаёт транзакцию. Если `pending=False`, средства начисляются сразу.
        Используется для платежных шлюзов и бонусов.
        """
        if amount <= ZERO:
            raise ValueError("Сумма транзакции должна быть больше 0")

        balance = BalanceService.ensure_balance(user, for_update=True)
        current_balance = balance.balance
        anticipated_balance = current_balance if pending else current_balance + amount

        tx = Transaction.objects.create(
            **BalanceService._build_transaction_kwargs(
                user=user,
                amount=amount,
                transaction_type=transaction_type,
                description=description,
                description_en=description_en,
                payment_method=payment_method,
                payment_id=payment_id,
                payment_data=payment_data,
                generation_request=generation_request,
            ),
            balance_after=anticipated_balance,
            is_pending=pending,
            is_completed=not pending,
        )

        if pending:
            tx.balance_after = current_balance
            tx.save(update_fields=["balance_after"])
            return tx

        BalanceService._apply_positive_amount(balance, amount, transaction_type)
        tx.balance_after = balance.balance
        tx.is_pending = False
        tx.is_completed = True
        tx.save(update_fields=["balance_after", "is_pending", "is_completed"])
        return tx

    @staticmethod
    @db_transaction.atomic
    def complete_transaction(
        transaction: Union[Transaction, int],
        *,
        status: str = "completed",
    ) -> Transaction:
        """
        Подтверждает или отклоняет ранее созданную pending-транзакцию.

        Args:
            transaction: объект Transaction или его ID
            status: 'completed' или 'failed'
        """
        if status not in {"completed", "failed"}:
            raise ValueError("status должен быть 'completed' или 'failed'")

        if isinstance(transaction, int):
            tx = Transaction.objects.select_for_update().get(id=transaction)
        else:
            tx = Transaction.objects.select_for_update().get(id=transaction.id)

        if not tx.is_pending:
            return tx  # уже обработана

        if status == "failed":
            tx.is_pending = False
            tx.is_completed = False
            tx.save(update_fields=["is_pending", "is_completed"])
            return tx

        balance = BalanceService.ensure_balance(tx.user, for_update=True)
        BalanceService._apply_positive_amount(balance, tx.amount, tx.type)
        tx.balance_after = balance.balance
        tx.is_pending = False
        tx.is_completed = True
        tx.save(update_fields=["balance_after", "is_pending", "is_completed"])

        if tx.type == "deposit":
            BalanceService.add_first_deposit_bonus(tx.user, deposit_amount=tx.amount)

        return tx

    # --------------------------------------------------------------------- #
    # Генерация и списания
    # --------------------------------------------------------------------- #

    @staticmethod
    @db_transaction.atomic
    def charge_for_generation(
        user: TgUser,
        ai_model: AIModel,
        quantity: int = 1,
        total_cost_tokens: Optional[Decimal] = None,
    ) -> Transaction:
        """
        Списывает средства за генерацию и создаёт запись транзакции.
        """
        if quantity <= 0:
            raise ValueError("quantity должен быть положительным")

        if total_cost_tokens is not None:
            total_cost = total_cost_tokens.quantize(Decimal("0.01"))
        else:
            total_cost = (ai_model.price * quantity).quantize(Decimal("0.01"))
        balance = BalanceService.ensure_balance(user, for_update=True)

        if balance.balance < total_cost:
            raise InsufficientBalanceError(
                f"Недостаточно средств. Баланс: {balance.balance}, требуется: {total_cost}"
            )

        balance.balance -= total_cost
        balance.total_spent += total_cost
        balance.save(update_fields=["balance", "total_spent", "updated_at"])

        transaction = Transaction.objects.create(
            **BalanceService._build_transaction_kwargs(
                user=user,
                amount=-total_cost,
                transaction_type="generation",
                description=f"Генерация {ai_model.display_name} x{quantity}",
                description_en=f"Generation {ai_model.display_name} x{quantity}",
            ),
            balance_after=balance.balance,
            is_completed=True,
            is_pending=False,
        )

        return transaction

    # --------------------------------------------------------------------- #
    # Бонусы и депозиты
    # --------------------------------------------------------------------- #

    @staticmethod
    def add_bonus(
        user: TgUser,
        *,
        amount: Decimal,
        description: str,
        description_en: Optional[str] = None,
    ) -> Transaction:
        """Начисляет бонус и записывает транзакцию."""
        if amount <= ZERO:
            raise ValueError("Сумма бонуса должна быть больше 0")

        return BalanceService.create_transaction(
            user,
            amount=amount,
            transaction_type="bonus",
            description=description,
            description_en=description_en,
            payment_method="bonus",
            pending=False,
        )

    @staticmethod
    def add_deposit(
        user: TgUser,
        *,
        amount: Decimal,
        payment_method: str,
        payment_id: Optional[str] = None,
        payment_data: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> Transaction:
        """Начисляет депозит (используется для админских сценариев)."""
        if amount <= ZERO:
            raise ValueError("Сумма депозита должна быть больше 0")

        return BalanceService.create_transaction(
            user,
            amount=amount,
            transaction_type="deposit",
            description=description or f"Пополнение через {payment_method}",
            payment_method=payment_method,
            payment_id=payment_id,
            payment_data=payment_data,
            pending=False,
        )

    @staticmethod
    def add_welcome_bonus(user: TgUser) -> Optional[Transaction]:
        """Начисляет приветственный бонус, если он ещё не выдавался."""
        if Transaction.objects.filter(
            user=user,
            type="bonus",
            description__icontains="приветственный бонус",
        ).exists():
            return None

        return BalanceService.add_bonus(
            user,
            amount=Decimal("5.00"),
            description="Приветственный бонус",
            description_en="Welcome bonus",
        )

    @staticmethod
    def add_first_deposit_bonus(user: TgUser, *, deposit_amount: Decimal) -> Optional[Transaction]:
        """20% бонус за первое пополнение (максимум 50 токенов)."""
        if Transaction.objects.filter(
            user=user,
            type="bonus",
            description__icontains="первое пополнение",
        ).exists():
            return None

        bonus_amount = min(deposit_amount * Decimal("0.20"), Decimal("50.00"))

        return BalanceService.add_bonus(
            user,
            amount=bonus_amount,
            description="Бонус за первое пополнение (+20%)",
            description_en="First deposit bonus (+20%)",
        )

    @staticmethod
    @db_transaction.atomic
    def add_referral_bonus(referrer: TgUser, referred: TgUser) -> Tuple[Transaction, Transaction]:
        """Начисляет бонусы за приглашение друга."""
        referrer_balance = BalanceService.ensure_balance(referrer, for_update=True)
        referred_balance = BalanceService.ensure_balance(referred, for_update=True)

        referrer_tx = BalanceService.create_transaction(
            referrer,
            amount=Decimal("10.00"),
            transaction_type="referral",
            description=f"Реферальный бонус за {referred.username or referred.chat_id}",
            description_en=f"Referral bonus for {referred.username or referred.chat_id}",
            pending=False,
        )
        referrer_balance.referral_earnings += Decimal("10.00")
        referrer_balance.save(update_fields=["referral_earnings", "updated_at"])

        referred_tx = BalanceService.create_transaction(
            referred,
            amount=Decimal("5.00"),
            transaction_type="bonus",
            description="Бонус за регистрацию по реферальной ссылке",
            description_en="Referral signup bonus",
            pending=False,
        )

        return referrer_tx, referred_tx

    # --------------------------------------------------------------------- #
    # Возвраты и история
    # --------------------------------------------------------------------- #

    @staticmethod
    @db_transaction.atomic
    def refund_generation(user: TgUser, original_transaction: Transaction, *, reason: str) -> Transaction:
        """Возвращает средства за неудачную генерацию."""
        if original_transaction.amount >= ZERO:
            raise ValueError("Оригинальная транзакция должна быть списанием")

        refund_amount = abs(original_transaction.amount)
        balance = BalanceService.ensure_balance(user, for_update=True)
        BalanceService._apply_positive_amount(balance, refund_amount, "refund")

        refund_tx = Transaction.objects.create(
            **BalanceService._build_transaction_kwargs(
                user=user,
                amount=refund_amount,
                transaction_type="refund",
                description=f"Возврат за неудачную генерацию: {reason}",
                description_en=f"Refund for failed generation: {reason}",
                related_transaction=original_transaction,
            ),
            balance_after=balance.balance,
            is_completed=True,
            is_pending=False,
        )

        return refund_tx

    @staticmethod
    def get_user_transactions(user: TgUser, *, limit: int = 50):
        """Последние транзакции пользователя."""
        return Transaction.objects.filter(user=user).order_by("-created_at")[:limit]

    # --------------------------------------------------------------------- #
    # Проверка возможности генерации
    # --------------------------------------------------------------------- #

    @staticmethod
    def check_can_generate(
        user: TgUser,
        ai_model: AIModel,
        *,
        quantity: int = 1,
        total_cost_tokens: Optional[Decimal] = None,
    ) -> Tuple[bool, str]:
        """Проверка остатка средств и лимитов модели перед генерацией."""
        if quantity <= 0:
            return False, "Количество генераций должно быть больше 0"

        balance = BalanceService.ensure_balance(user)
        if total_cost_tokens is not None:
            total_cost = total_cost_tokens.quantize(Decimal("0.01"))
        else:
            total_cost = (ai_model.price * quantity).quantize(Decimal("0.01"))

        if balance.balance < total_cost:
            needed = total_cost - balance.balance
            return (
                False,
                f"Недостаточно средств. Баланс: {balance.balance} токенов, требуется: {total_cost} токенов "
                f"(нужно пополнить на {needed} токенов)",
            )

        if ai_model.daily_limit:
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_generations = Transaction.objects.filter(
                user=user,
                type="generation",
                created_at__gte=today_start,
                generation_request__ai_model=ai_model,
            ).count()

            if today_generations >= ai_model.daily_limit:
                return False, f"Достигнут дневной лимит для модели {ai_model.display_name}"

        return True, "OK"
