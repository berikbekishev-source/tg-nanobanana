from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from botapp.models import BotErrorEvent


class Command(BaseCommand):
    help = "Удаляет старые записи об ошибках бота."

    def handle(self, *args, **options):
        retention_days = getattr(settings, "ERROR_LOG_RETENTION_DAYS", 30)
        cutoff = timezone.now() - timedelta(days=retention_days)
        qs = BotErrorEvent.objects.filter(occurred_at__lt=cutoff)
        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Удалено {deleted} записей BotErrorEvent (старше {retention_days} дней)."
            )
        )
