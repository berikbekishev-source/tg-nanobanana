from django.db import migrations


def update_sora_params(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    try:
        model = AIModel.objects.get(slug="sora2")
    except AIModel.DoesNotExist:
        return

    default_params = model.default_params or {}
    allowed_params = model.allowed_params or {}

    default_params["duration"] = 8
    allowed_params["duration"] = [4, 8, 12]

    model.default_params = default_params
    model.allowed_params = allowed_params
    model.save(update_fields=["default_params", "allowed_params"])


def revert_sora_params(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    try:
        model = AIModel.objects.get(slug="sora2")
    except AIModel.DoesNotExist:
        return

    default_params = model.default_params or {}
    allowed_params = model.allowed_params or {}

    default_params["duration"] = 16
    allowed_params["duration"] = {"min": 2, "max": 60}

    model.default_params = default_params
    model.allowed_params = allowed_params
    model.save(update_fields=["default_params", "allowed_params"])


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0013_add_openai_sora_model"),
    ]

    operations = [
        migrations.RunPython(update_sora_params, revert_sora_params),
    ]
