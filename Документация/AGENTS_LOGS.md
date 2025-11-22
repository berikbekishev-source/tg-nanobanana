## [2025-11-22] Staging Deployment: Cleanup

**Агент:** Agent (Session 9K9rh)
**Ветка:** chore-debug-telegram-send-9K9rh
**PR:** #308 (Auto-created)
**Коммит:** c73ca05

### Выполненные действия:
1. Удалены временные `print(...)` вызовы из `botapp/api.py` и `botapp/handlers/image_generation.py`.
   - Логирование через `logging.info/error` сохранено.
   - Сырое тело запроса больше не дублируется в stdout.

### Итог:
Код готов к релизу в Production.
