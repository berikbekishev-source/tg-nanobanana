from django.db import migrations


def update_video_defaults(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    try:
        veo_fast = AIModel.objects.get(slug='veo3-fast')
    except AIModel.DoesNotExist:
        return

    params = veo_fast.default_params or {}
    params.update({
        'duration': 8,
        'resolution': '720p',
        'aspect_ratio': '9:16',
        'fps': 24,
    })
    veo_fast.default_params = params
    veo_fast.description = (
        'Передовая модель искусственного интеллекта от Google. Позволяет генерировать видео '
        'в качестве 720p и до 8 секунд.'
    )
    veo_fast.short_description = 'Быстрая генерация вертикальных видео 720p'
    veo_fast.save(update_fields=['default_params', 'description', 'short_description', 'updated_at'])


def reverse_func(apps, schema_editor):
    # Откатывать не требуется
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0006_genrequest_video_fields'),
    ]

    operations = [
        migrations.RunPython(update_video_defaults, reverse_func),
    ]

