from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid


class TgUser(models.Model):
    """Модель пользователя Telegram"""
    chat_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=255, blank=True, default="")
    first_name = models.CharField(max_length=255, blank=True, default="")
    last_name = models.CharField(max_length=255, blank=True, default="")
    language_code = models.CharField(max_length=10, default="ru")
    is_premium = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram User"
        verbose_name_plural = "Telegram Users"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.username or 'Unknown'} ({self.chat_id})"


class UserBalance(models.Model):
    """Баланс и финансовая информация пользователя"""
    user = models.OneToOneField(TgUser, on_delete=models.CASCADE, related_name='balance')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
                                  validators=[MinValueValidator(Decimal('0.00'))])
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_deposited = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    bonus_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    referral_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    referred_by = models.ForeignKey(TgUser, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='referrals')
    referral_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Balance"
        verbose_name_plural = "User Balances"

    def __str__(self):
        return f"Balance for {self.user.username}: {self.balance}"

    def save(self, *args, **kwargs):
        if not self.referral_code:
            # Генерируем уникальный реферальный код
            self.referral_code = f"REF{str(uuid.uuid4())[:8].upper()}"
        super().save(*args, **kwargs)


class AIModel(models.Model):
    """Каталог доступных AI моделей для генерации"""
    MODEL_TYPES = [
        ('image', 'Image Generation'),
        ('video', 'Video Generation'),
    ]

    PROVIDERS = [
        ('gemini', 'Google Gemini'),
        ('vertex', 'Google Vertex AI'),
        ('veo', 'Google Veo'),
        ('openai', 'OpenAI Sora'),
        ('kling', 'Kling AI'),
        ('midjourney', 'Midjourney (KIE)'),
        ('openai_image', 'OpenAI GPT Image'),
        ('imagen', 'Google Imagen'),
    ]

    slug = models.SlugField(unique=True, db_index=True)
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)  # Отображаемое имя в боте
    type = models.CharField(max_length=10, choices=MODEL_TYPES)
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    description = models.TextField()
    short_description = models.CharField(max_length=255)  # Краткое описание для меню
    class CostUnit(models.TextChoices):
        IMAGE = "image", "Per image"
        SECOND = "second", "Per second"
        GENERATION = "generation", "Per generation"

    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    unit_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Себестоимость генерации (историческое поле)",
    )
    base_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Себестоимость одной единицы (изображение/секунда)",
    )
    cost_unit = models.CharField(
        max_length=16,
        choices=CostUnit.choices,
        default=CostUnit.GENERATION,
        help_text="Базовая единица тарифа для расчёта себестоимости",
    )

    # Технические параметры
    api_endpoint = models.CharField(max_length=255, blank=True)
    api_model_name = models.CharField(max_length=100)  # Имя модели в API
    max_prompt_length = models.IntegerField(default=1000)
    supports_image_input = models.BooleanField(default=False)  # Поддержка входных изображений
    max_input_images = models.IntegerField(default=0)  # Макс. количество входных изображений

    # Параметры генерации
    default_params = models.JSONField(default=dict)  # Параметры по умолчанию
    allowed_params = models.JSONField(default=dict)  # Разрешенные параметры и их диапазоны

    # Ограничения
    max_quantity = models.IntegerField(default=4)  # Макс. количество за раз
    cooldown_seconds = models.IntegerField(default=0)  # Задержка между запросами
    daily_limit = models.IntegerField(null=True, blank=True)  # Дневной лимит на пользователя

    # Управление
    is_active = models.BooleanField(default=True)
    is_beta = models.BooleanField(default=False)  # Бета-версия (доступна не всем)
    min_user_level = models.IntegerField(default=0)  # Минимальный уровень пользователя
    order = models.IntegerField(default=0)  # Порядок отображения в списке

    # Статистика
    total_generations = models.IntegerField(default=0)
    total_errors = models.IntegerField(default=0)
    average_generation_time = models.FloatField(default=0.0)  # В секундах

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Model"
        verbose_name_plural = "AI Models"
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} ({self.type})"

    @property
    def hashtag(self) -> str:
        """Хэштег модели для сообщений (без пробелов и спецсимволов)."""
        return f"#{self.slug.replace('-', '').replace('.', '')}"


class GenRequest(models.Model):
    """Запрос на генерацию контента"""
    GENERATION_TYPES = [
        ('text2image', 'Text to Image'),
        ('image2image', 'Image to Image'),
        ('text2video', 'Text to Video'),
        ('image2video', 'Image to Video'),
    ]

    STATUS_CHOICES = [
        ('queued', 'В очереди'),
        ('processing', 'Обработка'),
        ('done', 'Завершено'),
        ('error', 'Ошибка'),
        ('cancelled', 'Отменено'),
    ]

    # Основные поля
    run_code = models.CharField(max_length=64, db_index=True, unique=True)
    user = models.ForeignKey(TgUser, on_delete=models.CASCADE, related_name='generations', null=True, blank=True)
    chat_id = models.BigIntegerField(db_index=True)  # Для быстрого поиска

    # Параметры генерации
    prompt = models.TextField()
    generation_type = models.CharField(max_length=20, choices=GENERATION_TYPES, default='text2image')
    ai_model = models.ForeignKey(AIModel, on_delete=models.PROTECT, related_name='requests', null=True, blank=True)
    model = models.CharField(max_length=64)  # Оставляем для обратной совместимости

    # Входные данные
    input_images = models.JSONField(default=list, blank=True)  # URL входных изображений для режима Remix
    generation_params = models.JSONField(default=dict, blank=True)  # Дополнительные параметры генерации

    # Результаты
    quantity = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued", db_index=True)
    result_urls = models.JSONField(default=list)  # Публичные URL из Supabase Storage
    error_message = models.TextField(blank=True)

    # Для видео
    parent_request = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_requests",
    )
    duration = models.IntegerField(null=True, blank=True)  # Длительность видео в секундах
    video_resolution = models.CharField(max_length=20, blank=True)  # Разрешение видео
    aspect_ratio = models.CharField(max_length=10, blank=True)
    provider_job_id = models.CharField(max_length=512, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    source_media = models.JSONField(default=dict, blank=True)  # Источник входных данных (file_id и т.д.)

    # Финансы
    cost = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0.0000'))
    transaction = models.ForeignKey('Transaction', null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='generation')

    # Метрики
    processing_time = models.FloatField(null=True, blank=True)  # Время обработки в секундах
    file_sizes = models.JSONField(default=list)  # Размеры файлов результатов

    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Generation Request"
        verbose_name_plural = "Generation Requests"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'status']),
            models.Index(fields=['chat_id', '-created_at']),
        ]

    def __str__(self):
        return f"Request {self.id}: {self.prompt[:50]}... ({self.status})"


class Transaction(models.Model):
    """История транзакций пользователей"""
    TRANSACTION_TYPES = [
        ('deposit', 'Пополнение'),
        ('generation', 'Генерация'),
        ('bonus', 'Бонус'),
        ('referral', 'Реферальный бонус'),
        ('refund', 'Возврат'),
        ('admin', 'Админ операция'),
    ]

    PAYMENT_METHODS = [
        ('yoomoney', 'ЮMoney'),
        ('card', 'Банковская карта'),
        ('crypto_ton', 'TON'),
        ('crypto_usdt', 'USDT'),
        ('bonus', 'Бонусный счет'),
        ('admin', 'Администратор'),
    ]

    # Основные поля
    user = models.ForeignKey(TgUser, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # + приход, - расход
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)

    # Описание
    description = models.TextField()
    description_en = models.TextField(blank=True)  # Английская версия описания

    # Платежная информация
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, null=True, blank=True)
    payment_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)  # ID внешней платежной системы
    payment_data = models.JSONField(default=dict, blank=True)  # Дополнительные данные платежа

    # Связи
    generation_request = models.ForeignKey(GenRequest, null=True, blank=True, on_delete=models.SET_NULL,
                                           related_name='transactions')
    related_transaction = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)  # Для возвратов

    # Статус
    is_completed = models.BooleanField(default=True)
    is_pending = models.BooleanField(default=False)

    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_type_display()} {self.amount} for {self.user.username}"


class UserSettings(models.Model):
    """Настройки пользователя"""
    user = models.OneToOneField(TgUser, on_delete=models.CASCADE, related_name='settings')

    # Уведомления
    notifications_enabled = models.BooleanField(default=True)
    notify_on_completion = models.BooleanField(default=True)
    notify_on_bonus = models.BooleanField(default=True)
    notify_on_news = models.BooleanField(default=True)

    # Язык
    interface_language = models.CharField(max_length=10, default='ru')

    # Настройки генерации
    default_image_quantity = models.IntegerField(default=1)
    default_video_duration = models.IntegerField(default=5)  # секунд
    preferred_image_model = models.ForeignKey(AIModel, null=True, blank=True, on_delete=models.SET_NULL,
                                              related_name='preferred_by_users_image')
    preferred_video_model = models.ForeignKey(AIModel, null=True, blank=True, on_delete=models.SET_NULL,
                                              related_name='preferred_by_users_video')

    # Статистика использования
    total_generations = models.IntegerField(default=0)
    total_images_generated = models.IntegerField(default=0)
    total_videos_generated = models.IntegerField(default=0)
    last_generation_at = models.DateTimeField(null=True, blank=True)
    daily_reward_streak = models.IntegerField(default=0)
    last_daily_reward_at = models.DateTimeField(null=True, blank=True)

    # Уровень и достижения
    user_level = models.IntegerField(default=0)
    experience_points = models.IntegerField(default=0)
    achievements = models.JSONField(default=list)  # Список достижений

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Settings"
        verbose_name_plural = "User Settings"

    def __str__(self):
        return f"Settings for {self.user.username}"


class Promocode(models.Model):
    """Промокоды для пополнения баланса"""
    code = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.TextField()

    # Тип и значение
    is_percentage = models.BooleanField(default=False)  # True - процент, False - фиксированная сумма
    value = models.DecimalField(max_digits=10, decimal_places=2)  # Значение скидки или бонуса
    min_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))  # Мин. сумма пополнения

    # Ограничения
    max_uses = models.IntegerField(null=True, blank=True)  # Общее количество использований
    max_uses_per_user = models.IntegerField(default=1)  # Макс. использований одним пользователем
    current_uses = models.IntegerField(default=0)  # Текущее количество использований
    used_by = models.ManyToManyField(
        TgUser,
        related_name='used_promocodes',
        blank=True,
    )

    # Период действия
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()

    # Статус
    is_active = models.BooleanField(default=True)

    # Статистика
    total_activated = models.IntegerField(default=0)
    total_bonus_given = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Promocode"
        verbose_name_plural = "Promocodes"
        ordering = ['-created_at']

    def __str__(self):
        return f"Promo: {self.code} ({self.value})"


class PricingSettings(models.Model):
    """Глобальные настройки курсов и наценки для расчёта прайса."""

    usd_to_token_rate = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('20.0000'),
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text="Сколько токенов выдаём за 1 доллар США",
    )
    markup_multiplier = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal('2.000'),
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Глобальный коэффициент наценки",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pricing Settings"
        verbose_name_plural = "Pricing Settings"
        db_table = "pricing_settings"

    def __str__(self):
        return f"Курс {self.usd_to_token_rate} токенов за $1 (×{self.markup_multiplier})"


class TokenPackage(models.Model):
    """Пакеты токенов для внешних платёжных каналов (миниапп, Stars, Lava)."""

    code = models.CharField(max_length=100, primary_key=True)
    title = models.CharField(max_length=255)
    credits = models.DecimalField(max_digits=12, decimal_places=2)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    stars_amount = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=100)

    class Meta:
        db_table = 'token_packages'
        managed = False
        ordering = ['sort_order', 'price_usd']

    def __str__(self):
        return f"{self.title} — ${self.price_usd}"
