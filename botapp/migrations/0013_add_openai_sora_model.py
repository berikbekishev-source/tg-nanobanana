from decimal import Decimal

from django.db import migrations


def add_sora_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")

    if AIModel.objects.filter(slug="sora2").exists():
        return

    AIModel.objects.create(
        slug="sora2",
        name="OpenAI Sora 2",
        display_name="🎥 Sora 2 (OpenAI)",
        type="video",
        provider="openai",
        description=(
            "Флагманская модель генерации видео от OpenAI. Поддерживает текстовые и визуальные подсказки, "
            "создаёт кинематографические ролики с высокой детализацией до 60 секунд."
        ),
        short_description="Кинематографические ролики до 60 сек",
        price=Decimal("79.00"),
        api_endpoint="",
        api_model_name="sora-2",
        max_prompt_length=3000,
        supports_image_input=True,
        max_input_images=1,
        default_params={
            "duration": 16,
            "resolution": "1080p",
            "aspect_ratio": "16:9",
        },
        allowed_params={
            "duration": {"min": 2, "max": 60},
            "resolution": ["720p", "1080p"],
            "aspect_ratio": ["16:9", "9:16", "1:1"],
        },
        max_quantity=1,
        cooldown_seconds=45,
        daily_limit=5,
        is_active=True,
        is_beta=True,
        min_user_level=2,
        order=30,
    )


def remove_sora_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="sora2").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0012_create_ais2025_promocode"),
    ]

    operations = [
        migrations.RunPython(add_sora_model, remove_sora_model),
    ]
