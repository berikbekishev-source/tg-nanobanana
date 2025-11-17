# Мониторинг ошибок бота

## Что собираем
- Все ошибки из Telegram webhook, aiogram-обработчиков, Celery и бизнес-логики проходят через `botapp.error_tracker.ErrorTracker`.
- События сохраняются в `BotErrorEvent` (источник, уровень, статус, пользователь/GenRequest, текст, стек, payload).
- Критические ошибки отправляются в Telegram `ERROR_ALERT_CHAT_ID` (не чаще, чем раз в `ERROR_ALERT_COOLDOWN` секунд).
- При наличии `SENTRY_DSN` ErrorTracker дублирует события в Sentry с тегами `origin` и `gen_request_id`.

## Встроенные источники
ErrorTracker уже подключён к основным точкам сбоя:
- `/api/telegram/webhook` — все exeptions парсинга/валидации апдейтов улетают с `origin=webhook` и `severity=critical`, что моментально триггерит Telegram-уведомление.
- `botapp/aiogram_errors.py` — глобальный обработчик aiogram фиксирует любые падения FSM/handlers.
- Celery задачи (`generate_image_task`, `generate_video_task`, `extend_video_task`, `process_payment_webhook`) логируют финальные ошибки и уведомляют пользователя.
- `GenerationService.fail_generation` пишет предупреждения, когда генерация завершилась с ошибкой и клиенту оформлен возврат.
- Обработчики “Создать изображение/видео” и “Референсный промт” сохраняют все неожиданные ошибки ещё до постановки задачи в очередь.

Для новых участков используйте `ErrorTracker.log(...)` или `await ErrorTracker.alog(...)` (см. пример ниже). Payload очищайте от PII.

## Настройки
Добавьте переменные окружения (см. `.env.example`):

| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|------------|
| `ERROR_ALERT_CHAT_ID` | `LAVA_FALLBACK_CHAT_ID` | Чат/пользователь для критических ошибок |
| `ERROR_ALERT_COOLDOWN` | `300` | Интервал между одинаковыми уведомлениями |
| `ERROR_LOG_RETENTION_DAYS` | `30` | Срок хранения событий |

Дополнительно:
- `ERROR_ALERT_CHAT_ID` должен ссылаться на личный Telegram заказчика (сейчас `283738604`). Для production/staging значение задаётся через Railway CLI.
- `ERROR_ALERT_COOLDOWN` регулирует дедупликацию: если одинаковая ошибка приходит чаще, сообщения в чат не спамятся.

## Админка
- В Django-админке путь **Операции → Ошибки бота** (модель `BotErrorEvent`). Таблица показывает источник, хендлер, статус, пользователя, ссылку на `GenRequest`.
- В карточке события лежат полный текст сообщения, стек, payload/extra, а также снапшот имени пользователя.
- Уровни: `info`, `warning`, `critical`. Telegram-алерты отправляются только для `critical`.
- Статусы (`new`, `in_progress`, `resolved`) можно менять по одной записи или массовыми action’ами (`Mark as in progress`, `Mark as resolved`). Меняйте их вручную, когда начали/завершили разбор.

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

## Telegram-уведомления
- Отправляются ботом с токеном `TELEGRAM_BOT_TOKEN` на `ERROR_ALERT_CHAT_ID`.
- Сообщение содержит источник, хендлер, chat_id и первые ~400 символов текста ошибки. Повторы одного и того же события блокируются на `ERROR_ALERT_COOLDOWN` секунд.
- Если чат недоступен (например, пользователь не написал боту), Telegram API вернёт `400 chat not found` — проверьте, что заказчик ранее запускал тестового бота и что переменные окружения актуальны.

## Чек-лист перед релизом
1. `python manage.py migrate`
2. Проверить раздел Bot Errors в админке.
3. Вызвать тестовую ошибку и убедиться, что запись появилась и пришло Telegram-уведомление.

### Как вызвать тестовую ошибку на стенде
1. Узнайте значение `TG_WEBHOOK_SECRET` в Railway (`railway variables --service web | rg TG_WEBHOOK_SECRET`).
2. Выполните команду (подставьте секрет):

```bash
curl -X POST "https://web-staging-70d1.up.railway.app/api/telegram/webhook" \
     -H "x-telegram-bot-api-secret-token: <TG_WEBHOOK_SECRET>" \
     -H "Content-Type: application/json" \
     -d 'this-is-not-json'
```
3. Результат: в админке появится событие с `origin=webhook`, а в чат `ERROR_ALERT_CHAT_ID` прилетит предупреждение о JSONDecodeError.
