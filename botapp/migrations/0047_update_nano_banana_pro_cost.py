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

    model = AIModel.objects.filter(slug="nano-banana-pro").first()
    if not model:
        return

    pricing_settings = PricingSettings.objects.order_by("id").first()
    cost = Decimal("0.10")

    model.base_cost_usd = cost
    model.unit_cost_usd = cost

    update_fields = ["base_cost_usd", "unit_cost_usd"]
    new_price = _recalc_price(pricing_settings, cost)
    if new_price is not None:
        model.price = new_price
        update_fields.append("price")

    model.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("botapp", "0046_update_video_base_costs"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
