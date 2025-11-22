## [2025-11-22] Staging Deployment: Fix Decimal Serialization

**Агент:** Agent (Session 9K9rh)
**Ветка:** chore-debug-telegram-send-9K9rh
**PR:** #305 (Auto-created)
**Коммит:** e286c10

### Выполненные действия:
1. Исправлена ошибка `Object of type Decimal is not JSON serializable`.
   - В `handle_midjourney_webapp_data` добавлено приведение `float(cost)` перед сохранением в `state`.
   - Это необходимо, так как Redis/JSON не поддерживают тип Decimal.

### Результат:
Ожидается автоматический мердж PR #305 и деплой на Staging.
Требуется повторная проверка генерации.
