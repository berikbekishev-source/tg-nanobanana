
from django.db import migrations
from decimal import Decimal

def add_nano_banana_pro(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    
    AIModel.objects.create(
        slug='nano-banana-pro',
        name='Nano Banana Pro',
        display_name='🍌 Nano Banana Pro',
        type='image',
        provider='gemini_vertex',
        description='Улучшенная версия Nano Banana (Gemini 3 Pro). Генерирует и редактирует изображения с повышенной детализацией и пониманием сложных запросов.',
        short_description='Gemini 3 Pro для топовых генераций',
        price=Decimal('2.00'),
        api_model_name='publishers/google/models/gemini-3-pro-image-preview',
        supports_image_input=True,
        max_input_images=4,
        default_params={
            'temperature': 0.8,
            'top_p': 0.95,
            'top_k': 40
        },
        allowed_params={
            'temperature': {'min': 0.0, 'max': 1.0},
            'top_p': {'min': 0.0, 'max': 1.0},
            'top_k': {'min': 1, 'max': 100}
        },
        max_quantity=4,
        is_active=True,
        order=2  # После обычной Nano Banana
    )

def remove_nano_banana_pro(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    AIModel.objects.filter(slug='nano-banana-pro').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0030_boterrorevent'),
    ]

    operations = [
        migrations.RunPython(add_nano_banana_pro, remove_nano_banana_pro),
    ]

