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

    midjourney = AIModel.objects.filter(slug="midjourney-v6").first()
    if midjourney:
        midjourney.slug = "midjourney-v7-fast"
        midjourney.base_cost_usd = Decimal("0.04")
        midjourney.unit_cost_usd = Decimal("0.04")
        new_price = _recalc_price(pricing_settings, midjourney.base_cost_usd)
        if new_price is not None:
            midjourney.price = new_price
        midjourney.save(update_fields=["slug", "base_cost_usd", "unit_cost_usd", "price"])

    midjourney_video = AIModel.objects.filter(slug="midjourney-video").first()
    if midjourney_video:
        defaults = midjourney_video.default_params or {}
        defaults["duration"] = 5
        midjourney_video.default_params = defaults
        midjourney_video.base_cost_usd = Decimal("0.05")
        midjourney_video.unit_cost_usd = Decimal("0.05")
        new_price = _recalc_price(pricing_settings, midjourney_video.base_cost_usd)
        if new_price is not None:
            midjourney_video.price = new_price
        midjourney_video.save(update_fields=["default_params", "base_cost_usd", "unit_cost_usd", "price"])

    AIModel.objects.all().update(daily_limit=None, max_prompt_length=4000)


def backward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")
    pricing_settings = PricingSettings.objects.order_by("id").first()

    midjourney = AIModel.objects.filter(slug="midjourney-v7-fast").first()
    if midjourney:
        midjourney.slug = "midjourney-v6"
        midjourney.base_cost_usd = Decimal("0.015")
        midjourney.unit_cost_usd = Decimal("0.015")
        old_price = _recalc_price(pricing_settings, midjourney.base_cost_usd)
        if old_price is not None:
            midjourney.price = old_price
        midjourney.save(update_fields=["slug", "base_cost_usd", "unit_cost_usd", "price"])

    midjourney_video = AIModel.objects.filter(slug="midjourney-video").first()
    if midjourney_video:
        defaults = midjourney_video.default_params or {}
        defaults["duration"] = 10
        midjourney_video.default_params = defaults
        midjourney_video.base_cost_usd = Decimal("0.05")
        midjourney_video.unit_cost_usd = Decimal("0.05")
        old_price = _recalc_price(pricing_settings, midjourney_video.base_cost_usd)
        if old_price is not None:
            midjourney_video.price = old_price
        midjourney_video.save(update_fields=["default_params", "base_cost_usd", "unit_cost_usd", "price"])

    # Вернём ежедневные лимиты к "без ограничений" и снизим лимит промта
    AIModel.objects.all().update(daily_limit=None, max_prompt_length=2000)


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0039_increase_video_prompt_limits"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
