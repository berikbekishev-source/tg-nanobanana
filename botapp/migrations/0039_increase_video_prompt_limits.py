from django.db import migrations


def increase_video_prompt_limits(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(type="video").update(max_prompt_length=4000)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0038_add_midjourney_video_model"),
    ]

    operations = [
        migrations.RunPython(increase_video_prompt_limits, noop),
    ]
