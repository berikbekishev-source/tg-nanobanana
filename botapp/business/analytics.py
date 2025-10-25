"""
Аналитический сервис для отслеживания метрик и статистики
"""
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from django.utils import timezone
from django.db.models import (
    Count, Sum, Avg, Q, F,
    ExpressionWrapper, DecimalField,
    DateTimeField, IntegerField
)
from django.db.models.functions import TruncDate, TruncHour, TruncWeek, TruncMonth
import json

from ..models import (
    TgUser,
    GenRequest,
    Transaction,
    AIModel,
    UserBalance
)


class AnalyticsService:
    """
    Сервис для сбора и анализа метрик использования бота
    """

    @classmethod
    def get_model_usage_stats(cls,
                             model: Optional[AIModel] = None,
                             period_days: int = 30) -> Dict[str, Any]:
        """
        Статистика использования моделей

        Args:
            model: Конкретная модель или None для всех
            period_days: Период анализа в днях

        Returns:
            Словарь со статистикой
        """
        start_date = timezone.now() - timedelta(days=period_days)

        # Базовый queryset
        qs = GenRequest.objects.filter(
            created_at__gte=start_date,
            status='done'
        )

        if model:
            qs = qs.filter(ai_model=model)

        # Общая статистика
        total_stats = qs.aggregate(
            total_requests=Count('id'),
            unique_users=Count('user', distinct=True),
            total_revenue=Sum('cost'),
            avg_cost=Avg('cost'),
            success_rate=Count('id', filter=Q(status='done')) * 100.0 / Count('id')
        )

        # Статистика по типам генерации
        by_type = qs.values('generation_type').annotate(
            count=Count('id'),
            revenue=Sum('cost')
        ).order_by('-count')

        # Статистика по дням
        daily_stats = qs.annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            requests=Count('id'),
            revenue=Sum('cost'),
            users=Count('user', distinct=True)
        ).order_by('date')

        # Топ пользователей по модели
        top_users = qs.values(
            'user__username',
            'user__chat_id'
        ).annotate(
            generations=Count('id'),
            spent=Sum('cost')
        ).order_by('-generations')[:10]

        # Средняя задержка генерации
        completed_requests = qs.filter(
            status='done',
            updated_at__isnull=False
        ).annotate(
            duration=ExpressionWrapper(
                F('updated_at') - F('created_at'),
                output_field=IntegerField()
            )
        )

        avg_duration = completed_requests.aggregate(
            avg_seconds=Avg('duration')
        )['avg_seconds']

        return {
            'period_days': period_days,
            'model': model.display_name if model else 'All models',
            'total_stats': total_stats,
            'by_type': list(by_type),
            'daily_stats': list(daily_stats),
            'top_users': list(top_users),
            'avg_generation_time': avg_duration
        }

    @classmethod
    def get_revenue_analytics(cls, period_days: int = 30) -> Dict[str, Any]:
        """
        Аналитика доходов

        Args:
            period_days: Период анализа

        Returns:
            Словарь с финансовой аналитикой
        """
        start_date = timezone.now() - timedelta(days=period_days)

        # Доходы от генераций
        generation_revenue = Transaction.objects.filter(
            created_at__gte=start_date,
            transaction_type='generation',
            status='completed'
        ).aggregate(
            total=Sum('amount'),
            count=Count('id'),
            avg=Avg('amount')
        )

        # Доходы от пополнений
        deposit_revenue = Transaction.objects.filter(
            created_at__gte=start_date,
            transaction_type='deposit',
            status='completed'
        ).aggregate(
            total=Sum('amount'),
            count=Count('id'),
            avg=Avg('amount')
        )

        # Расходы на бонусы
        bonus_expenses = Transaction.objects.filter(
            created_at__gte=start_date,
            transaction_type='bonus',
            status='completed'
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )

        # Доходы по методам оплаты
        by_payment_method = Transaction.objects.filter(
            created_at__gte=start_date,
            transaction_type='deposit',
            status='completed'
        ).values('payment_method').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        # Доходы по моделям
        by_model = GenRequest.objects.filter(
            created_at__gte=start_date,
            status='done'
        ).values(
            'ai_model__display_name',
            'ai_model__slug'
        ).annotate(
            revenue=Sum('cost'),
            requests=Count('id')
        ).order_by('-revenue')

        # ARPU (Average Revenue Per User)
        active_users = TgUser.objects.filter(
            transactions__created_at__gte=start_date,
            transactions__transaction_type='generation'
        ).distinct().count()

        arpu = (generation_revenue['total'] or 0) / active_users if active_users > 0 else 0

        # Конверсия (пользователи, которые сделали платеж)
        total_users = TgUser.objects.filter(created_at__gte=start_date).count()
        paying_users = TgUser.objects.filter(
            transactions__transaction_type='deposit',
            transactions__status='completed',
            transactions__created_at__gte=start_date
        ).distinct().count()

        conversion_rate = (paying_users / total_users * 100) if total_users > 0 else 0

        return {
            'period_days': period_days,
            'generation_revenue': generation_revenue,
            'deposit_revenue': deposit_revenue,
            'bonus_expenses': bonus_expenses,
            'net_revenue': (deposit_revenue['total'] or 0) - (bonus_expenses['total'] or 0),
            'by_payment_method': list(by_payment_method),
            'by_model': list(by_model),
            'arpu': float(arpu),
            'conversion_rate': float(conversion_rate),
            'active_users': active_users,
            'paying_users': paying_users,
            'total_users': total_users
        }

    @classmethod
    def get_user_analytics(cls, period_days: int = 30) -> Dict[str, Any]:
        """
        Аналитика пользователей

        Args:
            period_days: Период анализа

        Returns:
            Словарь с пользовательской аналитикой
        """
        start_date = timezone.now() - timedelta(days=period_days)

        # Новые пользователи
        new_users = TgUser.objects.filter(
            created_at__gte=start_date
        ).count()

        # Активные пользователи (сделали хотя бы одну генерацию)
        active_users = TgUser.objects.filter(
            requests__created_at__gte=start_date
        ).distinct().count()

        # Retention (пользователи, вернувшиеся на следующий день)
        yesterday = timezone.now().date() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)

        users_day_before = TgUser.objects.filter(
            requests__created_at__date=day_before
        ).distinct()

        users_returned = users_day_before.filter(
            requests__created_at__date=yesterday
        ).distinct().count()

        retention_rate = (users_returned / users_day_before.count() * 100) if users_day_before.exists() else 0

        # Распределение по количеству генераций
        generation_distribution = TgUser.objects.annotate(
            total_generations=Count('requests')
        ).values('total_generations').annotate(
            users=Count('id')
        ).order_by('total_generations')

        # Топ пользователей по тратам
        top_spenders = TgUser.objects.filter(
            transactions__created_at__gte=start_date,
            transactions__transaction_type='generation'
        ).annotate(
            total_spent=Sum('transactions__amount')
        ).order_by('-total_spent')[:20]

        # Средние показатели на пользователя
        user_averages = TgUser.objects.filter(
            created_at__gte=start_date
        ).aggregate(
            avg_balance=Avg('balance__balance'),
            avg_generations=Avg(
                Count('requests')
            ),
            avg_spent=Avg(
                Sum('transactions__amount',
                    filter=Q(transactions__transaction_type='generation'))
            )
        )

        # Пользователи по языкам
        by_language = TgUser.objects.values('language_code').annotate(
            count=Count('id')
        ).order_by('-count')

        return {
            'period_days': period_days,
            'new_users': new_users,
            'active_users': active_users,
            'retention_rate': float(retention_rate),
            'generation_distribution': list(generation_distribution)[:20],
            'top_spenders': [
                {
                    'username': u.username,
                    'chat_id': u.chat_id,
                    'total_spent': float(u.total_spent or 0)
                }
                for u in top_spenders
            ],
            'user_averages': user_averages,
            'by_language': list(by_language)
        }

    @classmethod
    def get_performance_metrics(cls) -> Dict[str, Any]:
        """
        Метрики производительности системы

        Returns:
            Словарь с метриками производительности
        """
        now = timezone.now()
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)

        # Запросы за последний час
        hourly_requests = GenRequest.objects.filter(
            created_at__gte=last_hour
        ).count()

        # Успешность за последний день
        daily_requests = GenRequest.objects.filter(
            created_at__gte=last_day
        )

        success_rate = daily_requests.filter(
            status='done'
        ).count() / daily_requests.count() * 100 if daily_requests.exists() else 0

        # Среднее время генерации по моделям
        avg_times_by_model = GenRequest.objects.filter(
            created_at__gte=last_day,
            status='done',
            updated_at__isnull=False
        ).values(
            'ai_model__display_name'
        ).annotate(
            avg_time=Avg(
                ExpressionWrapper(
                    F('updated_at') - F('created_at'),
                    output_field=IntegerField()
                )
            ),
            count=Count('id')
        )

        # Очередь ожидания
        pending_requests = GenRequest.objects.filter(
            status='pending'
        ).count()

        # Ошибки за последний день
        errors = GenRequest.objects.filter(
            created_at__gte=last_day,
            status='error'
        ).count()

        # Загрузка по часам
        hourly_load = GenRequest.objects.filter(
            created_at__gte=last_day
        ).annotate(
            hour=TruncHour('created_at')
        ).values('hour').annotate(
            requests=Count('id')
        ).order_by('hour')

        return {
            'hourly_requests': hourly_requests,
            'daily_success_rate': float(success_rate),
            'avg_times_by_model': list(avg_times_by_model),
            'pending_requests': pending_requests,
            'daily_errors': errors,
            'hourly_load': list(hourly_load),
            'timestamp': now.isoformat()
        }

    @classmethod
    def get_model_comparison(cls) -> List[Dict[str, Any]]:
        """
        Сравнение эффективности моделей

        Returns:
            Список с данными по каждой модели
        """
        models = AIModel.objects.filter(is_active=True)
        comparison = []

        for model in models:
            stats = GenRequest.objects.filter(
                ai_model=model,
                created_at__gte=timezone.now() - timedelta(days=30)
            ).aggregate(
                total_requests=Count('id'),
                success_rate=Count('id', filter=Q(status='done')) * 100.0 / Count('id'),
                total_revenue=Sum('cost'),
                unique_users=Count('user', distinct=True),
                avg_satisfaction=Avg('user_rating')  # Если добавить рейтинг
            )

            # Добавляем информацию о модели
            stats.update({
                'model_name': model.display_name,
                'model_slug': model.slug,
                'model_type': model.type,
                'price': float(model.price),
                'provider': model.provider,
                'roi': float(stats['total_revenue'] or 0) / float(model.price) if model.price > 0 else 0
            })

            comparison.append(stats)

        # Сортируем по доходу
        comparison.sort(key=lambda x: x['total_revenue'] or 0, reverse=True)

        return comparison

    @classmethod
    def export_analytics_report(cls, period_days: int = 30) -> Dict[str, Any]:
        """
        Полный аналитический отчет для экспорта

        Args:
            period_days: Период анализа

        Returns:
            Полный отчет со всеми метриками
        """
        return {
            'generated_at': timezone.now().isoformat(),
            'period_days': period_days,
            'revenue': cls.get_revenue_analytics(period_days),
            'users': cls.get_user_analytics(period_days),
            'models': cls.get_model_comparison(),
            'performance': cls.get_performance_metrics(),
            'model_usage': cls.get_model_usage_stats(period_days=period_days)
        }

    @classmethod
    def track_event(cls,
                   user: TgUser,
                   event_type: str,
                   metadata: Optional[Dict] = None) -> None:
        """
        Отслеживание пользовательских событий

        Args:
            user: Пользователь
            event_type: Тип события
            metadata: Дополнительные данные
        """
        # Здесь можно интегрировать с внешней аналитикой (Amplitude, Mixpanel, etc)
        # Или сохранять в отдельную таблицу событий

        event_data = {
            'user_id': user.chat_id,
            'username': user.username,
            'event_type': event_type,
            'timestamp': timezone.now().isoformat(),
            'metadata': metadata or {}
        }

        # Пример отправки в внешний сервис
        # send_to_analytics_service(event_data)

        # Или логирование
        import logging
        logger = logging.getLogger('analytics')
        logger.info(f"Event: {event_type}", extra=event_data)