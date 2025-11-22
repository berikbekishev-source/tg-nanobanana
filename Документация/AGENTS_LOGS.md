## [2025-11-22] Staging Deployment: Debug WebApp & Fix All Errors

**Агент:** Agent (Session 9K9rh)
**Ветка:** chore-debug-telegram-send-9K9rh
**PR:** #306
**Коммит:** (Latest HEAD)

### Выполненные действия:
1. Синхронизация с staging (pull origin staging).
2. Реализована диагностика WebApp (showAlert, logs, fallback REST).
3. Исправлен парсинг JSON в `handle_midjourney_webapp_data` (dirty JSON, double encoding).
4. Исправлен атрибут модели: `max_images` -> `max_input_images`.
5. Исправлена сериализация цены: `Decimal` -> `float`.
6. Исправлена проверка баланса:
   - `check_balance` -> `check_can_generate`.
   - Добавлена обработка возвращаемого статуса.

### Результат:
Ожидается автоматический деплой на Staging. Требуется финальная проверка генерации.
