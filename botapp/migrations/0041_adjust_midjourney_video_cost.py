from decimal import Decimal

from django.db import migrations


def _recalc_price(settings, base_cost: Decimal) -> Decimal | None:
    if not settings:
        return None
    rate = getattr(settings, "usd_to_token_rate", None)
    markup = getattr(settings, "markup_multiplier", None)
    if rate is None or markup is None:
        return None
    return (base_cost * rate * markup).quantize(Decimal("0.01"))


def forward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")
    pricing_settings = PricingSettings.objects.order_by("id").first()

    midjourney_video = AIModel.objects.filter(slug="midjourney-video").first()
    if midjourney_video:
        midjourney_video.base_cost_usd = Decimal("0.015")
        midjourney_video.unit_cost_usd = Decimal("0.015")
        new_price = _recalc_price(pricing_settings, midjourney_video.base_cost_usd)
        if new_price is not None:
            midjourney_video.price = new_price
        midjourney_video.save(update_fields=["base_cost_usd", "unit_cost_usd", "price"])


def backward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")
    pricing_settings = PricingSettings.objects.order_by("id").first()

    midjourney_video = AIModel.objects.filter(slug="midjourney-video").first()
    if midjourney_video:
        midjourney_video.base_cost_usd = Decimal("0.05")
        midjourney_video.unit_cost_usd = Decimal("0.05")
        old_price = _recalc_price(pricing_settings, midjourney_video.base_cost_usd)
        if old_price is not None:
            midjourney_video.price = old_price
        midjourney_video.save(update_fields=["base_cost_usd", "unit_cost_usd", "price"])


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0040_update_midjourney_pricing_and_limits"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
