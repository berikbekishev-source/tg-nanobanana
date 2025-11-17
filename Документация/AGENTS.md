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
- Перед каждым деплоем бронируйте стенд через `STAGING_STATUS.md` (см. гайд ниже) и освобождайте его сразу после проверок.
- Стройте план действий и проговаривайте его.
- При работе с кодом запускайте доступные тесты/линтеры. Если тесты не предусмотрены, объясните, как вручную проверили результат.
- Всегда проверяйте логи (web, worker, beat) и `/api/health` перед тем как отчитаться об успехе.
- Соблюдайте чистоту репозитория: не коммитьте артефакты (`__pycache__`, `.env`, дампы`).

### 3.3 Отчётность и диагностика
- Для каждого релиза фиксируйте: какие ветки задействованы, какие проверки прошли, какие команды Railway/`curl` выполнялись.
- Для деплоя на `staging` обязательно записывайте в `Документация/AGENTS_LOGS.md`: время бронирования, PR/коммит, команды (`railway status/logs`, `curl /api/health`), результат и факт уведомления человека.
- Если пайплайн сломался, собирайте факты (ID workflow, выдержки из логов, команды) и прикладывайте в отчёт человеку.
- Никогда не скрывайте ошибки: лучше сразу описать проблему и предложить план её устранения.

### 3.4 Безопасность
- Не публикуйте токены за пределами приватного репозитория.
- Не запускайте `railway up/deploy` руками, не редактируйте переменные окружения без необходимости.
- Rollback или git revert выполняйте только после подтверждения человека или если этого требует автоматический workflow.

### 3.5 Скрипты для быстрого деплоя
- `bin/staging-status reserve|release` — обновляет `STAGING_STATUS.md`, следит, чтобы стенд не заняли параллельно, и автоматически создаёт коммиты `chore: занял/освободил staging`.
- `bin/deploy-staging <PR#>` — проверяет, что PR направлен в `staging`, убеждается в зелёном CI, мержит `--squash --admin`, запускает `railway status`, логи web/worker/beat и `curl "$STAGING_BASE_URL/api/health"`. Весь цикл занимает ~2 минуты.
- Перед началом сессии выполните:
  ```bash
  gh auth status || echo "$GITHUB_PAT" | gh auth login --with-token
  export RAILWAY_TOKEN="47a20fbb-1f26-402d-8e66-ba38660ef1d4"
  railway login --token "$RAILWAY_TOKEN" && railway link --project 866bc61a-0ef1-41d1-af53-26784f6e5f06
  export STAGING_BASE_URL="https://web-staging-70d1.up.railway.app"
  ```
  Тогда оба скрипта работают без лишних вопросов, и деплой на `staging` укладывается в ≤5 минут.

## 4. Правила работы с GitHub и Railway

### 4.1 Ветки и защита
| Ветка | Назначение | Правила |
|-------|------------|---------|
| `feature/*` | Работа ИИ-агента над задачей | Ветка создаётся из `staging`. Пуши запускают `CI and Smoke` и автогенерацию PR в `staging`.
| `staging` | Тестовое окружение и тестовый бот | Защищена. Merge делается **вручную через `gh pr merge --squash`** только после зелёного CI и бронирования стенда в `STAGING_STATUS.md`.
| `main` | Продакшн | Защищена. Merge разрешён только человеку через веб-интерфейс GitHub; авто-merge отключён.

### 4.2 GitHub Actions
- `pr-from-feature.yml` — создаёт/обновляет PR `feature/* → staging` сразу после push.
- `CI and Smoke` — линтеры, тесты, сборка и смоки. Запускается на push в feature, на PR к `staging`, на push в `staging` и `main`.
- `auto-approve.yml` — выполняет машинное ревью и ставит approve от `github-actions[bot]`, но **не включает auto-merge**.
- `auto-merge-staging.yml` — отключён. Merge выполняет агент вручную через CLI после бронирования стенда.
- `setup-branch-protection.yml` — поддерживает настройки защищённых веток (идёт в режиме `continue-on-error`, не ломайте его).
- `post-deploy-monitor.yml` — после успешного push в `main` собирает Railway логи, пингует `/api/health`, при сбое делает rollback/`git revert` и шлёт уведомление в Telegram.

### 4.3 Цикл feature → staging
1. Создайте ветку `feature/<task>` от `staging`, пуш — создаст PR `feature → staging`; дождитесь зелёного `CI / build-test`.
2. Забронируйте стенд через ChatOps в PR: `/reserve-staging 15m reason: <текст>` — бот обновит `STAGING_STATUS.md` в `staging` коммитом `chore(staging): занял стенд`.
3. Выполните `/deploy-staging` — бот сам смержит PR (squash), подождёт Railway до `SUCCESS`, снимет логи/health и оставит отчёт.
4. Освободите стенд `/release-staging` — бот обновит `STAGING_STATUS.md` на «Свободен» и допишет журнал.
5. Сообщите человеку: “Staging готов, проверил status/logs/health”.

### 4.4 Проверка стейджинга
- Быстрее всего использовать ChatOps `/deploy-staging` — бот сам соберёт Railway статус, снимет логи `web/worker/beat` (при наличии CLI) и сделает `curl "$STAGING_BASE_URL/api/health"`. Итог попадёт в `Документация/AGENTS_LOGS.md`.
- Команды для проверки:
  ```bash
  railway status --json | jq '.services.edges[].node.serviceInstances.edges[] | select(.node.environmentId=="9e15b55d-8220-4067-a47e-191a57c2bcca") | {serviceName: .node.serviceName, status: .node.latestDeployment.status, commit: .node.latestDeployment.meta.commitHash}'
  railway logs --service web --tail 200
  railway logs --service worker --tail 200
  curl -sf "$STAGING_BASE_URL/api/health"
  ```
- Эти проверки выполняет ИИ-агент. Как только они зелёные, агент уведомляет человека.
- Ручные смоки в тестовом Telegram-боте `@test_integer_ai_bot` проводит только человек. Агент обязан предоставить ссылку на коммит и список проверок.
- Все результаты (команды, timestamp, статус стенда) фиксируйте в `AGENTS_LOGS` и упомянутом отчёте.
> Комментарий 2025-11-17: во время текущего теста деплоя дополнительно сохранил полный вывод `bin/deploy-staging` и `railway status` в журнале, чтобы следующий агент видел последовательность шагов без поиска.

### 4.8 ChatOps и защита веток
- Doc-only коммиты в `staging` (только `STAGING_STATUS.md` и `Документация/*`) выполняет `github-actions[bot]`/`ADMIN_GH_TOKEN`.
- Проверки `STAGING_BUSY`/`STAGING_FREE` выставляются ботом на последний коммит `staging` для видимости занятости стенда.
- TTL брони — по умолчанию 15 минут; авто-освобождение по крону.

### 4.5 Продвижение в main и прод-окружение
1. Никакого автоматического деплоя в `main` нет. После ручного теста человек явно даёт добро.
2. Получив добро, агент создаёт PR `staging → main` (при необходимости через временную ветку `release/...`).
3. `CI and Smoke` снова гоняет тесты. Merge выполняет **только человек** через кнопку GitHub (auto-merge выключен). Агент ждёт подтверждения.
4. Merge в `main` → Railway production автодеплой. Следите за run `CI and Smoke` на push в `main` и за логами Railway.
5. Workflow `post-deploy-monitor` проверяет `/api/health` и логи (web/worker/beat). При сбое он сам делает rollback через Railway API и `git revert`, а затем отправляет сообщение в Telegram. Агент обязан проанализировать уведомление и подготовить отчёт.
6. Никогда не перезапускайте push-ран `CI and Smoke` на `main`, если он уже завершился успехом: повторный rerun создаёт новый check со статусом `failure`, и Railway пометит деплой как `skipped`. Для повторного релиза делайте новый коммит.
7. После успешного релиза подтяните `main` в `staging`, чтобы ветки не расходились.

### 4.6 Действия при сбоях
- **Авто-PR завис** — проверьте `gh pr checks <num>`, если все проверки зелёные, поставьте approve и смержите вручную. Если проверки красные, разбирайтесь в логах, фиксите, пушьте обновление.
- **CI упал** — изучите логи job, исправьте код и повторите push. Не отключайте проверки.
- **Railway деплой не стартовал** — посмотрите `railway status --json` и `Railway dashboard`. Частая причина — нет зелёного `CI` на соответствующем коммите; прогоните `CI` на нужной ветке заново.
- **Staging/production нездоров** — соберите логи (`railway logs`), проверьте `/api/health`, при критических ошибках уведомите человека и предложите rollback (только после подтверждения).

### 4.7 Работа с Railway
- Допустимые команды: `status`, `logs`, `variables`, `deployment list`, `run` для чтения. Нельзя выполнять `deploy`, `up`, `rollback` самостоятельно без явного распоряжения или автоматического workflow.
- Чтобы убедиться, что нужный коммит задеплоился, используйте:
  ```bash
  railway status --json | jq '.services.edges[].node.serviceInstances.edges[] | {serviceName: .node.serviceName, env: .node.environmentId, commit: .node.latestDeployment.meta.commitHash}'
  ```
- Для health-check используйте `/api/health` соответствующего домена (`STAGING_BASE_URL`, `PRODUCTION_BASE_URL`).
- Rollback вручную допускается только по указанию человека. В штатном режиме rollback выполняет workflow `post-deploy-monitor`.

---
Соблюдайте эти правила, оперативно обновляйте журнал действий и не забывайте согласовывать любые нетипичные шаги. Это гарантирует предсказуемые деплои и быстрый отклик на инциденты.
## Быстрый путь (ChatOps)
- Резерв стенда: в комментарии к PR напишите `/reserve-staging 15m reason: <что выкатываю>`
- Деплой на staging: `/deploy-staging` — merge (squash) в `staging`, ожидание Railway и смоки — бот сделает сам и оставит отчёт
- Освобождение стенда: `/release-staging`

Замечания:
- Бронь и журнал вносятся ботом прямо в ветку `staging` коммитами по `STAGING_STATUS.md` и `Документация/AGENTS_LOGS.md` (doc-only, исключение защиты ветки)
- Время полного цикла: обычно 2–5 минут: merge (<10с) → Railway (1–3 мин) → health (<10с)
