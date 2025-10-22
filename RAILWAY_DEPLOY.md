# Инструкция по деплою на Railway

Этот проект состоит из нескольких сервисов, которые нужно развернуть на Railway.

## Архитектура

Проект требует 4 сервиса на Railway:
1. **Redis** - брокер сообщений для Celery
2. **Web** - Django API + Telegram webhook (Dockerfile.web)
3. **Worker** - Celery worker для обработки задач генерации изображений (Dockerfile.worker)
4. **Beat** - Celery Beat планировщик (Dockerfile.worker)

## Шаг 1: Создайте проект на Railway

1. Зайдите на https://railway.app
2. Создайте новый проект (New Project)
3. Выберите "Empty Project"

## Шаг 2: Добавьте Redis

1. В проекте нажмите "+ New"
2. Выберите "Database" → "Redis"
3. Railway автоматически создаст сервис Redis и переменную `REDIS_URL`

## Шаг 3: Создайте сервис Web

1. Нажмите "+ New" → "GitHub Repo" (или "Empty Service" если хотите деплоить вручную)
2. Подключите ваш GitHub репозиторий или загрузите код
3. В настройках сервиса:
   - **Name**: `web`
   - **Dockerfile Path**: `Dockerfile.web`
   - **Root Directory**: оставьте пустым (корень проекта)

4. Добавьте переменные окружения (Settings → Variables):

```env
DJANGO_DEBUG=false
SECRET_KEY=ваш-секретный-ключ-для-django
ALLOWED_HOSTS=*.railway.app
DATABASE_URL=ваш-postgresql-dsn-от-supabase
REDIS_URL=${{Redis.REDIS_URL}}
TELEGRAM_BOT_TOKEN=ваш-токен-от-botfather
TG_WEBHOOK_SECRET=ваш-секретный-заголовок-для-webhook
PUBLIC_BASE_URL=${{Railway.RAILWAY_PUBLIC_DOMAIN}}
GEMINI_API_KEY=ваш-ключ-gemini-api
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
GEMINI_IMAGE_MODEL_FALLBACK=gemini-2.5-flash-image-preview
SUPABASE_URL=https://ваш-проект.supabase.co
SUPABASE_SERVICE_ROLE_KEY=ваш-service-role-key
SUPABASE_BUCKET=bot-images
PORT=${{Railway.PORT}}
```

**Важно**:
- `REDIS_URL=${{Redis.REDIS_URL}}` - автоматически подставит URL Redis из первого шага
- `PUBLIC_BASE_URL` должен содержать домен вашего Railway приложения (например: `https://web-production-xxxx.up.railway.app`)
- После первого деплоя скопируйте домен из раздела "Settings → Domains" и обновите `PUBLIC_BASE_URL`

## Шаг 4: Создайте сервис Worker

1. Нажмите "+ New" → "GitHub Repo" (тот же репозиторий)
2. В настройках сервиса:
   - **Name**: `worker`
   - **Dockerfile Path**: `Dockerfile.worker`
   - **Root Directory**: оставьте пустым

3. Добавьте ВСЕ те же переменные окружения, что и для Web (можно скопировать)

**Важно**: Worker использует Dockerfile.worker, который уже содержит правильную команду для запуска Celery worker.

## Шаг 5: Создайте сервис Beat

1. Нажмите "+ New" → "GitHub Repo" (тот же репозиторий)
2. В настройках сервиса:
   - **Name**: `beat`
   - **Dockerfile Path**: `Dockerfile.worker`
   - **Custom Start Command**: `celery -A config.celery:app beat -l INFO`

3. Добавьте ВСЕ те же переменные окружения

## Шаг 6: Настройте Telegram Webhook

После деплоя сервиса Web:

1. Получите публичный URL вашего сервиса web (например: `https://web-production-xxxx.up.railway.app`)
2. Обновите переменную `PUBLIC_BASE_URL` в настройках сервиса web
3. Зайдите в логи сервиса web и выполните миграции (если ещё не выполнены):

```bash
# Railway автоматически выполнит миграции при старте, если вы используете railway.toml
```

4. Установите webhook для Telegram бота (можно через curl или через Railway CLI):

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://ваш-домен.railway.app/api/telegram/webhook", "secret_token": "ваш-TG_WEBHOOK_SECRET"}'
```

Или используйте Django management команду (если есть SSH доступ):
```bash
python manage.py set_webhook
```

## Шаг 7: Проверьте работу

1. Откройте Telegram и отправьте сообщение вашему боту
2. Проверьте логи сервисов:
   - **Web**: должен получать webhook от Telegram
   - **Worker**: должен обрабатывать задачи генерации изображений
   - **Beat**: должен работать (если есть периодические задачи)

## Дополнительно: Flower (опционально)

Если хотите мониторить Celery задачи через Flower:

1. Создайте ещё один сервис с тем же репозиторием
2. Настройте:
   - **Name**: `flower`
   - **Dockerfile Path**: `Dockerfile.worker`
   - **Custom Start Command**: `celery -A config.celery:app flower --address=0.0.0.0 --port=$PORT`
3. Добавьте все переменные окружения
4. Flower будет доступен по публичному URL этого сервиса

## Полезные команды

Проверить статус webhook:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

Удалить webhook (для тестирования):
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/deleteWebhook"
```

## Troubleshooting

### Бот не отвечает
- Проверьте логи сервиса Web
- Убедитесь что webhook установлен правильно: `getWebhookInfo`
- Проверьте что `TG_WEBHOOK_SECRET` совпадает с тем, что вы указали при setWebhook

### Worker не обрабатывает задачи
- Проверьте что Redis доступен (переменная `REDIS_URL` правильная)
- Проверьте логи Worker
- Убедитесь что все сервисы используют одинаковую конфигурацию Redis

### Ошибки с базой данных
- Проверьте правильность `DATABASE_URL` от Supabase
- Убедитесь что миграции выполнены
- Проверьте что Supabase проект активен и доступен

## Структура переменных окружения

Обязательные:
- `DJANGO_DEBUG` - false для production
- `SECRET_KEY` - секретный ключ Django
- `ALLOWED_HOSTS` - домены Railway (*.railway.app)
- `DATABASE_URL` - PostgreSQL от Supabase
- `REDIS_URL` - от Railway Redis сервиса
- `TELEGRAM_BOT_TOKEN` - от BotFather
- `TG_WEBHOOK_SECRET` - ваш секретный токен для webhook
- `PUBLIC_BASE_URL` - публичный URL вашего Railway приложения
- `GEMINI_API_KEY` - API ключ Google Gemini
- `SUPABASE_URL` - URL вашего Supabase проекта
- `SUPABASE_SERVICE_ROLE_KEY` - ключ Supabase
- `SUPABASE_BUCKET` - имя bucket для изображений (bot-images)

Опциональные:
- `SENTRY_DSN` - для мониторинга ошибок
- `GEMINI_IMAGE_MODEL_FALLBACK` - резервная модель
