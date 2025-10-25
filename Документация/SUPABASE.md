# Supabase Management Guide

Документация по работе с Supabase для проекта Telegram NanoBanana Bot.

## Содержание

1. [Информация о проекте](#информация-о-проекте)
2. [Supabase CLI](#supabase-cli)
3. [Management API](#management-api)
4. [Client API](#client-api)
5. [Storage API](#storage-api)
6. [Типичные задачи](#типичные-задачи)

---

## Информация о проекте

### Текущая конфигурация

```bash
# Получить из Railway
railway variables --service worker | grep SUPABASE
```

**Используемые переменные:**
- `SUPABASE_URL` - URL проекта Supabase
- `SUPABASE_SERVICE_ROLE_KEY` - Service Role ключ (полный доступ)
- `SUPABASE_BUCKET` - название bucket для хранения изображений (текущий: `video_veo3`)

### Что использует проект

1. **Supabase Storage** - для хранения сгенерированных изображений
2. **Supabase Database (PostgreSQL)** - через `DATABASE_URL` для Django моделей

### Текущие bucket'ы

- `video_veo3` - основной bucket для изображений

---

## Supabase CLI

### Установка

```bash
# macOS/Linux
brew install supabase/tap/supabase

# NPM (все платформы)
npm install -g supabase

# Проверка версии
supabase --version
```

### Аутентификация

```bash
# Получить access token из Supabase Dashboard
# https://supabase.com/dashboard/account/tokens

# Логин
supabase login

# Или использовать токен напрямую
export SUPABASE_ACCESS_TOKEN="your-access-token"
```

### Привязка к проекту

```bash
# Получить Project ID из Dashboard или URL
# URL формат: https://app.supabase.com/project/[PROJECT_ID]

# Линк к проекту
supabase link --project-ref YOUR_PROJECT_ID

# Проверка статуса
supabase status
```

### Основные команды CLI

#### Работа с базой данных

```bash
# Получить информацию о БД
supabase db dump

# Создать миграцию
supabase db diff -f migration_name

# Применить миграции
supabase db push

# Сброс БД (локально)
supabase db reset

# Запустить SQL запрос
supabase db query "SELECT * FROM botapp_tguser LIMIT 10"
```

#### Работа с Storage

```bash
# Список bucket'ов
supabase storage list

# Создать bucket
supabase storage create my-bucket --public

# Удалить bucket
supabase storage rm my-bucket

# Список файлов в bucket
supabase storage ls video_veo3

# Скачать файл
supabase storage download video_veo3/path/to/file.png -o local-file.png

# Загрузить файл
supabase storage upload video_veo3/test.png local-file.png
```

#### Локальная разработка

```bash
# Запустить Supabase локально (Docker)
supabase start

# Остановить локальный Supabase
supabase stop

# Статус локального окружения
supabase status
```

#### Функции (Edge Functions)

```bash
# Создать новую функцию
supabase functions new my-function

# Деплой функции
supabase functions deploy my-function

# Логи функции
supabase functions logs my-function
```

---

## Management API

Supabase Management API позволяет программно управлять проектами.

### Endpoint

```
https://api.supabase.com/v1
```

### Аутентификация

Нужен **Access Token** из Supabase Dashboard: https://supabase.com/dashboard/account/tokens

```bash
Authorization: Bearer YOUR_ACCESS_TOKEN
```

### Примеры запросов

#### 1. Получить список проектов

```bash
curl -X GET https://api.supabase.com/v1/projects \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

#### 2. Получить информацию о проекте

```bash
curl -X GET https://api.supabase.com/v1/projects/PROJECT_ID \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### 3. Получить API ключи проекта

```bash
curl -X GET https://api.supabase.com/v1/projects/PROJECT_ID/api-keys \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### 4. Получить статистику использования

```bash
curl -X GET https://api.supabase.com/v1/projects/PROJECT_ID/usage \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### 5. Получить настройки Storage

```bash
curl -X GET https://api.supabase.com/v1/projects/PROJECT_ID/config/storage \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Python скрипт для Management API

```python
import requests
import json

SUPABASE_ACCESS_TOKEN = "your-access-token"
PROJECT_ID = "your-project-id"
BASE_URL = "https://api.supabase.com/v1"

def supabase_management(endpoint, method="GET", data=None):
    """Выполнить запрос к Supabase Management API"""
    headers = {
        "Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}{endpoint}"

    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=data)
    elif method == "PATCH":
        response = requests.patch(url, headers=headers, json=data)
    elif method == "DELETE":
        response = requests.delete(url, headers=headers)

    return response.json()

# Получить список проектов
projects = supabase_management("/projects")
print(json.dumps(projects, indent=2))

# Получить информацию о конкретном проекте
project = supabase_management(f"/projects/{PROJECT_ID}")
print(json.dumps(project, indent=2))

# Получить API ключи
api_keys = supabase_management(f"/projects/{PROJECT_ID}/api-keys")
print(json.dumps(api_keys, indent=2))

# Получить статистику
usage = supabase_management(f"/projects/{PROJECT_ID}/usage")
print(json.dumps(usage, indent=2))
```

---

## Client API

Supabase Client API используется для работы с данными и storage из приложения.

### Python Client

Уже используется в проекте (`botapp/services.py`):

```python
from supabase import create_client
from django.conf import settings

# Инициализация клиента
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
```

### Работа с базой данных

```python
# SELECT
users = supabase.table('botapp_tguser').select('*').execute()

# INSERT
result = supabase.table('botapp_tguser').insert({
    'chat_id': 123456789,
    'username': 'test_user'
}).execute()

# UPDATE
result = supabase.table('botapp_tguser').update({
    'username': 'new_username'
}).eq('chat_id', 123456789).execute()

# DELETE
result = supabase.table('botapp_tguser').delete().eq('chat_id', 123456789).execute()

# Сложные запросы
requests = supabase.table('botapp_genrequest') \
    .select('*') \
    .eq('status', 'done') \
    .gte('created_at', '2025-01-01') \
    .order('created_at', desc=True) \
    .limit(10) \
    .execute()
```

### Работа с Storage (текущая реализация)

```python
# Загрузка файла (из botapp/services.py)
def supabase_upload_png(content: bytes) -> str:
    """Загружает PNG в Supabase Storage и возвращает публичный URL."""
    import uuid
    from supabase import create_client
    from django.conf import settings

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    key = f"images/{uuid.uuid4().hex}.png"

    # Загрузка
    supabase.storage.from_(settings.SUPABASE_BUCKET).upload(
        path=key,
        file=content,
        file_options={"content-type": "image/png", "upsert": "true"}
    )

    # Получить публичный URL
    public = supabase.storage.from_(settings.SUPABASE_BUCKET).get_public_url(key)
    return public
```

---

## Storage API

### REST API для Storage

Supabase Storage имеет собственный REST API.

**Base URL:** `https://YOUR_PROJECT.supabase.co/storage/v1`

### Примеры Storage API

#### 1. Список bucket'ов

```bash
curl https://YOUR_PROJECT.supabase.co/storage/v1/bucket \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY"
```

#### 2. Создать bucket

```bash
curl -X POST https://YOUR_PROJECT.supabase.co/storage/v1/bucket \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-new-bucket",
    "public": true,
    "file_size_limit": 52428800,
    "allowed_mime_types": ["image/png", "image/jpeg"]
  }'
```

#### 3. Загрузить файл

```bash
curl -X POST https://YOUR_PROJECT.supabase.co/storage/v1/object/video_veo3/test.png \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY" \
  -H "Content-Type: image/png" \
  --data-binary @image.png
```

#### 4. Скачать файл

```bash
curl https://YOUR_PROJECT.supabase.co/storage/v1/object/video_veo3/images/abc123.png \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY" \
  -o downloaded.png
```

#### 5. Список файлов в bucket

```bash
curl -X POST https://YOUR_PROJECT.supabase.co/storage/v1/object/list/video_veo3 \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 100,
    "offset": 0,
    "sortBy": {
      "column": "created_at",
      "order": "desc"
    }
  }'
```

#### 6. Удалить файл

```bash
curl -X DELETE https://YOUR_PROJECT.supabase.co/storage/v1/object/video_veo3/images/abc123.png \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY"
```

#### 7. Получить публичный URL

Для публичных bucket'ов URL формируется так:

```
https://YOUR_PROJECT.supabase.co/storage/v1/object/public/video_veo3/images/abc123.png
```

### Python скрипт для Storage API

```python
import requests
import json

SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SERVICE_ROLE_KEY = "your-service-role-key"
BUCKET = "video_veo3"

def storage_api(endpoint, method="GET", data=None, files=None):
    """Выполнить запрос к Storage API"""
    headers = {
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}"
    }
    if not files:
        headers["Content-Type"] = "application/json"

    url = f"{SUPABASE_URL}/storage/v1{endpoint}"

    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        if files:
            response = requests.post(url, headers=headers, files=files)
        else:
            response = requests.post(url, headers=headers, json=data)
    elif method == "DELETE":
        response = requests.delete(url, headers=headers)

    return response.json() if response.text else {}

# Список bucket'ов
buckets = storage_api("/bucket")
print(json.dumps(buckets, indent=2))

# Список файлов
files = storage_api(f"/object/list/{BUCKET}", "POST", {
    "limit": 10,
    "sortBy": {"column": "created_at", "order": "desc"}
})
print(json.dumps(files, indent=2))

# Загрузить файл
with open("test.png", "rb") as f:
    result = storage_api(
        f"/object/{BUCKET}/test-upload.png",
        "POST",
        files={"file": ("test.png", f, "image/png")}
    )
print(json.dumps(result, indent=2))

# Удалить файл
result = storage_api(f"/object/{BUCKET}/test-upload.png", "DELETE")
print(result)
```

---

## Типичные задачи

### 1. Получить статистику Storage

```bash
# Через Management API
curl https://api.supabase.com/v1/projects/PROJECT_ID/usage \
  -H "Authorization: Bearer ACCESS_TOKEN" | jq '.storage'
```

### 2. Очистить старые изображения

```python
from supabase import create_client
from datetime import datetime, timedelta
import os

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# Получить список файлов старше 30 дней
bucket = "video_veo3"
files = supabase.storage.from_(bucket).list(path="images")

cutoff_date = datetime.now() - timedelta(days=30)

for file in files:
    file_date = datetime.fromisoformat(file['created_at'].replace('Z', '+00:00'))
    if file_date < cutoff_date:
        print(f"Deleting old file: {file['name']}")
        supabase.storage.from_(bucket).remove([f"images/{file['name']}"])
```

### 3. Миграция bucket (переименование)

```python
from supabase import create_client
import os

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

old_bucket = "video_veo3"
new_bucket = "bot-images"

# 1. Создать новый bucket
supabase.storage.create_bucket(new_bucket, {"public": True})

# 2. Скопировать все файлы
files = supabase.storage.from_(old_bucket).list()
for file in files:
    # Скачать
    data = supabase.storage.from_(old_bucket).download(file['name'])
    # Загрузить в новый bucket
    supabase.storage.from_(new_bucket).upload(file['name'], data)

# 3. Обновить переменную окружения на Railway
# railway variables --set SUPABASE_BUCKET=bot-images --service worker
```

### 4. Бэкап базы данных

```bash
# Через CLI
supabase db dump > backup_$(date +%Y%m%d).sql

# Восстановление
supabase db reset
psql "$DATABASE_URL" < backup_20250123.sql
```

### 5. Мониторинг использования Storage

```python
import requests

SUPABASE_ACCESS_TOKEN = "your-token"
PROJECT_ID = "your-project-id"

response = requests.get(
    f"https://api.supabase.com/v1/projects/{PROJECT_ID}/usage",
    headers={"Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}"}
)

usage = response.json()
storage_gb = usage['storage']['total'] / (1024**3)
print(f"Storage usage: {storage_gb:.2f} GB")
```

### 6. Создать signed URL для приватного файла

```python
from supabase import create_client

supabase = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

# Создать URL с истечением через 1 час
signed_url = supabase.storage.from_("video_veo3").create_signed_url(
    "images/secret.png",
    expires_in=3600
)

print(signed_url)
```

### 7. Проверить существование bucket

```python
from supabase import create_client

supabase = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

try:
    bucket = supabase.storage.get_bucket("video_veo3")
    print(f"Bucket exists: {bucket}")
except Exception as e:
    print(f"Bucket does not exist: {e}")
```

### 8. Массовое удаление файлов по паттерну

```python
from supabase import create_client

supabase = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

# Удалить все .tmp файлы
files = supabase.storage.from_("video_veo3").list("images")
tmp_files = [f"images/{f['name']}" for f in files if f['name'].endswith('.tmp')]

if tmp_files:
    result = supabase.storage.from_("video_veo3").remove(tmp_files)
    print(f"Deleted {len(tmp_files)} files")
```

---

## Интеграция с Railway

### Автоматическое обновление переменных

```bash
# Получить Supabase credentials и установить в Railway
SUPABASE_URL="https://your-project.supabase.co"
SERVICE_KEY="your-service-role-key"

railway variables --set SUPABASE_URL="$SUPABASE_URL" --service worker
railway variables --set SUPABASE_SERVICE_ROLE_KEY="$SERVICE_KEY" --service worker
railway variables --set SUPABASE_BUCKET="bot-images" --service worker
```

### Скрипт синхронизации

```python
import os
import subprocess
import requests

# Получить данные из Supabase Management API
ACCESS_TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN")
PROJECT_ID = os.getenv("SUPABASE_PROJECT_ID")

response = requests.get(
    f"https://api.supabase.com/v1/projects/{PROJECT_ID}/api-keys",
    headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}
)

keys = response.json()
service_role = next(k for k in keys if k['name'] == 'service_role')

# Установить в Railway
subprocess.run([
    "railway", "variables", "--set",
    f"SUPABASE_SERVICE_ROLE_KEY={service_role['api_key']}",
    "--service", "worker"
])
```

---

## Полезные ссылки

- **Supabase Dashboard:** https://app.supabase.com
- **CLI Docs:** https://supabase.com/docs/guides/cli
- **Management API Docs:** https://supabase.com/docs/reference/api
- **Storage API Docs:** https://supabase.com/docs/reference/javascript/storage
- **Python Client Docs:** https://supabase.com/docs/reference/python/introduction

---

## Безопасность

⚠️ **НЕ КОММИТИТЬ В GIT:**
- Service Role Key (полный доступ к проекту)
- Access Token (управление проектами)
- Database passwords

✅ **Используйте:**
- Environment variables (Railway)
- `.env` файлы (gitignore'd)
- Row Level Security (RLS) в Supabase

---

**Автор:** Claude Code
**Последнее обновление:** 2025-10-23
