from decimal import Decimal

from django.db import migrations


SLUG = "gemini-2.5-pro"
NAME = "Gemini 2.5 pro"
DISPLAY_NAME = "📲Промт по референсу"
API_MODEL_NAME = "gemini-2.5-pro"
ORDER = 990
BASE_COST = Decimal("0.01")


def _calc_price(pricing_settings, base_cost: Decimal) -> Decimal:
    if not pricing_settings:
        return Decimal("0.00")
    rate = getattr(pricing_settings, "usd_to_token_rate", None)
    markup = getattr(pricing_settings, "markup_multiplier", None)
    if rate is None or markup is None:
        return Decimal("0.00")
    return (base_cost * rate * markup).quantize(Decimal("0.01"))


def forwards(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")

    if AIModel.objects.filter(slug=SLUG).exists():
        return

    pricing_settings = PricingSettings.objects.order_by("id").first()
    price_tokens = _calc_price(pricing_settings, BASE_COST)

    AIModel.objects.create(
        slug=SLUG,
        name=NAME,
        display_name=DISPLAY_NAME,
        type="video",
        provider="gemini",
        description="Генерация промта по референсу через Gemini 2.5 Pro.",
        short_description="Промт по референсу (Gemini 2.5 Pro)",
        price=price_tokens,
        unit_cost_usd=BASE_COST,
        base_cost_usd=BASE_COST,
        cost_unit="generation",
        api_endpoint="",
        api_model_name=API_MODEL_NAME,
        max_prompt_length=4000,
        supports_image_input=True,
        max_input_images=1,
        default_params={},
        allowed_params={},
        max_quantity=1,
        cooldown_seconds=0,
        daily_limit=None,
        is_active=True,
        is_beta=True,
        min_user_level=0,
        order=ORDER,
    )


def backwards(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    AIModel.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0042_update_kling_model"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
