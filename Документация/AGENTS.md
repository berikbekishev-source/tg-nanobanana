# Инструкция для ИИ-агентов

Документ описывает как работать с проектом Telegram NanoBanana Bot, какие ресурсы доступны и как устроен пайплайн деплоя. Все действия выполняйте строго по описанным правилам.

## 1. Структура проекта

### 1.1 Репозиторий и стек
- Репозиторий: `https://github.com/berikbekishev-source/tg-nanobanana`.
- Основной стек: Python 3.12, Django 5.2, Celery, Redis, PostgreSQL (Supabase), Railway, Telegram Bot API.
- Web-сервис и воркеры запускаются в Railway. Для разработки используйте Docker (`docker-compose.yml`) или локальный Python.

### 1.2 Основные каталоги
- `botapp/` — бизнес-логика бота, API (`api.py`), задачи Celery (`tasks.py`), обработчики Telegram (`handlers/`), интеграции (`providers/`).
- `config/` — настройки Django (ASGI, Celery, URL, env-профили).
- `manage.py` — точка входа Django.
- `Dockerfile.web`, `Dockerfile.worker`, `Dockerfile.beat`, `docker-compose.yml` — контейнеры и локальный запуск.
- `templates/`, `lavatop/`, `dashboard/` — вспомогательные UI-модули.
- `Документация/` — все инструкции проекта (добавляйте новые документы сюда).

### 1.3 Railway сервисы и окружения
- Railway Workspace: **Berik's Projects**, Project ID `866bc61a-0ef1-41d1-af53-26784f6e5f06` (`Telegram_bot`).
- Сопоставление веток и окружений:

| Git ветка | Railway окружение | ENV_ID | Назначение |
|-----------|-------------------|--------|------------|
| `staging` | `staging`         | `9e15b55d-8220-4067-a47e-191a57c2bcca` | Автотесты, тестовый Telegram-бот.
| `main`    | `production`      | `2eee50d8-402e-44bf-9035-8298efef91bc` | Продакшн и основной бот.

- Сервисы и команды:
  - `web` (`29038dc3-c812-4b0d-9749-23cdd1b91863`) — `gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --workers 2` (Dockerfile.web).
  - `worker` (`aeb9b998-c05b-41a0-865c-5b58b26746d2`) — `celery -A config worker -l info --pool=prefork --concurrency=2` (Dockerfile.worker).
  - `beat` (`4e7336b6-89b9-4385-b0d2-3832cab482e0`) — `celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler` (Dockerfile.beat).
  - `redis` (`e8f15267-93da-42f2-a1da-c79ad8399d0f`) — управляемый сервис Railway.

### 1.4 Документация и служебные файлы
- Все инструкции размещайте в `Документация/*.md`. Текущий файл — эталон процесса.
- Журнал действий агентов ведётся в `Документация/AGENTS_LOGS.md`. Если файла нет — создайте, добавляйте туда дату, задачу, сделанный шаг и ссылку на коммит.
- Любые новые регламенты или чек-листы добавляйте только после согласования с человеком.

## 2. Доступы к инструментам

### 2.1 GitHub Access

**GitHub Personal Access Token (PAT):**
- **Где получить:** Попросите токен у человека перед началом работы
- **Формат:** `ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`
- **Хранение:** Храните в переменной окружения, НЕ коммитьте в репозиторий!

**Репозиторий:** `https://github.com/berikbekishev-source/tg-nanobanana`

**Авторизация в GitHub CLI:**
```bash
# Получите токен у человека и установите в переменную окружения GH_TOKEN
export GH_TOKEN="<ваш_токен>"

# GitHub CLI автоматически использует GH_TOKEN - НЕ нужен gh auth login!
# Это позволяет нескольким агентам работать параллельно без конфликтов
```

**Проверка доступа:**
```bash
# Проверка что токен работает
gh auth status

# Проверка доступа к репозиторию
gh repo view berikbekishev-source/tg-nanobanana
gh pr list --limit 5
```

**⚠️ ВАЖНО для параллельной работы:**
- Используйте `GH_TOKEN` вместо `gh auth login` - это предотвращает конфликты между агентами
- `gh auth login` сохраняет токен в `~/.config/gh/hosts.yml` и агенты перезаписывают друг друга
- `GH_TOKEN` работает из переменной окружения и не создает конфликтов

**Когда ИИ агент должен подключаться к GitHub:**
1. **При подготовке к работе** - для проверки текущего состояния веток и PR
2. **После деплоя в staging** - для проверки статуса PR и CI
3. **При создании Release PR** - для запуска workflow `create-release-pr.yml`
4. **После создания Release PR** - для мониторинга CI и проверки готовности к merge
5. **После merge в main** - для проверки что merge прошел успешно

**Критичные секреты репозитория:**
- `ADMIN_GH_TOKEN` - используется в GitHub Actions для автоматических операций
- `RAILWAY_API_TOKEN` - для деплоя из GitHub Actions
- `PRODUCTION_BASE_URL`, `TELEGRAM_NOTIFY_TOKEN`, `TELEGRAM_NOTIFY_CHAT_ID` - для уведомлений

⚠️ **НЕ меняйте названия секретов и НЕ коммитьте токены в репозиторий!**

### 2.2 Railway Access

**Railway API Token (Account):**
- **Где получить:** Попросите токен у человека или найдите в защищенном хранилище (1Password)
- **Формат:** `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- **Использование:** Для GraphQL API запросов к Railway

**Railway CLI Token:**
- **Получение:** Через `railway login` (откроется браузер)
- **Автоматическое хранение:** `~/.railway/config.json`

**Project ID:** `866bc61a-0ef1-41d1-af53-26784f6e5f06`

**Быстрая настройка Railway CLI:**
  ```bash
# Авторизация через браузер (рекомендуется для первого запуска)
railway login
# Откроется браузер, войдите как Berik (berik.bekishev@gmail.com)

# Проверка авторизации
railway whoami
# Должно вывести: Logged in as Berik (berik.bekishev@gmail.com) 👋

# Линковка проекта
railway link --project 866bc61a-0ef1-41d1-af53-26784f6e5f06

# Проверка статуса
railway status
```

**Альтернативная авторизация через API Token:**
  ```bash
# Если у вас есть Railway CLI Token
export RAILWAY_TOKEN="<ваш_railway_cli_token>"
railway login --token "$RAILWAY_TOKEN"
  railway link --project 866bc61a-0ef1-41d1-af53-26784f6e5f06
  ```

**Основные команды для диагностики:**
  ```bash
# Статус проекта
railway status

# Логи сервисов (только для чтения!)
railway logs --service web --tail 50
railway logs --service worker --tail 50
railway logs --service beat --tail 30

# Переменные окружения (только просмотр)
  railway variables --service web
  ```

**Railway GraphQL API:**
- Endpoint: `https://backboard.railway.app/graphql/v2`
- Authorization: `Bearer <RAILWAY_API_TOKEN>`

**Пример запроса через GraphQL API (проверка deployment):**
```bash
# Установите Railway API Token в переменную
export RAILWAY_API_TOKEN="<ваш_railway_api_token>"

curl -s -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { deployments(input: { environmentId: \"9e15b55d-8220-4067-a47e-191a57c2bcca\", serviceId: \"29038dc3-c812-4b0d-9749-23cdd1b91863\" }) { edges { node { id status createdAt } } } }"
  }' | jq '.data.deployments.edges[0].node'
```

**Когда ИИ агент должен подключаться к Railway:**
1. **После merge в staging** - для проверки статуса деплоя (wait ~2 мин)
2. **После успешного деплоя staging** - для проверки логов и health
3. **После merge в main** - для проверки статуса production деплоя
4. **После production деплоя** - для финальной проверки логов и health

**Environment IDs:**
- Staging: `9e15b55d-8220-4067-a47e-191a57c2bcca`
- Production: `2eee50d8-402e-44bf-9035-8298efef91bc`

**Service IDs:**
- Web: `29038dc3-c812-4b0d-9749-23cdd1b91863`
- Worker: `aeb9b998-c05b-41a0-865c-5b58b26746d2`
- Beat: `4e7336b6-89b9-4385-b0d2-3832cab482e0`
- Redis: `e8f15267-93da-42f2-a1da-c79ad8399d0f`

⚠️ **ЗАПРЕЩЕНО:** `railway deploy`, `railway up`, `railway redeploy` - код выкатывается ТОЛЬКО через GitHub Actions!

### 2.3 Supabase (PostgreSQL + Storage)
- Подключение к БД:
  `postgresql://postgres.eqgcrggbksouurhjxvzs:3ZVyk8a27nT4lHMh@aws-1-eu-north-1.pooler.supabase.com:5432/postgres`
- REST/Storage:
  - `SUPABASE_URL = https://eqgcrggbksouurhjxvzs.supabase.co`
  - `SUPABASE_SERVICE_ROLE_KEY = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVxZ2NyZ2dia3NvdXVyaGp4dnpzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTUxNDc5OSwiZXhwIjoyMDcxMDkwNzk5fQ.MPnkmxqucGWASbifVoBN80d4k_fIGeo0XTWWdNf1AU0`
  - `SUPABASE_BUCKET = video`
  - `SUPABASE_VIDEO_BUCKET = video_veo3`
- CLI:
  ```bash
  supabase login --token $SUPABASE_SERVICE_ROLE_KEY
  supabase db remote connect --db-url "$DATABASE_URL"
  ```
- Для REST-запросов добавляйте заголовки `apikey` и `Authorization` со значением сервисного ключа.

### 2.4 Telegram-боты
- Тестовый бот (staging): `@test_integer_ai_bot`, токен `7869572156:AAGZ1_83Vpuw8wg7ma1HhEpTnxFfjTHh3M4`.
- Продакшн бот: `@tg_nanobanana_bot` (название условно), токен `8238814681:AAEXaV8GPwsFne2sr8uTOcgCWcdDs0k3Ewk`.
- Никогда не путайте токены между окружениями. В staging проверяются новые функции; production — только после успешного релиза.

### 2.5 Обязательные переменные окружения
Минимальный набор для каждого окружения (хранится в Railway variables):
- `TELEGRAM_BOT_TOKEN`, `TG_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`.
- `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`, `SUPABASE_VIDEO_BUCKET`.
- `REDIS_URL` (Railway выдаёт автоматически, но проконтролируйте).
- `SENTRY_DSN`, `SENTRY_ENVIRONMENT` (опционально, но желательно для мониторинга).
- `GEMINI_API_KEY` + `USE_VERTEX_AI` / `GOOGLE_APPLICATION_CREDENTIALS` при необходимости.
- `RAILWAY_API_TOKEN` для workflow, `TELEGRAM_NOTIFY_TOKEN`, `TELEGRAM_NOTIFY_CHAT_ID` для уведомлений о релизах.

## 3. Правила работы ИИ агента

### 3.1 Основные принципы
1. Всю коммуникацию ведите только на русском языке. Комментарии в коде пишите исключительно на русском.
2. Выполняйте задачи максимально самостоятельно, используя доступы и инструкции из этого файла. Не перекладывайте работу на человека без веской причины.
3. Каждое значимое изменение фиксируйте отдельным коммитом и пушьте в GitHub. Так проще найти и откатить правки.
4. Работайте пошагово: делайте один шаг, фиксируйте результат, пишите краткий отчёт, затем переходите к следующему.
5. После каждого шага вносите запись в `Документация/AGENTS_LOGS.md` (дата, ветка, сделанное действие, ссылка на PR/коммит).
6. Если требований не хватает — уточните детали до начала работы, чтобы не переделывать.
7. Не делайте ничего «на своё усмотрение». Все изменения (фичи, настройки, миграции) согласовывайте с человеком и следуйте полученным инструкциям.

### 3.2 Рабочий процесс
- Перед началом работы синхронизируйтесь с нужной веткой (`staging` для фич, `main` для хотфиксов).
- Стройте план действий и проговаривайте его.
- При работе с кодом запускайте доступные тесты/линтеры. Если тесты не предусмотрены, объясните, как вручную проверили результат.
- Всегда проверяйте логи (web, worker, beat) и `/api/health` перед тем как отчитаться об успехе.
- Соблюдайте чистоту репозитория: не коммитьте артефакты (`__pycache__`, `.env`, дампы`).

### 3.3 Отчётность и диагностика
- Для каждого релиза фиксируйте: какие ветки задействованы, какие проверки прошли, какие команды Railway/`curl` выполнялись.
- Если пайплайн сломался, собирайте факты (ID workflow, выдержки из логов, команды) и прикладывайте в отчёт человеку.
- Никогда не скрывайте ошибки: лучше сразу описать проблему и предложить план её устранения.

### 3.4 Безопасность
- Не публикуйте токены за пределами приватного репозитория.
- Не запускайте `railway up/deploy` руками, не редактируйте переменные окружения без необходимости.
- Rollback или git revert выполняйте только после подтверждения человека или если этого требует автоматический workflow.

### 3.5 Обязательная работа в отдельном worktree (для каждого агента)
1. В основном каталоге (`pwd` → `.../INTEGER:VSCODE`) обновите staging: `git fetch origin staging`.
2. Посмотрите занятые worktree, чтобы выбрать уникальное имя: `git worktree list`.
3. Создайте worktree с уникальным и понятным именем (не совпадающим с существующими): `git worktree add ../<уникальное-имя> -b feature/<уникальное-имя> origin/staging`.
4. Перейдите в свой worktree: `cd ../<уникальное-имя>`.
5. Подтвердите для человека, что находитесь в нём, выполнив и показав вывод:
   - `pwd` → должен быть `.../<уникальное-имя>`
   - `git rev-parse --show-toplevel` → `.../<уникальное-имя>`
   - `git worktree list` → в списке есть строка с вашим worktree
6. Сообщите: «Работаю в <уникальное-имя> на ветке feature/<уникальное-имя>, готов к работе». Все дальнейшие команды выполняйте из этого worktree, чтобы не мешать другим агентам.

## 4. 🚀 Fast Track Deployment Pipeline

Главный принцип: **"Минимум бюрократии на Staging, Максимум надежности на Production".**

### 4.1 Подготовка: Настройка окружения

**Перед началом работы агент должен:**

```bash
# 1. Получите токены у человека
# - GitHub PAT: ghp_XXXX...
# - Railway API Token: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# 2. Авторизация в GitHub (через GH_TOKEN для параллельной работы)
export GH_TOKEN="<ваш_github_pat>"
export RAILWAY_API_TOKEN="<ваш_railway_api_token>"

# Проверка GitHub авторизации (токен автоматически используется)
gh auth status

# 3. Авторизация в Railway
railway login  # Откроется браузер
railway whoami  # Проверка: Logged in as Berik
railway link --project 866bc61a-0ef1-41d1-af53-26784f6e5f06

# 4. Синхронизация с staging
git checkout staging
git pull origin staging

# 5. Создание feature ветки
git checkout -b feature/<название-задачи>
```

**💡 Почему GH_TOKEN вместо gh auth login?**
- ✅ Несколько агентов могут работать параллельно без конфликтов
- ✅ Не требует записи в `~/.config/gh/hosts.yml`
- ✅ Токен изолирован в переменной окружения каждого агента

### 4.2 Разработка и Тестирование

**Агент пишет код и проверяет локально:**

```bash
# 1. Внесение изменений
# ... пишем код ...

# 2. Локальная проверка (опционально)
python manage.py test
flake8 .

# 3. Коммит изменений
git add .
git commit -m "feat: описание изменения"
```

### 4.3 Staging Deployment (Автоматический, 2-3 минуты)

#### Шаг 1: Финальная синхронизация и Push

```bash
# Подтягиваем свежие изменения из staging
git pull origin staging

# Пушим feature ветку
git push origin feature/<название-задачи>
```

**Что происходит автоматически:**
- 🤖 GitHub Actions создает PR `feature/* → staging` (workflow: `pr-from-feature.yml`)
- 🔍 Запускается **Lint Check** (только синтаксис, ~30-60 сек)
- ✅ Если линтер прошел → `auto-merge-staging.yml` автоматически мержит PR (squash)
- 🚀 Railway видит изменения в `staging` и запускает deploy (~2 мин)

#### Шаг 2: Мониторинг Staging Deployment

**Агент подключается к GitHub для проверки статуса:**

```bash
# Проверка статуса PR (найти номер своего PR)
gh pr list --head feature/<название-задачи> --state all

# Проверка статуса CI
gh pr view <PR_NUMBER> --json state,mergeable,statusCheckRollup

# Ожидание: state = "MERGED", все checks = "SUCCESS"
```

**Ожидание Railway deployment (~2 минуты):**

```bash
# Подождать завершения деплоя
sleep 120

# Проверка статуса через Railway GraphQL API
curl -s -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { deployments(input: { environmentId: \"9e15b55d-8220-4067-a47e-191a57c2bcca\", serviceId: \"29038dc3-c812-4b0d-9749-23cdd1b91863\" }) { edges { node { status createdAt } } } }"
  }' | jq '.data.deployments.edges[0].node'

# Ожидаемый результат: "status": "SUCCESS"
```

#### Шаг 3: Проверка Staging Health

**Агент подключается к Railway для проверки логов:**

```bash
# Проверка статуса всех сервисов
for service_id in "29038dc3-c812-4b0d-9749-23cdd1b91863" "aeb9b998-c05b-41a0-865c-5b58b26746d2" "4e7336b6-89b9-4385-b0d2-3832cab482e0"; do
  service_name=$(case $service_id in 
    "29038dc3-c812-4b0d-9749-23cdd1b91863") echo "web" ;;
    "aeb9b998-c05b-41a0-865c-5b58b26746d2") echo "worker" ;;
    "4e7336b6-89b9-4385-b0d2-3832cab482e0") echo "beat" ;;
  esac)
  
  deploy_status=$(curl -s -X POST https://backboard.railway.app/graphql/v2 \
    -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"query { deployments(input: { environmentId: \\\"9e15b55d-8220-4067-a47e-191a57c2bcca\\\", serviceId: \\\"$service_id\\\" }) { edges { node { status } } } }\"}" | jq -r '.data.deployments.edges[0].node.status')
  
  echo "$service_name: $deploy_status"
done

# Ожидаемый результат: все сервисы "SUCCESS"
```

**Проверка логов (опционально, для диагностики):**

```bash
railway logs --service web --tail 50
railway logs --service worker --tail 30
railway logs --service beat --tail 20
```

#### Шаг 4: Отчет человеку

**Агент сообщает:**

```
✅ Staging Deployment SUCCESS

📋 Детали:
- PR #<NUMBER>: merged into staging
- Railway deployment: SUCCESS (web/worker/beat)
- Deployed at: <timestamp>

🧪 Staging готов к ручному тестированию в @test_integer_ai_bot

Ожидаю вашего подтверждения для деплоя в production.
```

**Что если два агента запушили одновременно?**
- GitHub обработает PR-ы последовательно (concurrency control)
- Railway задеплоит кумулятивный результат обоих изменений
- Последний PR будет "топовым" в STAGING_DEPLOYED.json

### 4.4 Production Release (Контролируемый, ~10-15 минут)

#### Шаг 1: Получение команды от человека

**Человек тестирует staging и дает команду:**
```
"Все ок, даю добро на деплой в production"
```

#### Шаг 2: Создание Release PR

**Агент подключается к GitHub для создания Release PR:**

```bash
# Запуск workflow через GitHub CLI
gh workflow run create-release-pr.yml \
  -f release_title="Release: <краткое описание изменений>" \
  -f release_notes="Список изменений:
- feat: <описание фичи 1>
- fix: <описание фикса 1>
- ..."
```

**Что происходит автоматически:**
- 🤖 Workflow создает PR `staging → main`
- 🔍 Запускается **Full CI** (lint + unit tests + integration tests, ~5-10 мин)
- ⏸️ **Auto-merge ОТКЛЮЧЕН** - мерджит только человек

#### Шаг 3: Мониторинг Release PR

**Агент проверяет статус CI через GitHub:**

```bash
# Найти Release PR
gh pr list --base main --head staging

# Проверка статуса CI и mergeable
gh pr view <PR_NUMBER> --json state,mergeable,statusCheckRollup,mergeStateStatus

# Ожидаемый результат:
# - mergeable: "MERGEABLE"
# - mergeStateStatus: "CLEAN"
# - все statusCheckRollup: "SUCCESS"
```

**Ожидание завершения CI (~5-10 минут):**

```bash
# Проверять статус каждые 30 секунд
while true; do
  status=$(gh pr view <PR_NUMBER> --json statusCheckRollup --jq '.statusCheckRollup[] | select(.name=="CI / full-test") | .status')
  echo "CI Status: $status"
  
  if [ "$status" = "COMPLETED" ]; then
    conclusion=$(gh pr view <PR_NUMBER> --json statusCheckRollup --jq '.statusCheckRollup[] | select(.name=="CI / full-test") | .conclusion')
    echo "CI Conclusion: $conclusion"
    break
  fi
  
  sleep 30
done
```

#### Шаг 4: Обработка результатов CI

**Если CI FAILED:**

```bash
# 1. Изучить логи CI
gh pr checks <PR_NUMBER>

# 2. Исправить проблемы в staging
git checkout staging
git pull origin staging
# ... исправления ...
git add . && git commit -m "fix: <описание фикса>"
git push origin staging

# 3. Закрыть старый Release PR
gh pr close <PR_NUMBER>

# 4. Создать новый Release PR (повторить Шаг 2)
```

**Если CI SUCCESS:**

```bash
# Проверить что нет конфликтов
gh pr view <PR_NUMBER> --json mergeable,mergeStateStatus

# Если mergeable = "CONFLICTING" - нужно разрешить конфликты
# Если mergeable = "MERGEABLE" - сообщить человеку
```

#### Шаг 5: Отчет человеку о готовности PR

**Агент сообщает:**

```
✅ Release PR готов к merge

📋 PR #<NUMBER>: staging → main
🔍 CI Status: ALL PASSED
- Lint: ✅
- Unit Tests: ✅
- Integration Tests: ✅

✅ Mergeable: CLEAN (нет конфликтов)

📝 Release Notes:
<список изменений из PR description>

🔒 Ожидаю вашего ручного merge в GitHub.
```

#### Шаг 6: Человек мерджит PR

**Человек открывает PR в GitHub и нажимает "Squash and Merge"**

**ИЛИ через CLI (только человек):**
```bash
gh pr merge <PR_NUMBER> --squash
```

#### Шаг 7: Мониторинг Production Deployment

**Агент подключается к GitHub для подтверждения merge:**

```bash
# Проверка что PR смержен
gh pr view <PR_NUMBER> --json state,mergedAt,mergedBy

# Ожидаемый результат: state = "MERGED"
```

**Ожидание Railway production deploy (~2-3 минуты):**

```bash
# Подождать завершения деплоя
sleep 120

# Проверка статуса production deployment
curl -s -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { deployments(input: { environmentId: \"2eee50d8-402e-44bf-9035-8298efef91bc\", serviceId: \"29038dc3-c812-4b0d-9749-23cdd1b91863\" }) { edges { node { status createdAt meta } } } }"
  }' | jq '.data.deployments.edges[0].node'
```

**Проверка статуса всех production сервисов:**

```bash
for service_id in "29038dc3-c812-4b0d-9749-23cdd1b91863" "aeb9b998-c05b-41a0-865c-5b58b26746d2" "4e7336b6-89b9-4385-b0d2-3832cab482e0"; do
  service_name=$(case $service_id in 
    "29038dc3-c812-4b0d-9749-23cdd1b91863") echo "web" ;;
    "aeb9b998-c05b-41a0-865c-5b58b26746d2") echo "worker" ;;
    "4e7336b6-89b9-4385-b0d2-3832cab482e0") echo "beat" ;;
  esac)
  
  deploy_status=$(curl -s -X POST https://backboard.railway.app/graphql/v2 \
    -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"query { deployments(input: { environmentId: \\\"2eee50d8-402e-44bf-9035-8298efef91bc\\\", serviceId: \\\"$service_id\\\" }) { edges { node { status } } } }\"}" | jq -r '.data.deployments.edges[0].node.status')
  
  echo "$service_name: $deploy_status"
done
```

#### Шаг 8: Финальный отчет

**Если Production Deployment SUCCESS:**

```
🎉 Production Deployment SUCCESS

📋 Детали:
- PR #<NUMBER>: merged into main by <user>
- Railway deployment: SUCCESS (web/worker/beat)
- Deployed at: <timestamp>
- Commit: <commit_hash>

✅ Production bot @tg_nanobanana_bot работает корректно

📊 Все сервисы:
- web: SUCCESS
- worker: SUCCESS
- beat: SUCCESS

Релиз успешно завершен! 🚀
```

**Если Production Deployment FAILED:**

```bash
# 1. Собрать логи ошибок
railway logs --service web --tail 100 > production_error.log
railway logs --service worker --tail 50 >> production_error.log

# 2. Сообщить человеку об ошибке с логами
# 3. Предложить rollback (ТОЛЬКО после подтверждения человека)

# Rollback (если человек подтвердил):
git checkout main
git pull origin main
git revert HEAD --no-edit
git push origin main
```

### 4.5 Временные рамки Fast Track Pipeline

| Этап | Время | Автоматизация |
|------|-------|---------------|
| **Staging Deployment** | **~2-3 мин** | **Полностью автоматический** |
| - Feature push → PR creation | ~10 сек | Auto |
| - Lint check | ~30-60 сек | Auto |
| - Auto-merge | ~10 сек | Auto |
| - Railway deploy | ~2 мин | Auto |
| **Ручное тестирование staging** | По необходимости | Человек |
| **Production Release** | **~10-15 мин** | **Полуавтоматический** |
| - Release PR creation | ~10 сек | Auto (по команде) |
| - Full CI (lint + tests) | ~5-10 мин | Auto |
| - Human review & merge | По необходимости | Человек |
| - Railway production deploy | ~2 мин | Auto |

**Итого:** От feature push до production ~15-20 минут (при условии что staging тестирование прошло быстро)

### 4.6 Критические правила Fast Track Pipeline

#### ❌ НИКОГДА НЕ ДЕЛАЙТЕ:

1. **НЕ мерджите PR в main автоматически**
   - Только человек принимает решение о production release
   - Использование `gh pr merge --auto` для main запрещено

2. **НЕ пушьте напрямую в staging или main**
   - Ветки защищены branch protection rules
   - Все изменения только через PR

3. **НЕ используйте `railway deploy/up/redeploy`**
   - Код выкатывается ТОЛЬКО через GitHub Actions
   - Railway CLI используется только для мониторинга (logs, status)

4. **НЕ делайте rollback без подтверждения человека**
   - Rollback - это критическая операция
   - Всегда сначала сообщите о проблеме и дождитесь команды

5. **НЕ коммитьте токены и секреты**
   - GitHub PAT не должен попасть в репозиторий
   - Railway API Token хранится только в GitHub Secrets

#### ✅ ВСЕГДА ДЕЛАЙТЕ:

1. **Синхронизируйтесь перед началом работы**
   ```bash
   git checkout staging && git pull origin staging
   ```

2. **Проверяйте статус CI перед переходом к следующему шагу**
   ```bash
   gh pr checks <PR_NUMBER>
   ```

3. **Ждите завершения Railway deployment (~2 мин)**
   - Не спешите проверять логи сразу после push
   - Используйте `sleep 120` или GraphQL API для проверки статуса

4. **Сообщайте человеку о каждом важном этапе**
   - После staging deployment
   - После создания Release PR
   - После production deployment

5. **Записывайте все действия в AGENTS_LOGS.md**
   - Дата, задача, действие, ссылка на PR/коммит
   - Результаты проверок (CI status, Railway status, health checks)

### 4.7 FAQ и Troubleshooting

**Q: PR не создался автоматически после push feature ветки**

A: Проверьте:
```bash
# 1. Проверка workflow
gh run list --workflow=pr-from-feature.yml --limit 5

# 2. Создайте PR вручную
gh pr create --base staging --head feature/<название> --title "feat: <описание>" --body "Auto-generated PR"
```

**Q: Auto-merge не сработал после успешного линтера**

A: Проверьте:
```bash
# 1. Статус всех checks
gh pr view <PR_NUMBER> --json statusCheckRollup

# 2. Mergeable status
gh pr view <PR_NUMBER> --json mergeable

# 3. Если все зеленое - смерджите вручную
gh pr merge <PR_NUMBER> --squash
```

**Q: Railway deployment завис в статусе "BUILDING"**

A: Проверьте логи:
```bash
# 1. Логи build
railway logs --service web --tail 100

# 2. Проверка через GraphQL (может быть в очереди)
curl -s -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { deployments(input: { environmentId: \"9e15b55d-8220-4067-a47e-191a57c2bcca\", serviceId: \"29038dc3-c812-4b0d-9749-23cdd1b91863\" }) { edges { node { status buildLogs } } } }"}' | jq '.'

# 3. Если застрял >10 минут - сообщите человеку
```

**Q: CI tests failed на Release PR**

A: Исправьте проблемы:
```bash
# 1. Посмотрите детали ошибок
gh pr checks <PR_NUMBER>
gh run view <RUN_ID> --log-failed

# 2. Исправьте в staging
git checkout staging
git pull origin staging
# ... фиксы ...
git add . && git commit -m "fix: <описание>"
git push origin staging

# 3. Закройте старый PR и создайте новый
gh pr close <OLD_PR_NUMBER>
gh workflow run create-release-pr.yml -f release_title="..." -f release_notes="..."
```

**Q: Merge conflicts в Release PR**

A: Разрешите конфликты:
```bash
# 1. Создайте clean release branch
git checkout main
git pull origin main
git checkout staging
git pull origin staging
git checkout -b release/manual-clean
git merge origin/main -m "sync: merge main for clean release"

# 2. Разрешите конфликты вручную
# ... resolve conflicts ...
git add .
git commit -m "merge: resolve conflicts"
git push origin release/manual-clean

# 3. Создайте PR через UI
# staging → main (но используя release/manual-clean как source)
```

**Q: Production deployment failed - что делать?**

A: **СООБЩИТЕ ЧЕЛОВЕКУ НЕМЕДЛЕННО:**
```
🚨 Production Deployment FAILED

📋 PR #<NUMBER>: merged into main
❌ Railway deployment: FAILED
🔍 Service: <web/worker/beat>
📝 Error: <краткое описание из логов>

📎 Полные логи:
<вставьте последние 50 строк из railway logs>

⚠️ Предлагаю rollback на предыдущую версию.
Ожидаю вашего подтверждения.
```

## 5. Журнал действий (AGENTS_LOGS.md)

После каждого staging deployment агент должен добавить запись в `Документация/AGENTS_LOGS.md`:

```markdown
## [2025-11-19] Staging Deployment: <описание задачи>

**Агент:** AI Agent Name  
**Ветка:** feature/<название>  
**PR:** #<NUMBER>  
**Коммит:** <commit_hash>

### Выполненные действия:
1. Создана feature ветка из staging
2. Внесены изменения: <краткое описание>
3. Push в GitHub → автоматическое создание PR
4. Lint Check: ✅ PASSED
5. Auto-merge: ✅ SUCCESS
6. Railway deployment: ✅ SUCCESS (web/worker/beat)

### Проверки:
- GitHub PR: https://github.com/berikbekishev-source/tg-nanobanana/pull/<NUMBER>
- Railway status: SUCCESS
- Deployed at: <timestamp>
- Health check: OK

### Результат:
✅ Staging готов к ручному тестированию.
Уведомлен человек: <дата/время>
```

После каждого production release:

```markdown
## [2025-11-19] Production Release: <описание релиза>

**Release PR:** #<NUMBER>  
**Merged by:** <username>  
**Merge commit:** <commit_hash>

### Изменения в релизе:
- feat: <описание фичи 1>
- fix: <описание фикса 1>
- ...

### CI Results:
- Lint: ✅ PASSED
- Unit Tests: ✅ PASSED
- Integration Tests: ✅ PASSED

### Production Deployment:
- Railway status: ✅ SUCCESS (web/worker/beat)
- Deployed at: <timestamp>
- Health check: OK

### Результат:
🎉 Production release успешно завершен!
```

---

Соблюдайте эти правила, оперативно обновляйте журнал действий и не забывайте согласовывать любые нетипичные шаги. Это гарантирует предсказуемые деплои и быстрый отклик на инциденты.
