## [2025-11-22] Staging Deployment: Debug WebApp & Fix AIModel Error

**Агент:** Agent (Session 9K9rh)
**Ветка:** chore-debug-telegram-send-9K9rh
**PR:** (Pending creation/merge by user)
**Коммит:** (Latest HEAD)

### Выполненные действия:
1. Синхронизация с staging (pull origin staging).
2. Реализована диагностика WebApp:
   - Добавлен `tg.showAlert` и логирование в `webapps/midjourney/index.html`.
   - Реализован fallback REST endpoint для отправки данных, если `tg.sendData` не срабатывает.
3. Исправлена критическая ошибка парсинга JSON в `botapp/handlers/image_generation.py`:
   - Добавлена обработка "грязного" JSON (экранированные кавычки).
   - Добавлена обработка двойного кодирования JSON.
4. Исправлена ошибка атрибута модели:
   - Заменено `model.max_images` на корректное `model.max_input_images`.

### Результат:
Ожидается деплой на Staging через PR. Требуется ручная проверка:
1. Нажать "Сгенерировать" в WebApp.
2. Проверить появление алерта "Отправка данных...".
3. Проверить начало генерации.
