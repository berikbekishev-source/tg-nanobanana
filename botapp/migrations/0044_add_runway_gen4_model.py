from decimal import Decimal

from django.db import migrations


def add_runway_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")

    if AIModel.objects.filter(slug="runway_gen4").exists():
        return

    AIModel.objects.create(
        slug="runway_gen4",
        name="Runway Gen 4",
        display_name="🎞️ Runway Gen-4",
        type="video",
        provider="useapi",
        description=(
            "Runway Gen-4 через useapi: генерирует видео из изображения по текстовому промту. "
            "Поддерживает длительность 5 или 10 секунд, аспекты 16:9/9:16/1:1/3:4/4:3, разрешения 720p/1080p."
        ),
        short_description="Image → Video 5/10 c, 16:9/9:16/1:1/3:4/4:3, 720p/1080p",
        price=Decimal("0.00"),
        unit_cost_usd=Decimal("0.0500"),
        base_cost_usd=Decimal("0.0500"),
        cost_unit="second",
        api_endpoint="",
        api_model_name="runway-gen4",
        max_prompt_length=4000,
        supports_image_input=True,
        max_input_images=1,
        default_params={
            "duration": 5,
            "seconds": 5,
            "aspect_ratio": "16:9",
            "resolution": "720p",
        },
        allowed_params={
            "duration": {"options": [5, 10]},
            "aspect_ratio": ["16:9", "9:16", "1:1", "3:4", "4:3"],
            "resolution": ["720p", "1080p"],
        },
        max_quantity=1,
        cooldown_seconds=0,
        daily_limit=None,
        is_active=True,
        is_beta=False,
        min_user_level=0,
        order=75,
    )


def remove_runway_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="runway_gen4").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0043_add_reference_prompt_model"),
    ]

    operations = [
        migrations.RunPython(add_runway_model, remove_runway_model),
    ]
