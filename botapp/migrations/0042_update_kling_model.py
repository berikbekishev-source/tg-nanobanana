from django.db import migrations


OLD_SLUG = "kling-v1"
NEW_SLUG = "kling-v2-5-turbo"
NEW_NAME = "kling-v2-5-turbo"
NEW_DISPLAY_NAME = "🎥 Kling v2-5-turbo"
OLD_DISPLAY_NAME = "🎥 Kling (Kuaishou)"
OLD_NAME = "Kling Video"


def forwards(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")

    old_model = AIModel.objects.filter(slug=OLD_SLUG).first()
    new_model = AIModel.objects.filter(slug=NEW_SLUG).first()

    if new_model:
        updated_fields = []
        if new_model.name != NEW_NAME:
            new_model.name = NEW_NAME
            updated_fields.append("name")
        if new_model.display_name != NEW_DISPLAY_NAME:
            new_model.display_name = NEW_DISPLAY_NAME
            updated_fields.append("display_name")
        if getattr(new_model, "api_model_name", None) != NEW_SLUG:
            new_model.api_model_name = NEW_SLUG
            updated_fields.append("api_model_name")
        if updated_fields:
            updated_fields.append("updated_at")
            new_model.save(update_fields=updated_fields)

        if old_model and old_model.pk != new_model.pk and old_model.is_active:
            old_model.is_active = False
            old_model.save(update_fields=["is_active", "updated_at"])
        return

    if not old_model:
        return

    updated_fields = []
    if old_model.slug != NEW_SLUG:
        old_model.slug = NEW_SLUG
        updated_fields.append("slug")
    if old_model.name != NEW_NAME:
        old_model.name = NEW_NAME
        updated_fields.append("name")
    if old_model.display_name != NEW_DISPLAY_NAME:
        old_model.display_name = NEW_DISPLAY_NAME
        updated_fields.append("display_name")
    if getattr(old_model, "api_model_name", None) != NEW_SLUG:
        old_model.api_model_name = NEW_SLUG
        updated_fields.append("api_model_name")
    if updated_fields:
        updated_fields.append("updated_at")
        old_model.save(update_fields=updated_fields)


def backwards(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    model = AIModel.objects.filter(slug=NEW_SLUG).first()
    if not model:
        return

    updated_fields = []
    if model.slug != OLD_SLUG:
        model.slug = OLD_SLUG
        updated_fields.append("slug")
    if model.name != OLD_NAME:
        model.name = OLD_NAME
        updated_fields.append("name")
    if model.display_name != OLD_DISPLAY_NAME:
        model.display_name = OLD_DISPLAY_NAME
        updated_fields.append("display_name")
    if getattr(model, "api_model_name", None) != OLD_SLUG:
        model.api_model_name = OLD_SLUG
        updated_fields.append("api_model_name")
    if not model.is_active:
        model.is_active = True
        updated_fields.append("is_active")
    if updated_fields:
        updated_fields.append("updated_at")
        model.save(update_fields=updated_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0041_adjust_midjourney_video_cost"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
