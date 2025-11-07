from django.db import migrations


def drop_style_param(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    for model in AIModel.objects.filter(slug='gpt-image-1'):
        defaults = model.default_params or {}
        defaults.pop('style', None)
        allowed = model.allowed_params or {}
        allowed.pop('style', None)
        model.default_params = defaults
        model.allowed_params = allowed
        model.save(update_fields=['default_params', 'allowed_params'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0018_update_gpt_image_defaults'),
    ]

    operations = [
        migrations.RunPython(drop_style_param, noop),
    ]
