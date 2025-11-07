from django.db import migrations


def switch_nano_to_gemini_vertex(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    AIModel.objects.filter(slug='nano-banana').update(
        provider='gemini_vertex',
        api_model_name='publishers/google/models/gemini-2.5-flash-image-preview',
        supports_image_input=True,
        max_input_images=4,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0024_remove_model_levels'),
    ]

    operations = [
        migrations.RunPython(switch_nano_to_gemini_vertex, noop),
    ]
