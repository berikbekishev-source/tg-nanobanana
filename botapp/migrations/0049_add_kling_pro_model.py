from decimal import Decimal

from django.db import migrations


def add_kling_pro_model(apps, schema_editor):
    """Создаёт модель kling-v2-5-turbo-pro для режима Pro."""
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")

    # Проверяем, не существует ли уже модель
    if AIModel.objects.filter(slug="kling-v2-5-turbo-pro").exists():
        return

    # Получаем базовую модель для копирования настроек
    base_model = AIModel.objects.filter(slug="kling-v2-5-turbo").first()
    if not base_model:
        # Если базовой модели нет, создаём с дефолтными параметрами
        base_model = None

    # Рассчитываем price из base_cost_usd
    pricing_settings = PricingSettings.objects.order_by("id").first()
    base_cost = Decimal("0.07")  # Pro стоит $0.07/секунда
    price = None
    if pricing_settings:
        rate = getattr(pricing_settings, "usd_to_token_rate", None)
        markup = getattr(pricing_settings, "markup_multiplier", None)
        if rate and markup:
            price = (base_cost * rate * markup).quantize(Decimal("0.01"))

    AIModel.objects.create(
        slug="kling-v2-5-turbo-pro",
        name="kling-v2-5-turbo-pro",
        display_name="🎥 Kling v2-5-turbo Pro",
        type="video",
        provider="kling",
        description=(
            "Kling v2-5-turbo в режиме Pro — повышенное качество генерации. "
            "Поддерживает text2video и image2video с начальным/конечным кадрами."
        ),
        short_description="Видео Pro · 5-10 сек · text2video/image2video",
        price=price or Decimal("0.00"),
        unit_cost_usd=base_cost,
        base_cost_usd=base_cost,
        cost_unit="second",
        api_endpoint=base_model.api_endpoint if base_model else "https://api.useapi.net/v1/kling/videos",
        api_model_name="kling-v2-5",
        max_prompt_length=base_model.max_prompt_length if base_model else 2500,
        supports_image_input=True,
        max_input_images=2,  # Начальный + конечный кадр
        default_params={
            "aspect_ratio": "16:9",
            "duration": 5,
            "mode": "pro",
        },
        allowed_params={
            "aspect_ratio": ["16:9", "9:16", "1:1"],
            "duration": {"options": [5, 10]},
            "mode": ["pro"],
        },
        max_quantity=1,
        cooldown_seconds=base_model.cooldown_seconds if base_model else 0,
        daily_limit=base_model.daily_limit if base_model else None,
        is_active=False,  # Не показываем в меню, используется только для расчёта стоимости
        is_beta=False,
        min_user_level=0,
        order=base_model.order + 1 if base_model else 61,
    )


def remove_kling_pro_model(apps, schema_editor):
    """Удаляет модель kling-v2-5-turbo-pro."""
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="kling-v2-5-turbo-pro").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0048_fix_runway_aleph_cost_unit"),
    ]

    operations = [
        migrations.RunPython(add_kling_pro_model, remove_kling_pro_model),
    ]
