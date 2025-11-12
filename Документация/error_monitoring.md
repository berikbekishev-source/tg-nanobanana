# Мониторинг ошибок бота

## Что мы собираем
- Все критичные исключения из Telegram webhook, aiogram‑хендлеров, Celery задач и бизнес-логики генераций проходят через `botapp.error_tracker.ErrorTracker`.
- Модель `BotErrorEvent` хранит источник (`origin`), уровень (`severity`), статус (`new/in_progress/resolved`), ссылку на пользователя/GenRequest, текст ошибки, стек и payload.
- При `severity=critical` событие отправляется в Telegram чат `ERROR_ALERT_CHAT_ID`. Для антиспама используется `ERROR_ALERT_COOLDOWN` (секунды между одинаковыми уведомлениями).
- Если указан `SENTRY_DSN`, ErrorTracker дополнительно отправляет ошибки в Sentry с тегами `origin` и `gen_request_id`.

## Настройки
Добавьте переменные в Railway/`.env` (пример в `.env.example`):

| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|------------|
| `ERROR_ALERT_CHAT_ID` | `LAVA_FALLBACK_CHAT_ID` (переопределите на 283738601) | Куда слать критические ошибки |
| `ERROR_ALERT_COOLDOWN` | `300` | Минимальный интервал между одинаковыми уведомлениями |
| `ERROR_LOG_RETENTION_DAYS` | `30` | Сколько дней хранить `BotErrorEvent` |

## Админка
- В Django admin появился раздел **Bot Errors** (см. `botapp/admin.py`). Там можно фильтровать события, менять статус (`new → in_progress → resolved`), смотреть payload/stacktrace и переходить к связанному пользователю или генерации.

## Очистка и обслуживание
- Для удаления старых записей есть команда:
  ```bash
  python manage.py prune_bot_errors
  ```
  Она ориентируется на `ERROR_LOG_RETENTION_DAYS`. Запускайте её по расписанию (Railway Scheduler/Cron) хотя бы раз в сутки.

## Как логировать новые источники
```python
from botapp.error_tracker import ErrorTracker
from botapp.models import BotErrorEvent

ErrorTracker.log(
    origin=BotErrorEvent.Origin.MINIAPP,
    severity=BotErrorEvent.Severity.WARNING,
    handler="miniapp.views.payments",
    chat_id=user.chat_id,
    payload={"request_id": request.id},
    exc=exc,
)
```
Для async‑контекста используйте `await ErrorTracker.alog(...)`. Обязательно фильтруйте PII перед передачей в `payload`.

## Чек-лист перед релизом
1. Применить миграции (`python manage.py migrate`).
2. Убедиться, что в админке появился раздел **Bot Errors**.
3. Провести тест: вызвать контролируемую ошибку (например, временно указать неверный токен webhook) и проверить, что запись создалась и пришло Telegram-уведомление.
