# Railway Deployment Guide

Документация по работе с Railway для проекта Telegram NanoBanana Bot.

## Содержание

1. [Структура проекта](#структура-проекта)
2. [Идентификаторы](#идентификаторы)
3. [Railway CLI](#railway-cli)
4. [Railway API](#railway-api)
5. [Переменные окружения](#переменные-окружения)
6. [Типичные задачи](#типичные-задачи)

---

## Структура проекта

**Проект:** Telegram_bot
**Workspace:** Berik's Projects
**Repository:** https://github.com/berikbekishev-source/tg-nanobanana

### Сервисы

Проект состоит из 4 сервисов:

1. **web** - Django приложение с веб-сервером (Gunicorn + Uvicorn)
2. **worker** - Celery worker для асинхронной генерации изображений
3. **beat** - Celery beat для периодических задач
4. **REDIS_URL** - Redis база данных для Celery и кеширования

### Конфигурация сервисов

#### Web Service
- **Dockerfile:** `Dockerfile.web`
- **Custom Start Command:** `gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --workers 2`
- **Port:** Переменная `$PORT` (автоматически от Railway)
- **Region:** europe-west4

#### Worker Service
- **Dockerfile:** `Dockerfile.worker`
- **Command:** `celery -A config worker -l info --pool=prefork --concurrency=2`
- **Autoscaling:** Нет

#### Beat Service
- **Dockerfile:** `Dockerfile.beat`
- **Command:** `celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler`

#### Redis Service
- **Type:** Railway Plugin (managed service)
- **Version:** Redis 7.x

---

## Идентификаторы

### Project & Environment

```bash
PROJECT_ID="866bc61a-0ef1-41d1-af53-26784f6e5f06"
ENVIRONMENT_ID="2eee50d8-402e-44bf-9035-8298efef91bc"
ENVIRONMENT_NAME="production"
```

### Service IDs

```bash
WEB_SERVICE_ID="29038dc3-c812-4b0d-9749-23cdd1b91863"
WORKER_SERVICE_ID="aeb9b998-c05b-41a0-865c-5b58b26746d2"
BEAT_SERVICE_ID="4e7336b6-89b9-4385-b0d2-3832cab482e0"
REDIS_SERVICE_ID="e8f15267-93da-42f2-a1da-c79ad8399d0f"
```

### API Token

```bash
RAILWAY_API_TOKEN="47a20fbb-1f26-402d-8e66-ba38660ef1d4"
```

⚠️ **ВАЖНО:** Этот токен дает полный доступ к проекту. Не публикуйте его в GitHub!

---

## Railway CLI

### Установка

```bash
# macOS/Linux
curl -fsSL https://railway.app/install.sh | sh

# Проверка версии
railway version
```

Текущая версия: `4.11.0`

### Аутентификация

```bash
# Через браузер
railway login

# Или через токен
export RAILWAY_TOKEN="47a20fbb-1f26-402d-8e66-ba38660ef1d4"
```

### Привязка к проекту

```bash
# Из директории проекта
cd /Users/berik/Desktop/tg-nanobanana

# Линковка уже выполнена, конфиг в ~/.railway/config.json
railway status
```

### Основные команды

#### Просмотр статуса

```bash
# Статус всех сервисов
railway status

# Статус в JSON формате
railway status --json

# Статус конкретного сервиса
railway status --service worker
```

#### Логи

```bash
# Логи worker (последние 100 строк)
railway logs --service worker

# Следить за логами в реальном времени
railway logs --service worker --tail 50

# Логи всех сервисов
railway logs
```

#### Переменные окружения

```bash
# Просмотр всех переменных для worker
railway variables --service worker

# Установка переменной
railway variables --set KEY=value --service worker

# Установка нескольких переменных
railway variables --set VAR1=value1 VAR2=value2 --service worker

# Удаление переменной
railway variables --unset KEY --service worker
```

#### Деплой

```bash
# Ручной редеплой сервиса
railway redeploy --service worker --yes

# Редеплой всех сервисов
railway redeploy --yes

# Деплой после git push (автоматический)
git push origin main
```

#### Другие команды

```bash
# Открыть проект в браузере
railway open

# Открыть логи в браузере
railway logs --service worker --open

# Запустить команду в Railway окружении
railway run python manage.py migrate

# Shell доступ (если поддерживается)
railway shell --service worker
```

---

## Railway API

Railway использует GraphQL API для всех операций.

### Endpoint

```
https://backboard.railway.app/graphql/v2
```

### Аутентификация

Все запросы требуют Bearer токен:

```bash
Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4
```

### Примеры запросов

#### 1. Получить информацию о сервисе

```bash
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { service(id: \"aeb9b998-c05b-41a0-865c-5b58b26746d2\") { name updatedAt deployments(first: 3) { edges { node { id status createdAt staticUrl } } } } }"
  }'
```

#### 2. Установить переменную окружения

```bash
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { variableUpsert(input: { environmentId: \"2eee50d8-402e-44bf-9035-8298efef91bc\", name: \"GEMINI_API_KEY\", serviceId: \"aeb9b998-c05b-41a0-865c-5b58b26746d2\", value: \"your-api-key-here\" }) }"
  }'
```

**Для установки переменных на всех сервисах:**

```bash
# Web
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { variableUpsert(input: { environmentId: \"2eee50d8-402e-44bf-9035-8298efef91bc\", name: \"YOUR_VAR\", serviceId: \"29038dc3-c812-4b0d-9749-23cdd1b91863\", value: \"value\" }) }"
  }'

# Worker
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { variableUpsert(input: { environmentId: \"2eee50d8-402e-44bf-9035-8298efef91bc\", name: \"YOUR_VAR\", serviceId: \"aeb9b998-c05b-41a0-865c-5b58b26746d2\", value: \"value\" }) }"
  }'

# Beat
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { variableUpsert(input: { environmentId: \"2eee50d8-402e-44bf-9035-8298efef91bc\", name: \"YOUR_VAR\", serviceId: \"4e7336b6-89b9-4385-b0d2-3832cab482e0\", value: \"value\" }) }"
  }'
```

#### 3. Триггернуть редеплой

```bash
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { serviceInstanceRedeploy(environmentId: \"2eee50d8-402e-44bf-9035-8298efef91bc\", serviceId: \"aeb9b998-c05b-41a0-865c-5b58b26746d2\") }"
  }'
```

#### 4. Получить логи

```bash
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { deploymentLogs(deploymentId: \"your-deployment-id\", limit: 100) { edges { node { message timestamp } } } }"
  }'
```

#### 5. Получить все переменные сервиса

```bash
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 47a20fbb-1f26-402d-8e66-ba38660ef1d4" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { variables(environmentId: \"2eee50d8-402e-44bf-9035-8298efef91bc\", serviceId: \"aeb9b998-c05b-41a0-865c-5b58b26746d2\") { edges { node { name value } } } }"
  }'
```

### Python скрипт для работы с API

```python
import requests
import json

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"
RAILWAY_TOKEN = "47a20fbb-1f26-402d-8e66-ba38660ef1d4"
ENVIRONMENT_ID = "2eee50d8-402e-44bf-9035-8298efef91bc"

def railway_query(query):
    """Выполнить GraphQL запрос к Railway API"""
    headers = {
        "Authorization": f"Bearer {RAILWAY_TOKEN}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        RAILWAY_API_URL,
        headers=headers,
        json={"query": query}
    )
    return response.json()

def set_variable(service_id, name, value):
    """Установить переменную окружения"""
    query = f"""
    mutation {{
      variableUpsert(input: {{
        environmentId: "{ENVIRONMENT_ID}",
        name: "{name}",
        serviceId: "{service_id}",
        value: "{value}"
      }})
    }}
    """
    return railway_query(query)

def redeploy_service(service_id):
    """Перезапустить сервис"""
    query = f"""
    mutation {{
      serviceInstanceRedeploy(
        environmentId: "{ENVIRONMENT_ID}",
        serviceId: "{service_id}"
      )
    }}
    """
    return railway_query(query)

# Пример использования
SERVICE_IDS = {
    "web": "29038dc3-c812-4b0d-9749-23cdd1b91863",
    "worker": "aeb9b998-c05b-41a0-865c-5b58b26746d2",
    "beat": "4e7336b6-89b9-4385-b0d2-3832cab482e0"
}

# Установить переменную на worker
result = set_variable(SERVICE_IDS["worker"], "DEBUG", "false")
print(json.dumps(result, indent=2))

# Перезапустить worker
result = redeploy_service(SERVICE_IDS["worker"])
print(json.dumps(result, indent=2))
```

---

## Переменные окружения

### Общие переменные (все сервисы)

```bash
# Django
SECRET_KEY=<random-secret-key>
DEBUG=false
ALLOWED_HOSTS=web-production-<hash>.up.railway.app,localhost,127.0.0.1

# Database (Supabase)
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
DATABASE_URL=postgresql://postgres.<project>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres

# Redis (автоматически от Railway)
REDIS_URL=redis://<host>:<port>

# Telegram Bot
TELEGRAM_BOT_TOKEN=<bot-token>
TELEGRAM_WEBHOOK_SECRET=<random-webhook-secret>

# Sentry (опционально)
SENTRY_DSN=<sentry-dsn>
SENTRY_ENVIRONMENT=production

# Gemini API
GEMINI_API_KEY=AIzaSyDjPIgc9s2J7seJAwFejV-R4skGFcTyxqw
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image-preview
GEMINI_IMAGE_MODEL_FALLBACK=gemini-2.5-flash-image-preview

# Google Vertex AI (опционально, если USE_VERTEX_AI=true)
USE_VERTEX_AI=false
GCP_PROJECT_ID=gen-lang-client-0838548551
GCP_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS_JSON=<service-account-json>
```

### Web Service специфичные

```bash
PORT=<auto-assigned-by-railway>
RAILWAY_PUBLIC_DOMAIN=web-production-<hash>.up.railway.app
```

### Worker Service специфичные

```bash
# Worker не требует дополнительных переменных
# Использует общие переменные
```

### Текущая конфигурация

**AI модель:** Gemini API (NanoBanana)
**Модель:** `gemini-2.5-flash-image-preview`
**Vertex AI:** Отключен (`USE_VERTEX_AI=false`)

---

## Типичные задачи

### 1. Сменить API ключ Gemini

```bash
# Через CLI (рекомендуется)
railway variables --set GEMINI_API_KEY="new-key-here" --service worker
railway variables --set GEMINI_API_KEY="new-key-here" --service web
railway variables --set GEMINI_API_KEY="new-key-here" --service beat

# Перезапустить worker для применения изменений
railway redeploy --service worker --yes
```

### 2. Переключиться на Vertex AI

```bash
# Включить Vertex AI
railway variables --set USE_VERTEX_AI=true --service worker

# Установить Service Account JSON
railway variables --set GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type":"service_account",...}' --service worker

# Установить GCP параметры
railway variables --set GCP_PROJECT_ID="your-project-id" --service worker
railway variables --set GCP_LOCATION="us-central1" --service worker

# Перезапустить worker
railway redeploy --service worker --yes
```

### 3. Вернуться на Gemini API

```bash
# Отключить Vertex AI
railway variables --set USE_VERTEX_AI=false --service worker

# Убедиться что модель установлена
railway variables --set GEMINI_IMAGE_MODEL="gemini-2.5-flash-image-preview" --service worker

# Перезапустить worker
railway redeploy --service worker --yes
```

### 4. Проверить логи после деплоя

```bash
# Следить за логами worker в реальном времени
railway logs --service worker --tail 50

# Проверить логи web (Django)
railway logs --service web --tail 50

# Проверить логи beat (Celery Beat)
railway logs --service beat --tail 50
```

### 5. Обновить код (git push)

```bash
# Коммит изменений
git add .
git commit -m "Your commit message"

# Пуш в GitHub (автоматически триггерит деплой)
git push origin main

# Проверить статус деплоя
railway status

# Следить за логами
railway logs --service worker
```

### 6. Запустить миграции Django

```bash
# Через Railway run
railway run python manage.py migrate

# Или через web service
railway run --service web python manage.py migrate
```

### 7. Создать суперпользователя Django

```bash
railway run python manage.py createsuperuser
```

### 8. Проверить здоровье всех сервисов

```bash
# Статус
railway status

# Логи всех сервисов (последние 20 строк каждого)
for service in web worker beat; do
  echo "=== $service ==="
  railway logs --service $service --tail 20
  echo ""
done
```

### 9. Массовая установка переменных

```bash
# Создать файл env.txt
cat > env.txt << 'EOF'
DEBUG=false
SENTRY_ENVIRONMENT=production
LOG_LEVEL=info
EOF

# Применить на все сервисы
for service in web worker beat; do
  while IFS='=' read -r key value; do
    railway variables --set "$key=$value" --service "$service"
  done < env.txt
done
```

### 10. Откатиться на предыдущий деплой

```bash
# 1. Посмотреть историю деплоев в Railway dashboard
railway open

# 2. Или через API получить список деплоев и выбрать нужный
# 3. Откатиться через dashboard или пересобрать из конкретного коммита

# Альтернатива - откатить git и пушнуть
git revert HEAD
git push origin main
```

---

## Мониторинг и отладка

### Проверка webhook Telegram

```bash
# Посмотреть логи web сервиса
railway logs --service web --tail 100

# Искать ошибки webhook
railway logs --service web | grep -i "webhook\|telegram\|error"
```

### Проверка генерации изображений

```bash
# Логи worker (где происходит генерация)
railway logs --service worker --tail 50

# Искать ошибки Gemini API
railway logs --service worker | grep -i "gemini\|error\|generate"

# Проверить статус Celery задач
railway run --service worker celery -A config inspect active
```

### Проверка Redis подключения

```bash
# Логи worker/web
railway logs --service worker | grep -i "redis\|connected"

# Проверить переменную REDIS_URL
railway variables --service worker | grep REDIS_URL
```

### Мониторинг ресурсов

Railway автоматически мониторит:
- CPU usage
- Memory usage
- Network traffic
- Request count

Все метрики доступны в Railway Dashboard: https://railway.app/project/866bc61a-0ef1-41d1-af53-26784f6e5f06

---

## Полезные ссылки

- **Railway Dashboard:** https://railway.app/project/866bc61a-0ef1-41d1-af53-26784f6e5f06
- **GitHub Repo:** https://github.com/berikbekishev-source/tg-nanobanana
- **Railway Docs:** https://docs.railway.app/
- **Railway API Docs:** https://docs.railway.app/reference/public-api
- **Gemini API Console:** https://aistudio.google.com/app/apikey
- **Google Cloud Console:** https://console.cloud.google.com/

---

## Troubleshooting

### Worker не подхватывает новые переменные

**Решение:** Перезапустить сервис после изменения переменных

```bash
railway redeploy --service worker --yes
```

### 429 Quota exceeded (Vertex AI)

**Причина:** Квоты на Imagen 3.0 не настроены или регион не поддерживается

**Решение:**
1. Переключиться на Gemini API (`USE_VERTEX_AI=false`)
2. Или запросить квоты в Google Cloud Console
3. Или попробовать другой регион (`GCP_LOCATION`)

### Gemini API errors

**Решение:** Проверить API ключ

```bash
# Проверить текущий ключ
railway variables --service worker | grep GEMINI_API_KEY

# Обновить ключ
railway variables --set GEMINI_API_KEY="new-key" --service worker
railway redeploy --service worker --yes
```

### Redis connection errors

**Решение:** Redis service должен быть запущен

```bash
railway status | grep -i redis
```

Если Redis не запущен - перезапустить через Railway dashboard.

### Django migrations не применяются

**Решение:** Запустить вручную

```bash
railway run python manage.py migrate
railway redeploy --service web --yes
```

---

## Безопасность

⚠️ **НЕ КОММИТИТЬ В GIT:**

- `.env` файлы
- `RAILWAY_API_TOKEN`
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `SUPABASE_SERVICE_ROLE_KEY`
- Service Account JSON файлы

✅ **Используйте:**

- Railway environment variables
- `.gitignore` для секретных файлов
- Railway Secrets для чувствительных данных

---

## Changelog

**2025-10-23**
- Добавлена поддержка Vertex AI Imagen
- Переключено обратно на Gemini API (NanoBanana model)
- Обновлен API ключ Gemini
- Создана документация по Railway

---

**Автор:** Claude Code
**Последнее обновление:** 2025-10-23
