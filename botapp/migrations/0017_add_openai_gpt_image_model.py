from decimal import Decimal

from django.db import migrations, models


def add_gpt_image_model(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    AIModel.objects.update_or_create(
        slug='gpt-image-1',
        defaults=dict(
            name='GPT Image 1',
            display_name='🖼️ GPT Image 1',
            type='image',
            provider='openai_image',
            description='Модель OpenAI GPT Image 1 для генерации иллюстраций с высокой детализацией и возможностью прозрачного фона.',
            short_description='OpenAI GPT Image с высоким качеством',
            price=Decimal('2.50'),
            api_endpoint='https://api.openai.com/v1/images',
            api_model_name='gpt-image-1',
            max_prompt_length=1500,
            supports_image_input=False,
            max_input_images=0,
            default_params={
                'size': '1024x1024',
                'quality': 'high',
                'style': 'vivid',
                'background': 'transparent'
            },
            allowed_params={
                'size': ['512x512', '768x1024', '1024x768', '1024x1024', '1024x1792', '1792x1024'],
                'quality': ['standard', 'high'],
                'style': ['natural', 'vivid'],
            },
            max_quantity=4,
            cooldown_seconds=0,
            daily_limit=None,
            is_active=True,
            is_beta=False,
            min_user_level=0,
            order=3,
        )
    )


def remove_gpt_image_model(apps, schema_editor):
    AIModel = apps.get_model('botapp', 'AIModel')
    AIModel.objects.filter(slug='gpt-image-1').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0016_update_openai_sora_resolution'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aimodel',
            name='provider',
            field=models.CharField(
                choices=[
                    ('gemini', 'Google Gemini'),
                    ('vertex', 'Google Vertex AI'),
                    ('veo', 'Google Veo'),
                    ('openai', 'OpenAI Sora'),
                    ('openai_image', 'OpenAI GPT Image'),
                    ('imagen', 'Google Imagen'),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(add_gpt_image_model, remove_gpt_image_model),
    ]
