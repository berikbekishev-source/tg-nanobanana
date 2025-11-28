from decimal import Decimal

from django.db import migrations


def add_midjourney_video_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")

    if AIModel.objects.filter(slug="midjourney-video").exists():
        return

    AIModel.objects.create(
        slug="midjourney-video",
        name="Midjourney Video",
        display_name="🎬 Midjourney video",
        type="video",
        provider="midjourney",
        description=(
            "Генерация видео из одного изображения через Midjourney (KIE.AI). "
            "Поддерживает только режим img2video, длина ролика ~10 секунд, доступно задание aspect ratio и версии модели."
        ),
        short_description="Видео ~10 сек по референсному кадру (img2video)",
        price=Decimal("0.00"),
        unit_cost_usd=Decimal("0.0500"),
        base_cost_usd=Decimal("0.0500"),
        cost_unit="second",
        api_endpoint="",
        api_model_name="midjourney/video",
        max_prompt_length=2000,
        supports_image_input=True,
        max_input_images=1,
        default_params={
            "duration": 10,
            "aspect_ratio": "16:9",
            "version": "7",
        },
        allowed_params={
            "aspect_ratio": ["16:9", "9:16", "1:1", "2:1", "1:2", "4:3", "3:4"],
            "version": ["7", "6.1", "6", "5.2", "5.1", "niji6"],
            "duration": {"min": 8, "max": 12},
        },
        max_quantity=1,
        cooldown_seconds=45,
        daily_limit=8,
        is_active=True,
        is_beta=True,
        min_user_level=0,
        order=36,
    )


def remove_midjourney_video_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="midjourney-video").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0037_update_nano_banana_models"),
    ]

    operations = [
        migrations.RunPython(add_midjourney_video_model, remove_midjourney_video_model),
    ]
