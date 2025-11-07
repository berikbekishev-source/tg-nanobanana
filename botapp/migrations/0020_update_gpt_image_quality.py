from django.db import migrations


def update_gpt_image_defaults(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    for model in AIModel.objects.filter(slug='gpt-image-1'):
        defaults = model.default_params or {}
        defaults['size'] = defaults.get('size') or '1024x1024'
        defaults['quality'] = 'auto'
        if defaults.get('background') not in (None, 'transparent'):
            defaults.pop('background', None)
        allowed = model.allowed_params or {}
        allowed['size'] = ['512x512', '768x1024', '1024x768', '1024x1024', '1024x1536', '1536x1024', 'auto']
        allowed['quality'] = ['low', 'medium', 'high', 'auto']
        allowed['background'] = ['transparent']
        allowed['format'] = ['png', 'jpeg', 'webp']
        allowed['output_compression'] = {'min': 0, 'max': 100}
        model.default_params = defaults
        model.allowed_params = allowed
        model.save(update_fields=['default_params', 'allowed_params'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0019_remove_gpt_image_style'),
    ]

    operations = [
        migrations.RunPython(update_gpt_image_defaults, noop),
    ]
