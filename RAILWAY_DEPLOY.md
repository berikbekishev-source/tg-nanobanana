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

1. Нажмите "+ New" → "GitHub Repo"
2. Подключите ваш GitHub репозиторий `berikbekishev-source/tg-nanobanana`
3. Переименуйте сервис в `web` (нажмите на имя сервиса вверху)
4. Перейдите в **Settings** сервиса

### 4.1 Настройте Build (Settings → Build)

В разделе **Build** → **Builder**:
- **Dockerfile**: кликните на поле и введите `Dockerfile.web`

В разделе **Deploy**:
- **Custom Start Command**: введите команду для миграций и запуска:
  ```
  sh -c 'python manage.py migrate && gunicorn -k uvicorn.workers.UvicornWorker config.asgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120'
  ```

### 4.2 Добавьте переменные окружения (Settings → Variables)

Нажмите **RAW Editor** (переключатель справа) и вставьте:

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
```

### 4.3 Настройка домена (Settings → Networking)

1. Нажмите **Generate Domain** (оставьте поле порта пустым - Railway автоматически определит)
2. Скопируйте сгенерированный домен (например: `web-production-xxxx.up.railway.app`)
3. Вернитесь в **Variables** и обновите `PUBLIC_BASE_URL`:
   ```
   PUBLIC_BASE_URL=https://web-production-xxxx.up.railway.app
   ```

**Важно**:
- `REDIS_URL=${{Redis.REDIS_URL}}` - автоматически подставит URL Redis из первого шага
- Переменная `PORT` не нужна - Railway предоставляет её автоматически

## Шаг 4: Создайте сервис Worker

1. Нажмите "+ New" → "GitHub Repo" (выберите тот же репозиторий)
2. Переименуйте сервис в `worker`
3. Перейдите в **Settings** → **Build**

### 4.1 Настройте Build

В разделе **Build** → **Builder**:
- **Dockerfile**: введите `Dockerfile.worker`

### 4.2 Добавьте переменные окружения

Скопируйте **ВСЕ** переменные из сервиса Web (Settings → Variables → RAW Editor)

**Важно**: Dockerfile.worker уже содержит команду запуска Celery worker, Custom Start Command не нужен.

## Шаг 5: Создайте сервис Beat

1. Нажмите "+ New" → "GitHub Repo" (выберите тот же репозиторий)
2. Переименуйте сервис в `beat`
3. Перейдите в **Settings** → **Build**

### 5.1 Настройте Build и Deploy

В разделе **Build** → **Builder**:
- **Dockerfile**: введите `Dockerfile.worker`

В разделе **Deploy**:
- **Custom Start Command**: введите:
  ```
  celery -A config.celery:app beat -l INFO
  ```

### 5.2 Добавьте переменные окружения

Скопируйте **ВСЕ** переменные из сервиса Web

## Шаг 6: Настройте Telegram Webhook

После деплоя сервиса Web:

1. Получите публичный URL вашего сервиса web (например: `https://web-production-xxxx.up.railway.app`)
2. Обновите переменную `PUBLIC_BASE_URL` в настройках сервиса web
3. Миграции выполнятся автоматически при старте web сервиса (через Custom Start Command)

4. Установите webhook для Telegram бота (можно через curl):

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

## Почему не используется railway.toml?

В этом проекте используется несколько сервисов (web, worker, beat) из одного репозитория, но с разными Dockerfile и командами запуска. Файл `railway.toml` применяется ко всем сервисам глобально и блокирует индивидуальные настройки через UI.

**Решение**: Настройка каждого сервиса индивидуально через Settings UI в Railway. Это даёт полный контроль над конфигурацией каждого сервиса.
