
from django.db import migrations

def update_max_input_images(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')

    # Обновляем max_input_images для Nano Banana Pro с 4 до 6
    # Gemini 3 Pro поддерживает до 6 входных изображений
    AIModel.objects.filter(slug='nano-banana-pro').update(max_input_images=6)

def revert_max_input_images(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    AIModel.objects.filter(slug='nano-banana-pro').update(max_input_images=4)

class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0031_add_nano_banana_pro'),
    ]

    operations = [
        migrations.RunPython(update_max_input_images, revert_max_input_images),
    ]
