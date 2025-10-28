from datetime import timedelta
from decimal import Decimal

from django.db import migrations
from django.utils import timezone


PROMO_CODE = "AIS2025"
PROMO_DESCRIPTION = "Акционный промокод AIS2025"
PROMO_BONUS = Decimal("1000.00")
PROMO_MIN_DEPOSIT = Decimal("0.00")
PROMO_VALIDITY_DAYS = 365 * 50  # Формально «не ограничен» — задаём горизонт в 50 лет


def create_ais_promocode(apps, schema_editor):
    Promocode = apps.get_model("botapp", "Promocode")

    now = timezone.now()
    promocode, created = Promocode.objects.get_or_create(
        code=PROMO_CODE,
        defaults={
            "description": PROMO_DESCRIPTION,
            "is_percentage": False,
            "value": PROMO_BONUS,
            "min_deposit": PROMO_MIN_DEPOSIT,
            "max_uses": None,
            "max_uses_per_user": 1,
            "current_uses": 0,
            "valid_from": now,
            "valid_until": now + timedelta(days=PROMO_VALIDITY_DAYS),
            "is_active": True,
        },
    )

    if created:
        return

    fields_to_update = []

    if promocode.description != PROMO_DESCRIPTION:
        promocode.description = PROMO_DESCRIPTION
        fields_to_update.append("description")

    if promocode.is_percentage:
        promocode.is_percentage = False
        fields_to_update.append("is_percentage")

    if promocode.value != PROMO_BONUS:
        promocode.value = PROMO_BONUS
        fields_to_update.append("value")

    if promocode.min_deposit != PROMO_MIN_DEPOSIT:
        promocode.min_deposit = PROMO_MIN_DEPOSIT
        fields_to_update.append("min_deposit")

    if promocode.max_uses_per_user != 1:
        promocode.max_uses_per_user = 1
        fields_to_update.append("max_uses_per_user")

    if not promocode.is_active:
        promocode.is_active = True
        fields_to_update.append("is_active")

    if promocode.valid_from > now:
        promocode.valid_from = now
        fields_to_update.append("valid_from")

    validity_threshold = now + timedelta(days=PROMO_VALIDITY_DAYS)
    if promocode.valid_until < validity_threshold:
        promocode.valid_until = validity_threshold
        fields_to_update.append("valid_until")

    if fields_to_update:
        fields_to_update.append("updated_at")
        promocode.save(update_fields=fields_to_update)


def remove_ais_promocode(apps, schema_editor):
    Promocode = apps.get_model("botapp", "Promocode")
    Promocode.objects.filter(code=PROMO_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("botapp", "0011_merge_0007_0010"),
    ]

    operations = [
        migrations.RunPython(create_ais_promocode, remove_ais_promocode),
    ]
