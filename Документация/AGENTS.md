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

### 2.1 GitHub
- Репозиторий: `git@github.com:berikbekishev-source/tg-nanobanana.git` (доступ по SSH) или HTTPS.
- Personal access token (classic) хранится у человека и в защищённом хранилище (1Password). Перед началом работы попросите его и установите в `GITHUB_PAT`, не коммитьте токены в репозиторий.
- Авторизация в GitHub CLI:
  ```bash
  echo "$GITHUB_PAT" | gh auth login --with-token
  ```
- Критичные секреты репозитория: `ADMIN_GH_TOKEN`, `RAILWAY_API_TOKEN`, `PRODUCTION_BASE_URL`, `TELEGRAM_NOTIFY_TOKEN`, `TELEGRAM_NOTIFY_CHAT_ID`. Не меняйте их названия.

### 2.2 Railway
- API токен / CLI токен: `47a20fbb-1f26-402d-8e66-ba38660ef1d4`.
- Быстрый вход:
  ```bash
  export RAILWAY_TOKEN="47a20fbb-1f26-402d-8e66-ba38660ef1d4"
  railway login --token $RAILWAY_TOKEN
  railway link --project 866bc61a-0ef1-41d1-af53-26784f6e5f06
  ```
- Основные команды (допустимы только для диагностики):
  ```bash
  railway status --json
  railway logs --service web --tail 200
  railway logs --service worker --tail 200
  railway variables --service web
  ```
- GraphQL API: `https://backboard.railway.app/graphql/v2` (Bearer `RAILWAY_API_TOKEN`). Используйте его для автоматических проверок и просмотра истории деплоев.
- Любые действия, меняющие код (ручной deploy, up, redeploy) запрещены — код выкатывается только через GitHub Actions.

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
- После деплоя на `staging` записывайте в `Документация/AGENTS_LOGS.md`: дату, PR/коммит, команды проверки, результат и факт уведомления человека.
- Если пайплайн сломался, собирайте факты (ID workflow, выдержки из логов, команды) и прикладывайте в отчёт человеку.
- Никогда не скрывайте ошибки: лучше сразу описать проблему и предложить план её устранения.

### 3.4 Безопасность
- Не публикуйте токены за пределами приватного репозитория.
- Не запускайте `railway up/deploy` руками, не редактируйте переменные окружения без необходимости.
- Rollback или git revert выполняйте только после подтверждения человека или если этого требует автоматический workflow.

### 3.5 Настройка окружения
Перед началом работы выполните:
```bash
# GitHub CLI
gh auth status || echo "$GITHUB_PAT" | gh auth login --with-token

# Railway CLI
export RAILWAY_TOKEN="47a20fbb-1f26-402d-8e66-ba38660ef1d4"
railway login --token "$RAILWAY_TOKEN"
railway link --project 866bc61a-0ef1-41d1-af53-26784f6e5f06

# Environment URLs
export STAGING_BASE_URL="https://web-staging-70d1.up.railway.app"
export PRODUCTION_BASE_URL="<production-url>"
```

## 4. Правила работы с GitHub и Railway

### 4.1 Ветки и защита
| Ветка | Назначение | Правила |
|-------|------------|---------|
| `feature/*` | Работа ИИ-агента над задачей | Ветка создаётся из `staging`. Пуши запускают `CI and Smoke` и автогенерацию PR в `staging`.
| `staging` | Тестовое окружение и тестовый бот | Защищена. Merge выполняется **автоматически** через `auto-merge-staging.yml` после зелёного CI.
| `main` | Продакшн | Защищена. Merge разрешён **только человеку** через веб-интерфейс GitHub; авто-merge отключён.

### 4.2 GitHub Actions
- **`pr-from-feature.yml`** — создаёт/обновляет PR `feature/* → staging` сразу после push.
- **`CI and Smoke`** — линтеры, тесты, сборка и смоки. Запускается на push в feature, на PR к `staging`, на push в `staging` и `main`.
- **`auto-approve.yml`** — ставит approve от `github-actions[bot]` через `ADMIN_GH_TOKEN`.
- **`auto-merge-staging.yml`** — автоматически мержит PR в `staging` после успешного CI. Использует concurrency control и обновляет `STAGING_DEPLOYED.json` через GitHub Contents API.
- **`staging-health-check.yml`** — проверяет Railway deployment, health endpoint и обновляет `AGENTS_LOGS.md`.
- **`create-release-pr.yml`** — создаёт PR `staging → main` по команде человека.
- **`setup-branch-protection.yml`** — поддерживает настройки защищённых веток (режим `continue-on-error`).
- **`post-deploy-monitor.yml`** — после push в `main` проверяет здоровье production, при сбое делает rollback и шлёт уведомление в Telegram.

### 4.3 Цикл feature → staging (полностью автоматический)

**Шаг 1: Создание feature ветки**
```bash
git checkout staging
git pull origin staging
git checkout -b feature/<task>
```

**Шаг 2: Разработка и коммиты**
```bash
# Вносите изменения
git add .
git commit -m "feat: описание изменения"
```

**Шаг 3: Push**
```bash
git push origin feature/<task>
```
Автоматически создаётся PR `feature → staging` и запускается CI.

**Шаг 4: Ожидание CI (автоматически)**
- ✅ `CI and Smoke` должен пройти успешно
- ✅ `auto-approve.yml` поставит approve

**Шаг 5: Auto-merge (автоматически)**
После зелёного CI workflow `auto-merge-staging.yml`:
- Мержит PR в `staging` (squash merge)
- Обновляет `STAGING_DEPLOYED.json` с информацией о PR
- Создаёт коммит: `ci: update staging deployment marker (PR #N)`

**Шаг 6: Railway deployment (автоматически)**
Railway автоматически деплоит в staging environment (web/worker/beat).

**Шаг 7: Health check (автоматически)**
Workflow `staging-health-check.yml`:
- Проверяет Railway deployment status
- Проверяет `/api/health` endpoint
- Обновляет `AGENTS_LOGS.md`

**Шаг 8: Проверка агентом**
```bash
# Убедитесь что на staging ваш PR
git checkout staging && git pull origin staging
cat STAGING_DEPLOYED.json | jq '.pr'

# Проверьте Railway status
railway deployment list --service web | head -5

# Проверьте health
curl "$STAGING_BASE_URL/api/health"

# Проверьте логи
railway logs --service web --tail 50
```

**Шаг 9: Отчёт человеку**
Сообщите: "✅ Staging deployment завершён. PR #X смерджен, Railway status: SUCCESS, health: OK. Готов к ручному тестированию в @test_integer_ai_bot"

### 4.4 Проверка стейджинга

**Шаг 1: Проверьте маркер деплоя**
```bash
# Убедитесь что на staging именно ваш PR
git checkout staging && git pull origin staging
cat STAGING_DEPLOYED.json | jq '.'
# Проверьте что поле "pr" соответствует вашему PR номеру
```

**Шаг 2: Проверьте Railway status**
```bash
# Статус всех сервисов в staging
railway deployment list --service web | head -5

# Логи сервисов
railway logs --service web --tail 50
railway logs --service worker --tail 50
railway logs --service beat --tail 30
```

**Шаг 3: Health check**
```bash
curl -sf "$STAGING_BASE_URL/api/health"
# Ожидаемый ответ: {"ok": true}
```

**Шаг 4: Ручное тестирование**
- Агент предоставляет человеку информацию о deployment
- Человек тестирует в тестовом боте `@test_integer_ai_bot`
- Агент фиксирует результаты в `Документация/AGENTS_LOGS.md`

### 4.6 Deployment marker (STAGING_DEPLOYED.json)

Файл `STAGING_DEPLOYED.json` показывает какой PR сейчас задеплоен на staging:

```json
{
  "pr": 123,
  "title": "feat: добавил новую фичу",
  "actor": "agent-name",
  "deployed_at": "2025-11-18T10:00:00Z",
  "commit": "abc1234567...",
  "commit_short": "abc1234"
}
```

**Обновляется автоматически** через `auto-merge-staging.yml` используя GitHub Contents API (bypass branch protection).

**Перед тестированием агент должен проверить:**
```bash
cat STAGING_DEPLOYED.json | jq '.pr'
```

Если PR не совпадает с вашим — кто-то другой задеплоил позже.

### 4.5 Продвижение в main и прод-окружение

**Процесс полуавтоматический:** агент создаёт PR по команде, человек мержит вручную.

#### Шаг 1: Получение одобрения
1. После успешного тестирования на staging **отчитайтесь человеку**
2. **Дождитесь явной команды** на создание release PR
3. Никакого автоматического деплоя в `main` нет

#### Шаг 2: Создание Release PR (по команде человека)
После получения команды используйте GitHub Actions workflow:

```bash
# Через GitHub UI:
# Actions → Create Release PR (staging → main) → Run workflow
# Заполните: Release title, Release notes

# Или через gh CLI:
gh workflow run create-release-pr.yml \
  -f release_title="Release: описание изменений" \
  -f release_notes="Краткое описание что включено"
```

**Что происходит автоматически:**
- ✅ Workflow проверяет, что staging впереди main
- ✅ Автоматически создаёт/обновляет PR `staging → main`
- ✅ Добавляет чек-лист и описание изменений
- ⚠️ **Auto-merge ОТКЛЮЧЁН** - PR мержит только человек вручную

#### Шаг 3: Проверка CI
1. `CI and Smoke` автоматически запустится на PR
2. **Дождитесь зелёного статуса** всех проверок
3. **НЕ используйте** `gh pr merge --auto` - мердж только вручную

#### Шаг 4: Мердж человеком
**Человек вручную** проверяет PR и мержит через:
- GitHub UI: кнопка "Squash and merge"  
- Или CLI: `gh pr merge <PR_NUM> --squash` (НО только человек!)

**❌ Агент НЕ должен мерджить PR в main автоматически!**

#### Шаг 5: Автоматический production деплой
После мерджа человеком:
1. ✅ Push в `main` → Railway production автодеплой
2. ✅ `CI and Smoke` запускается на push в `main`
3. ✅ Railway автоматически деплоит все сервисы (web/worker/beat)

#### Шаг 6: Post-deploy мониторинг
Workflow `post-deploy-monitor` **автоматически**:
- Проверяет `/api/health` endpoint
- Проверяет логи Railway (web/worker/beat)
- **При сбое:** делает rollback (`git revert` + Railway API)
- Отправляет уведомление в Telegram

**Агент обязан:**
- Следить за выполнением workflow
- Проанализировать Telegram уведомление (если пришло)
- Подготовить отчёт о результатах production деплоя

#### Шаг 7: Постдеплой
После успешного production релиза:
```bash
# Подтяните main в staging, чтобы ветки не расходились
git checkout staging
git pull origin staging
git merge origin/main -m "sync: merge main back to staging"
git push origin staging
```

Обновите `Документация/AGENTS_LOGS.md` с результатами release.

---

### ⚠️ КРИТИЧНЫЕ ПРАВИЛА для production:

1. **❌ НИКОГДА не мерджите PR в main автоматически**
   - Только человек принимает решение о production release
   - Auto-merge для main отключён

2. **❌ НЕ перезапускайте CI на main после успеха**
   - Повторный rerun создаёт check со статусом `failure`
   - Railway пометит деплой как `skipped`
   - Для повторного релиза создайте новый коммит через PR

3. **❌ НЕ пушьте напрямую в main**
   - Ветка защищена
   - Все изменения только через PR

4. **✅ Следите за post-deploy-monitor**
   - Rollback происходит автоматически
   - Telegram уведомление требует анализа
   - Человек должен быть проинформирован о любых проблемах

### 4.7 Действия при сбоях
- **Авто-PR завис** — проверьте `gh pr checks <num>`, если все проверки зелёные, поставьте approve и смержите вручную. Если проверки красные, разбирайтесь в логах, фиксите, пушьте обновление.
- **CI упал** — изучите логи job, исправьте код и повторите push. Не отключайте проверки.
- **Railway деплой не стартовал** — посмотрите `railway status --json` и `Railway dashboard`. Частая причина — нет зелёного `CI` на соответствующем коммите; прогоните `CI` на нужной ветке заново.
- **Staging/production нездоров** — соберите логи (`railway logs`), проверьте `/api/health`, при критических ошибках уведомите человека и предложите rollback (только после подтверждения).

### 4.8 Работа с Railway
- Допустимые команды: `status`, `logs`, `variables`, `deployment list`, `run` для чтения. Нельзя выполнять `deploy`, `up`, `rollback` самостоятельно без явного распоряжения или автоматического workflow.
- Чтобы убедиться, что нужный коммит задеплоился, используйте:
  ```bash
  railway status --json | jq '.services.edges[].node.serviceInstances.edges[] | {serviceName: .node.serviceName, env: .node.environmentId, commit: .node.latestDeployment.meta.commitHash}'
  ```
- Для health-check используйте `/api/health` соответствующего домена (`STAGING_BASE_URL`, `PRODUCTION_BASE_URL`).
- Rollback вручную допускается только по указанию человека. В штатном режиме rollback выполняет workflow `post-deploy-monitor`.

---

## 5. Упрощённый staging пайплайн (актуально с ноября 2024)

### 5.1 Принцип работы
**Полностью автоматический пайплайн** без резервирования и ChatOps:

```
feature/task
    ↓ push
[CI and Smoke] ✅
    ↓ auto
PR создаётся → staging
    ↓ CI pass
Auto-merge (concurrency control)
    ↓
Railway auto-deploy
    ↓
Health-check + отчёт в PR
    ↓
✅ Готово для ручного теста
```

### 5.2 Ключевые компоненты
- **`STAGING_DEPLOYED.json`** — маркер деплоя, показывает какой PR на staging
- **`auto-merge-staging.yml`** — авто-мердж с concurrency group
- **`staging-health-check.yml`** — post-deploy проверки и логирование
- **GitHub Contents API** — bypass branch protection для автоматических обновлений

### 5.3 Concurrency control
```yaml
concurrency:
  group: staging-deploy
  cancel-in-progress: false
```

Все мерджи в staging выполняются **последовательно**. Если два агента пушат одновременно, PR-ы обрабатываются по очереди.

### 5.4 Временные рамки
| Этап | Время |
|------|-------|
| Push → PR creation | ~10 сек |
| CI checks | 3-5 мин |
| Auto-merge | ~10 сек |
| Railway deploy | 2-3 мин |
| Health check | ~10 сек |
| **Итого** | **~6-9 мин** |

---
Соблюдайте эти правила, оперативно обновляйте журнал действий и не забывайте согласовывать любые нетипичные шаги. Это гарантирует предсказуемые деплои и быстрый отклик на инциденты.
