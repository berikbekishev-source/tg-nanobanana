"""Django signals for botapp."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from botapp.business.pricing import invalidate_pricing_settings_cache
from botapp.models import PricingSettings


@receiver(post_save, sender=PricingSettings)
def refresh_pricing_cache(sender, **kwargs):
    invalidate_pricing_settings_cache()
