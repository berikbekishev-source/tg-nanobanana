from django.db import migrations


def set_min_level(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="sora2").update(min_user_level=0)


def revert_min_level(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="sora2").update(min_user_level=2)


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0013_add_openai_sora_model"),
    ]

    operations = [
        migrations.RunPython(set_min_level, revert_min_level),
    ]
