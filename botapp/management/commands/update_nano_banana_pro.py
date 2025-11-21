"""
Django management команда для обновления max_input_images для Nano Banana Pro
"""
from django.core.management.base import BaseCommand
from botapp.models import AIModel


class Command(BaseCommand):
    help = 'Обновляет max_input_images для Nano Banana Pro с 4 до 6'

    def handle(self, *args, **options):
        try:
            model = AIModel.objects.get(slug='nano-banana-pro')
            old_value = model.max_input_images
            model.max_input_images = 6
            model.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Успешно обновлено max_input_images для "{model.display_name}": {old_value} → 6'
                )
            )
        except AIModel.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('❌ Модель с slug="nano-banana-pro" не найдена')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Ошибка: {str(e)}')
            )
