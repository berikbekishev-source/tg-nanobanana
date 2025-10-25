from django.db import migrations


TARGET_MODEL_SLUG = "veo3-fast"
OLD_API_NAMES = {"veo-3.1-fast", "veo-3.1-fast@default"}
NEW_API_NAME = "veo-3.1-fast-generate-preview"


def update_veo_api_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    try:
        veo = AIModel.objects.get(slug=TARGET_MODEL_SLUG)
    except AIModel.DoesNotExist:
        return

    if veo.api_model_name in OLD_API_NAMES or not veo.api_model_name:
        veo.api_model_name = NEW_API_NAME
        veo.save(update_fields=["api_model_name", "updated_at"])


def revert_veo_api_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    try:
        veo = AIModel.objects.get(slug=TARGET_MODEL_SLUG)
    except AIModel.DoesNotExist:
        return

    if veo.api_model_name == NEW_API_NAME:
        veo.api_model_name = "veo-3.1-fast"
        veo.save(update_fields=["api_model_name", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0007_update_video_defaults"),
    ]

    operations = [
        migrations.RunPython(update_veo_api_model, revert_veo_api_model),
    ]
