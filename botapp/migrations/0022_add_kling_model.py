from decimal import Decimal

from django.db import migrations


def add_kling_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")

    if AIModel.objects.filter(slug="kling-v1").exists():
        return

    AIModel.objects.create(
        slug="kling-v1",
        name="Kling Video",
        display_name="🎥 Kling (Kuaishou)",
        type="video",
        provider="kling",
        description=(
            "Премиальная модель генерации видео от Kuaishou. Поддерживает режимы text2video и image2video, "
            "работает с длительностью до 30 секунд, умеет синтезировать аудио дорожку и сохраняет стиль "
            "референсных кадров."
        ),
        short_description="Видео до 30 сек в 720p/1080p + режим Remix",
        price=Decimal("69.00"),
        api_endpoint="",
        api_model_name="kling-v1",
        max_prompt_length=2000,
        supports_image_input=True,
        max_input_images=1,
        default_params={
            "duration": 10,
            "resolution": "1080p",
            "aspect_ratio": "16:9",
            "enable_audio": True,
        },
        allowed_params={
            "duration": {"min": 4, "max": 30},
            "resolution": ["720p", "1080p"],
            "aspect_ratio": ["16:9", "9:16", "1:1"],
            "enable_audio": [True, False],
            "fps": {"min": 16, "max": 30},
        },
        max_quantity=1,
        cooldown_seconds=45,
        daily_limit=6,
        is_active=True,
        is_beta=True,
        min_user_level=2,
        order=35,
    )


def remove_kling_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="kling-v1").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0021_enable_gpt_image_inputs"),
    ]

    operations = [
        migrations.RunPython(add_kling_model, remove_kling_model),
    ]
