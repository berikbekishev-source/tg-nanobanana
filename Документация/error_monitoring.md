# Мониторинг ошибок бота

## Что собираем
- Все ошибки из Telegram webhook, aiogram-обработчиков, Celery и бизнес-логики проходят через `botapp.error_tracker.ErrorTracker`.
- События сохраняются в `BotErrorEvent` (источник, уровень, статус, пользователь/GenRequest, текст, стек, payload).
- Критические ошибки отправляются в Telegram `ERROR_ALERT_CHAT_ID` (не чаще, чем раз в `ERROR_ALERT_COOLDOWN` секунд).
- При наличии `SENTRY_DSN` ErrorTracker дублирует события в Sentry с тегами `origin` и `gen_request_id`.

## Настройки
Добавьте переменные окружения (см. `.env.example`):

| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|------------|
| `ERROR_ALERT_CHAT_ID` | `LAVA_FALLBACK_CHAT_ID` | Чат/пользователь для критических ошибок |
| `ERROR_ALERT_COOLDOWN` | `300` | Интервал между одинаковыми уведомлениями |
| `ERROR_LOG_RETENTION_DAYS` | `30` | Срок хранения событий |

## Админка
- В разделе **Bot Errors** (Django admin) доступны фильтры по источнику/статусу, просмотр payload/stacktrace и ссылки на пользователя/генерацию.
- Статусы можно менять массово (`new → in_progress → resolved`).

## Очистка
- Команда `python manage.py prune_bot_errors` удаляет записи старше `ERROR_LOG_RETENTION_DAYS`. Настройте cron/Scheduler (например, раз в сутки).

## Добавление источников
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
Для async-кода используйте `await ErrorTracker.alog(...)`. Перед передачей payload удаляйте PII.

## Чек-лист перед релизом
1. `python manage.py migrate`
2. Проверить раздел Bot Errors в админке.
3. Вызвать тестовую ошибку и убедиться, что запись появилась и пришло Telegram-уведомление.
