from django.db import migrations


def update_defaults(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    AIModel.objects.filter(slug='gpt-image-1').update(
        default_params={
            'size': '1024x1024',
            'quality': 'standard',
            'style': 'natural'
        },
        allowed_params={
            'size': ['512x512', '768x1024', '1024x768', '1024x1024', '1024x1792', '1792x1024'],
            'quality': ['standard', 'high'],
            'style': ['natural', 'vivid'],
            'background': ['transparent'],
        },
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0017_add_openai_gpt_image_model'),
    ]

    operations = [
        migrations.RunPython(update_defaults, noop),
    ]
