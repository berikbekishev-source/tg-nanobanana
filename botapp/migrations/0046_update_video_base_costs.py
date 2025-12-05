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

    updates = {
        "sora2": Decimal("0.0200"),
        "veo3-fast": Decimal("0.0500"),
        "runway_aleph": Decimal("0.5000"),
        "runway_gen4": Decimal("0.0200"),
        "midjourney-video": Decimal("0.0150"),
    }

    for slug, cost in updates.items():
        model = AIModel.objects.filter(slug=slug).first()
        if not model:
            continue

        model.base_cost_usd = cost
        model.unit_cost_usd = cost

        new_price = _recalc_price(pricing_settings, cost)
        update_fields = ["base_cost_usd", "unit_cost_usd"]
        if new_price is not None:
            model.price = new_price
            update_fields.append("price")

        model.save(update_fields=update_fields)


def backward(apps, schema_editor):
    AIModel = apps.get_model("botapp", "AIModel")
    PricingSettings = apps.get_model("botapp", "PricingSettings")
    pricing_settings = PricingSettings.objects.order_by("id").first()

    previous_costs = {
        "sora2": Decimal("0.1000"),
        "veo3-fast": Decimal("0.1500"),
        "runway_aleph": Decimal("0.0500"),
        "runway_gen4": Decimal("0.0500"),
        "midjourney-video": Decimal("0.0150"),
    }

    for slug, cost in previous_costs.items():
        model = AIModel.objects.filter(slug=slug).first()
        if not model:
            continue

        model.base_cost_usd = cost
        model.unit_cost_usd = cost

        price = _recalc_price(pricing_settings, cost)
        update_fields = ["base_cost_usd", "unit_cost_usd"]
        if price is not None:
            model.price = price
            update_fields.append("price")

        model.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0045_add_runway_aleph_model"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
