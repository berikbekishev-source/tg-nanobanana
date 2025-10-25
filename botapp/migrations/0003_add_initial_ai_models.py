# Generated manually
from django.db import migrations
from decimal import Decimal


def add_initial_models(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')

    # Модели для генерации изображений
    AIModel.objects.create(
        slug='nano-banana',
        name='Nano Banana',
        display_name='🍌 Nano Banana',
        type='image',
        provider='gemini',
        description='Нашумевшая нейросеть от Google: Gemini Flash 2.5 Banana. Прекрасно понимает контекст и ювелирно меняет объекты на ваших картинках, сохраняя исходное качество.',
        short_description='Быстрая генерация изображений с Gemini',
        price=Decimal('1.50'),
        api_endpoint='https://generativelanguage.googleapis.com/v1beta',
        api_model_name='gemini-2.5-flash-image',
        max_prompt_length=2000,
        supports_image_input=True,
        max_input_images=4,
        default_params={
            'temperature': 0.8,
            'top_p': 0.95,
            'top_k': 40
        },
        allowed_params={
            'temperature': {'min': 0.0, 'max': 1.0},
            'top_p': {'min': 0.0, 'max': 1.0},
            'top_k': {'min': 1, 'max': 100}
        },
        max_quantity=4,
        cooldown_seconds=0,
        daily_limit=None,
        is_active=True,
        is_beta=False,
        min_user_level=0,
        order=1
    )

    AIModel.objects.create(
        slug='imagen-3',
        name='Imagen 3.0',
        display_name='🎨 Imagen 3.0',
        type='image',
        provider='vertex',
        description='Продвинутая модель Google Imagen 3.0 для создания высококачественных изображений с точным следованием промту.',
        short_description='Премиум качество изображений',
        price=Decimal('3.00'),
        api_endpoint='',
        api_model_name='imagen-3.0-generate-001',
        max_prompt_length=1500,
        supports_image_input=False,
        max_input_images=0,
        default_params={
            'aspect_ratio': '1:1',
            'safety_filter': 'block_some',
            'person_generation': 'allowed'
        },
        allowed_params={
            'aspect_ratio': ['1:1', '16:9', '9:16', '4:3', '3:4'],
            'safety_filter': ['block_none', 'block_some', 'block_most'],
            'person_generation': ['allowed', 'disallowed']
        },
        max_quantity=4,
        cooldown_seconds=0,
        daily_limit=100,
        is_active=False,  # Пока не активна
        is_beta=False,
        min_user_level=0,
        order=2
    )

    # Модели для генерации видео
    AIModel.objects.create(
        slug='veo3-fast',
        name='Veo 3.1 Fast',
        display_name='⚡ Veo 3.1 Fast',
        type='video',
        provider='veo',
        description='Передовая модель искусственного интеллекта от Google. Позволяет генерировать видео в качестве 720p и до 8 секунд.',
        short_description='Быстрая генерация видео 720p',
        price=Decimal('19.00'),
        api_endpoint='',
        api_model_name='veo-3.1-fast',
        max_prompt_length=1000,
        supports_image_input=True,
        max_input_images=1,
        default_params={
            'duration': 5,
            'resolution': '720p',
            'fps': 24
        },
        allowed_params={
            'duration': {'min': 2, 'max': 8},
            'resolution': ['720p', '480p'],
            'fps': [24, 30]
        },
        max_quantity=1,
        cooldown_seconds=10,
        daily_limit=20,
        is_active=True,
        is_beta=True,
        min_user_level=0,
        order=10
    )

    AIModel.objects.create(
        slug='veo3-pro',
        name='Veo 3.1 Pro',
        display_name='🎬 Veo 3.1 Pro',
        type='video',
        provider='veo',
        description='Профессиональная версия Veo для создания видео высокого качества 1080p длительностью до 15 секунд.',
        short_description='Премиум видео 1080p до 15 сек',
        price=Decimal('49.00'),
        api_endpoint='',
        api_model_name='veo-3.1-pro',
        max_prompt_length=2000,
        supports_image_input=True,
        max_input_images=3,
        default_params={
            'duration': 10,
            'resolution': '1080p',
            'fps': 30,
            'quality': 'high'
        },
        allowed_params={
            'duration': {'min': 5, 'max': 15},
            'resolution': ['1080p', '720p'],
            'fps': [24, 30, 60],
            'quality': ['standard', 'high', 'ultra']
        },
        max_quantity=1,
        cooldown_seconds=30,
        daily_limit=10,
        is_active=False,  # Пока не активна
        is_beta=True,
        min_user_level=5,  # Требует 5 уровень
        order=11
    )


def add_initial_promocodes(apps, schema_editor):
    Promocode = apps.get_model('botapp', 'Promocode')
    from django.utils import timezone
    from datetime import timedelta

    # Приветственный промокод
    Promocode.objects.create(
        code='WELCOME2025',
        description='Приветственный промокод для новых пользователей',
        is_percentage=False,
        value=Decimal('10.00'),
        min_deposit=Decimal('0.00'),
        max_uses=1000,
        max_uses_per_user=1,
        current_uses=0,
        valid_from=timezone.now(),
        valid_until=timezone.now() + timedelta(days=90),
        is_active=True
    )

    # Промокод на скидку
    Promocode.objects.create(
        code='FIRST50',
        description='Скидка 50% на первое пополнение',
        is_percentage=True,
        value=Decimal('50.00'),
        min_deposit=Decimal('100.00'),
        max_uses=500,
        max_uses_per_user=1,
        current_uses=0,
        valid_from=timezone.now(),
        valid_until=timezone.now() + timedelta(days=30),
        is_active=True
    )


def reverse_func(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    Promocode = apps.get_model('botapp', 'Promocode')
    AIModel.objects.all().delete()
    Promocode.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0002_aimodel_promocode_transaction_userbalance_and_more'),
    ]

    operations = [
        migrations.RunPython(add_initial_models, reverse_func),
        migrations.RunPython(add_initial_promocodes, reverse_func),
    ]