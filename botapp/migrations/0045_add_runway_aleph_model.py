from decimal import Decimal

from django.db import migrations


def add_runway_aleph_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")

    if AIModel.objects.filter(slug="runway_aleph").exists():
        return

    AIModel.objects.create(
        slug="runway_aleph",
        name="Runway Aleph",
        display_name="🎞️ Runway Aleph",
        type="video",
        provider="useapi",
        description=(
            "Runway Gen-4 Aleph (video-to-video): преобразование исходного видео по текстовому промту. "
            "Поддерживает MP4/WEBM/MOV до 10 МБ; аспекты 16:9, 9:16, 1:1, 3:4, 4:3, 21:9."
        ),
        short_description="Видео → Видео · 10 МБ · 16:9/9:16/1:1/3:4/4:3/21:9",
        price=Decimal("0.00"),
        unit_cost_usd=Decimal("0.0500"),
        base_cost_usd=Decimal("0.0500"),
        cost_unit="generation",
        api_endpoint="https://api.useapi.net/v1/runwayml/gen4/video",
        api_model_name="runway-gen4-aleph",
        max_prompt_length=4000,
        supports_image_input=True,
        max_input_images=1,
        default_params={
            "aspect_ratio": "16:9",
            "duration": 5,
        },
        allowed_params={
            "aspect_ratio": ["16:9", "9:16", "1:1", "3:4", "4:3", "21:9"],
            "duration": {"options": [5]},
        },
        max_quantity=1,
        cooldown_seconds=0,
        daily_limit=None,
        is_active=True,
        is_beta=True,
        min_user_level=0,
        order=76,
    )


def remove_runway_aleph_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="runway_aleph").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0044_add_runway_gen4_model"),
    ]

    operations = [
        migrations.RunPython(add_runway_aleph_model, remove_runway_aleph_model),
    ]
