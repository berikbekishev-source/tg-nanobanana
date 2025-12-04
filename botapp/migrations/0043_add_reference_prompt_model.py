from decimal import Decimal

from django.db import migrations


REFERENCE_MODEL_SLUG = "gemini-2.5-pro"
DEFAULT_BASE_COST = Decimal("0.01")
DEFAULT_RATE = Decimal("20.0000")
DEFAULT_MARKUP = Decimal("2.000")


def create_reference_prompt_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")

    if AIModel.objects.filter(slug=REFERENCE_MODEL_SLUG).exists():
        return

    pricing = PricingSettings.objects.order_by("id").first()
    usd_to_token = pricing.usd_to_token_rate if pricing else DEFAULT_RATE
    markup = pricing.markup_multiplier if pricing else DEFAULT_MARKUP
    price_tokens = (DEFAULT_BASE_COST * usd_to_token * markup).quantize(Decimal("0.01"))

    AIModel.objects.create(
        slug=REFERENCE_MODEL_SLUG,
        name="Gemini 2.5 pro",
        display_name="📲Промт по референсу",
        type="video",
        provider="gemini",
        description="Генерация промта по референсу для видео.",
        short_description="Промт по референсу",
        price=price_tokens,
        unit_cost_usd=DEFAULT_BASE_COST,
        base_cost_usd=DEFAULT_BASE_COST,
        cost_unit="generation",
        api_endpoint="https://generativelanguage.googleapis.com/v1beta",
        api_model_name="gemini-2.5-pro",
        max_prompt_length=4000,
        supports_image_input=True,
        max_input_images=10,
        default_params={},
        allowed_params={},
        max_quantity=1,
        cooldown_seconds=0,
        daily_limit=None,
        is_active=False,
        is_beta=True,
        min_user_level=0,
        order=990,
    )


def delete_reference_prompt_model(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug=REFERENCE_MODEL_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0042_update_kling_model"),
    ]

    operations = [
        migrations.RunPython(create_reference_prompt_model, delete_reference_prompt_model),
    ]
