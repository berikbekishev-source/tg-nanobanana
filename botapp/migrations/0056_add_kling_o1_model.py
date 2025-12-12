"""Добавляет модель Kling O1 (Omni) для генерации видео."""
from decimal import Decimal

from django.db import migrations


def add_kling_o1_model(apps, schema_editor):
    """Создаёт модель kling_O1 для генерации видео через Kling Omni API."""
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")
    pricing_settings = PricingSettings.objects.order_by("id").first()

    def calc_price(base_cost: Decimal):
        if not pricing_settings:
            return Decimal("0.00")
        rate = getattr(pricing_settings, "usd_to_token_rate", None)
        markup = getattr(pricing_settings, "markup_multiplier", None)
        if rate and markup:
            return (base_cost * rate * markup).quantize(Decimal("0.01"))
        return Decimal("0.00")

    # Модель kling_O1 (Omni) - поддерживает text2video и image2video с референсами
    if not AIModel.objects.filter(slug="kling_O1").exists():
        base_cost = Decimal("0.10")
        AIModel.objects.create(
            slug="kling_O1",
            name="kling-o1",
            display_name="🐉 Kling O1",
            type="video",
            provider="kling",
            description=(
                "Kling O1 (Omni) — продвинутая модель генерации видео от Kuaishou. "
                "Поддерживает text2video и image2video с до 7 референсными изображениями "
                "или 1 видео + 4 изображения. Используйте @image_1, @video_1 в промте для ссылок на референсы."
            ),
            short_description="Видео · 3-10 сек · text2video/image2video · до 7 референсов",
            price=calc_price(base_cost),
            unit_cost_usd=base_cost,
            base_cost_usd=base_cost,
            cost_unit="second",
            api_endpoint="https://api.useapi.net/v1/kling/videos/omni",
            api_model_name="kling-o1",
            max_prompt_length=1700,
            supports_image_input=True,
            max_input_images=7,
            default_params={
                "aspect_ratio": "16:9",
                "duration": 5,
                "omni_version": "o1",
            },
            allowed_params={
                "aspect_ratio": ["16:9", "9:16", "1:1"],
                "duration": {"options": [3, 4, 5, 6, 7, 8, 9, 10]},
            },
            max_quantity=1,
            cooldown_seconds=0,
            daily_limit=None,
            is_active=True,
            is_beta=False,
            min_user_level=0,
            order=64,
        )


def remove_kling_o1_model(apps, schema_editor):
    """Удаляет модель kling_O1."""
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="kling_O1").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0055_activate_kling_v21_master"),
    ]

    operations = [
        migrations.RunPython(add_kling_o1_model, remove_kling_o1_model),
    ]
