"""
Утилиты бонусной системы (этап 3).

Сценарии:
* приветственный бонус при первом появлении пользователя;
* бонус за первое пополнение;
* реферальная награда (пригласившему и приглашённому);
* ежедневная награда с семидневной лестницей.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional, Tuple

from django.utils import timezone

from botapp.business.balance import BalanceService
from botapp.models import TgUser, Transaction, UserSettings


class BonusService:
    """Высокоуровневая работа с бонусами."""

    DAILY_REWARD_SEQUENCE = (
        Decimal("1.00"),
        Decimal("1.50"),
        Decimal("2.00"),
        Decimal("2.50"),
        Decimal("3.00"),
        Decimal("4.00"),
        Decimal("5.00"),
    )

    @staticmethod
    def grant_welcome_bonus(user: TgUser) -> Optional[Transaction]:
        """Передаёт выдачу приветственного бонуса на уровень BalanceService."""
        return BalanceService.add_welcome_bonus(user)

    @staticmethod
    def grant_first_deposit_bonus(user: TgUser, *, deposit_amount: Decimal) -> Optional[Transaction]:
        """Бонус за первое пополнение – 20% от суммы, максимум 50 токенов."""
        return BalanceService.add_first_deposit_bonus(user, deposit_amount=deposit_amount)

    @staticmethod
    def grant_referral_bonus(referrer: TgUser, referred: TgUser) -> Tuple[Transaction, Transaction]:
        """Бонусы обеим сторонам реферальной программы."""
        return BalanceService.add_referral_bonus(referrer, referred)

    # ------------------------------------------------------------------ #
    # Ежедневные награды
    # ------------------------------------------------------------------ #

    @classmethod
    def claim_daily_reward(cls, user: TgUser) -> Tuple[Optional[Transaction], int]:
        """
        Возвращает кортеж (транзакция, текущая_серия).
        Если уже получал сегодня – возвращает (None, streak).
        """
        settings = BonusService._get_user_settings(user)
        if not settings:
            return None, 0

        now = timezone.now()
        last_claim = settings.last_daily_reward_at

        # Уже получал сегодня
        if last_claim and last_claim.date() == now.date():
            return None, settings.daily_reward_streak

        # Определяем новую серию
        if last_claim and (now - last_claim) <= timedelta(days=1):
            streak = min(settings.daily_reward_streak + 1, len(cls.DAILY_REWARD_SEQUENCE))
        else:
            streak = 1

        reward_amount = cls.DAILY_REWARD_SEQUENCE[streak - 1]
        transaction = BalanceService.add_bonus(
            user,
            amount=reward_amount,
            description=f"Ежедневная награда (день {streak})",
            description_en=f"Daily reward (day {streak})",
        )

        settings.daily_reward_streak = streak
        settings.last_daily_reward_at = now
        settings.save(update_fields=["daily_reward_streak", "last_daily_reward_at", "updated_at"])

        return transaction, streak

    @staticmethod
    def _get_user_settings(user: TgUser) -> Optional[UserSettings]:
        """Безопасно возвращает настройки пользователя (если созданы)."""
        try:
            return user.settings
        except UserSettings.DoesNotExist:
            return None

