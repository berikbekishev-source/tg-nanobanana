#!/usr/bin/env python
"""
Скрипт для обновления max_input_images для Nano Banana Pro
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nanobanana_codex.settings')
django.setup()

from botapp.models import AIModel

try:
    model = AIModel.objects.get(slug='nano-banana-pro')
    old_value = model.max_input_images
    model.max_input_images = 6
    model.save()
    print(f'✅ Успешно обновлено max_input_images для "{model.display_name}": {old_value} → 6')
except AIModel.DoesNotExist:
    print('❌ Модель с slug="nano-banana-pro" не найдена')
except Exception as e:
    print(f'❌ Ошибка: {str(e)}')
