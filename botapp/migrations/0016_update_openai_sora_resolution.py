from django.db import migrations


def update_sora_resolution(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    try:
        model = AIModel.objects.get(slug="sora2")
    except AIModel.DoesNotExist:
        return

    default_params = model.default_params or {}
    allowed_params = model.allowed_params or {}

    default_params["resolution"] = "720p"
    default_params["aspect_ratio"] = "9:16"
    allowed_params["resolution"] = ["720p"]
    allowed_params["aspect_ratio"] = ["9:16", "16:9"]

    model.default_params = default_params
    model.allowed_params = allowed_params
    model.save(update_fields=["default_params", "allowed_params"])


def revert_sora_resolution(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    try:
        model = AIModel.objects.get(slug="sora2")
    except AIModel.DoesNotExist:
        return

    default_params = model.default_params or {}
    allowed_params = model.allowed_params or {}

    default_params["resolution"] = "1080p"
    default_params["aspect_ratio"] = "16:9"
    allowed_params["resolution"] = ["720p", "1080p"]
    allowed_params["aspect_ratio"] = ["16:9", "9:16", "1:1"]

    model.default_params = default_params
    model.allowed_params = allowed_params
    model.save(update_fields=["default_params", "allowed_params"])


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0015_update_openai_sora_params"),
    ]

    operations = [
        migrations.RunPython(update_sora_resolution, revert_sora_resolution),
    ]
