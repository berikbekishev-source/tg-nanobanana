from django.db import migrations


def forward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="midjourney-v6").update(
        display_name="🎨 Midjourney",
        description="Midjourney. Поддерживает text2image и image2image, а также пресеты качества/аспекта.",
        short_description="Midjourney",
    )


def backward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug="midjourney-v6").update(
        display_name="🎨 Midjourney (KIE.AI)",
        description="Midjourney через KIE.AI. Поддерживает text2image и image2image, а также пресеты качества/аспекта.",
        short_description="Midjourney через KIE",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0034_update_nano_banana_pro_pricing"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
