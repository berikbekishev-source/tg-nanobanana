from decimal import Decimal

from django.db import migrations


def add_kling_v21_models(apps, schema_editor):
    """Создаёт модели kling-v2-1, kling-v2-1-pro и kling-v2-1-master."""
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

    # Модель kling-v2-1 (только img2video, поддерживает mode std/pro)
    if not AIModel.objects.filter(slug="kling-v2-1").exists():
        base_cost_std = Decimal("0.04")
        AIModel.objects.create(
            slug="kling-v2-1",
            name="kling-v2-1",
            display_name="🐉 Kling v2-1",
            type="video",
            provider="kling",
            description=(
                "Kling v2-1 — модель генерации видео от Kuaishou. "
                "Поддерживает только image2video с двумя кадрами (начальный и конечный)."
            ),
            short_description="Видео · 5-10 сек · image2video · std/pro",
            price=calc_price(base_cost_std),
            unit_cost_usd=base_cost_std,
            base_cost_usd=base_cost_std,
            cost_unit="second",
            api_endpoint="https://api.useapi.net/v1/kling/videos",
            api_model_name="kling-v2-1",
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
            },
            max_quantity=1,
            cooldown_seconds=0,
            daily_limit=None,
            is_active=True,
            is_beta=False,
            min_user_level=0,
            order=61,
        )

    # Модель kling-v2-1-pro (для расчёта стоимости при mode=pro)
    if not AIModel.objects.filter(slug="kling-v2-1-pro").exists():
        base_cost_pro = Decimal("0.07")
        AIModel.objects.create(
            slug="kling-v2-1-pro",
            name="kling-v2-1-pro",
            display_name="🐉 Kling v2-1 Pro",
            type="video",
            provider="kling",
            description=(
                "Kling v2-1 в режиме Pro — повышенное качество генерации."
            ),
            short_description="Видео Pro · 5-10 сек",
            price=calc_price(base_cost_pro),
            unit_cost_usd=base_cost_pro,
            base_cost_usd=base_cost_pro,
            cost_unit="second",
            api_endpoint="https://api.useapi.net/v1/kling/videos",
            api_model_name="kling-v2-1",
            max_prompt_length=2500,
            supports_image_input=True,
            max_input_images=1,
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
            cooldown_seconds=0,
            daily_limit=None,
            is_active=False,  # Не показываем в меню, используется для расчёта стоимости
            is_beta=False,
            min_user_level=0,
            order=62,
        )

    # Модель kling-v2-1-master (txt2video и img2video, mode не поддерживается)
    if not AIModel.objects.filter(slug="kling-v2-1-master").exists():
        base_cost_master = Decimal("0.16")
        AIModel.objects.create(
            slug="kling-v2-1-master",
            name="kling-v2-1-master",
            display_name="🐉 Kling v2-1 Master",
            type="video",
            provider="kling",
            description=(
                "Kling v2-1 Master — премиум модель генерации видео от Kuaishou. "
                "Поддерживает text2video и image2video. Параметр mode не поддерживается."
            ),
            short_description="Видео · 5-10 сек · text2video/image2video",
            price=calc_price(base_cost_master),
            unit_cost_usd=base_cost_master,
            base_cost_usd=base_cost_master,
            cost_unit="second",
            api_endpoint="https://api.useapi.net/v1/kling/videos",
            api_model_name="kling-v2-1-master",
            max_prompt_length=2500,
            supports_image_input=True,
            max_input_images=1,
            default_params={
                "aspect_ratio": "16:9",
                "duration": 5,
            },
            allowed_params={
                "aspect_ratio": ["16:9", "9:16", "1:1"],
                "duration": {"options": [5, 10]},
            },
            max_quantity=1,
            cooldown_seconds=0,
            daily_limit=None,
            is_active=False,  # Не показываем отдельно, используется через webapp kling-v2-1
            is_beta=False,
            min_user_level=0,
            order=63,
        )


def remove_kling_v21_models(apps, schema_editor):
    """Удаляет модели kling-v2-1."""
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(
        slug__in=["kling-v2-1", "kling-v2-1-pro", "kling-v2-1-master"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0050_add_kling_v26_models"),
    ]

    operations = [
        migrations.RunPython(add_kling_v21_models, remove_kling_v21_models),
    ]
