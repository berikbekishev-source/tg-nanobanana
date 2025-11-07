from django.db import migrations


def enable_gpt_image_inputs(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    AIModel.objects.filter(slug='gpt-image-1').update(
        supports_image_input=True,
        max_input_images=4,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0020_update_gpt_image_quality'),
    ]

    operations = [
        migrations.RunPython(enable_gpt_image_inputs, noop),
    ]
