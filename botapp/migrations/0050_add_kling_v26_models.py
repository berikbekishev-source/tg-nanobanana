from decimal import Decimal

from django.db import migrations


def add_kling_v26_models(apps, schema_editor):
    """Создаёт модели kling-v2-6 и kling-v2-6-pro-with-sound, обновляет эмодзи у kling моделей."""
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")
    pricing_settings = PricingSettings.objects.order_by("id").first()

    # Обновляем эмодзи у существующих kling моделей на 🐉
    AIModel.objects.filter(slug="kling-v2-5-turbo").update(display_name="🐉 Kling v2-5-turbo")
    AIModel.objects.filter(slug="kling-v2-5-turbo-pro").update(display_name="🐉 Kling v2-5-turbo Pro")

    def calc_price(base_cost: Decimal):
        if not pricing_settings:
            return Decimal("0.00")
        rate = getattr(pricing_settings, "usd_to_token_rate", None)
        markup = getattr(pricing_settings, "markup_multiplier", None)
        if rate and markup:
            return (base_cost * rate * markup).quantize(Decimal("0.01"))
        return Decimal("0.00")

    # Модель kling-v2-6 (базовая, без аудио)
    if not AIModel.objects.filter(slug="kling-v2-6").exists():
        base_cost_std = Decimal("0.055")
        AIModel.objects.create(
            slug="kling-v2-6",
            name="kling-v2-6",
            display_name="🐉 Kling v2-6",
            type="video",
            provider="kling",
            description=(
                "Kling v2-6 — новейшая версия генерации видео от Kuaishou. "
                "Поддерживает text2video и image2video с Native Audio."
            ),
            short_description="Видео · 5-10 сек · text2video/image2video · Native Audio",
            price=calc_price(base_cost_std),
            unit_cost_usd=base_cost_std,
            base_cost_usd=base_cost_std,
            cost_unit="second",
            api_endpoint="https://api.useapi.net/v1/kling/videos",
            api_model_name="kling-v2-6",
            max_prompt_length=2500,
            supports_image_input=True,
            max_input_images=1,
            default_params={
                "aspect_ratio": "16:9",
                "duration": 5,
                "mode": "std",
            },
            allowed_params={
                "aspect_ratio": ["16:9", "9:16", "1:1"],
                "duration": {"options": [5, 10]},
                "mode": ["std", "pro"],
                "enable_audio": [True, False],
            },
            max_quantity=1,
            cooldown_seconds=0,
            daily_limit=None,
            is_active=True,
            is_beta=False,
            min_user_level=0,
            order=59,
        )

    # Модель kling-v2-6-pro-with-sound (для расчёта стоимости при enable_audio=true)
    if not AIModel.objects.filter(slug="kling-v2-6-pro-with-sound").exists():
        base_cost_pro = Decimal("0.07")
        AIModel.objects.create(
            slug="kling-v2-6-pro-with-sound",
            name="kling-v2-6-pro-with-sound",
            display_name="🐉 Kling v2-6 Pro + Audio",
            type="video",
            provider="kling",
            description=(
                "Kling v2-6 в режиме Pro с Native Audio — "
                "AI-генерируемый звук синхронизированный с видео."
            ),
            short_description="Видео Pro + Audio · 5-10 сек",
            price=calc_price(base_cost_pro),
            unit_cost_usd=base_cost_pro,
            base_cost_usd=base_cost_pro,
            cost_unit="second",
            api_endpoint="https://api.useapi.net/v1/kling/videos",
            api_model_name="kling-v2-6",
            max_prompt_length=2500,
            supports_image_input=True,
            max_input_images=1,
            default_params={
                "aspect_ratio": "16:9",
                "duration": 5,
                "mode": "pro",
                "enable_audio": True,
            },
            allowed_params={
                "aspect_ratio": ["16:9", "9:16", "1:1"],
                "duration": {"options": [5, 10]},
                "mode": ["pro"],
                "enable_audio": [True],
            },
            max_quantity=1,
            cooldown_seconds=0,
            daily_limit=None,
            is_active=False,  # Не показываем в меню, используется для расчёта стоимости
            is_beta=False,
            min_user_level=0,
            order=60,
        )


def remove_kling_v26_models(apps, schema_editor):
    """Удаляет модели kling-v2-6 и восстанавливает старые эмодзи."""
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug__in=["kling-v2-6", "kling-v2-6-pro-with-sound"]).delete()
    # Восстанавливаем старые эмодзи
    AIModel.objects.filter(slug="kling-v2-5-turbo").update(display_name="🎥 Kling v2-5-turbo")
    AIModel.objects.filter(slug="kling-v2-5-turbo-pro").update(display_name="🎥 Kling v2-5-turbo Pro")


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0049_add_kling_pro_model"),
    ]

    operations = [
        migrations.RunPython(add_kling_v26_models, remove_kling_v26_models),
    ]
