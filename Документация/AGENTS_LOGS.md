## [2025-11-22] Staging Deployment: Fix Balance Check Method

**Агент:** Agent (Session 9K9rh)
**Ветка:** chore-debug-telegram-send-9K9rh
**PR:** #306 (Auto-created)
**Коммит:** d51b547

### Выполненные действия:
1. Исправлена ошибка `AttributeError: 'BalanceService' object has no attribute 'check_balance'`.
   - Заменен вызов несуществующего метода `check_balance` на корректный статический метод `check_can_generate`.
   - Добавлена корректная обработка результата (возвращает `Tuple[bool, str]`, а не кидает исключение).

### Результат:
Ожидается автоматический деплой на Staging.
Требуется повторная проверка генерации.
