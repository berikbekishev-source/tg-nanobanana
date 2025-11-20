# Инструкция для ИИ-агентов

<!-- Тестовое изменение для проверки процесса автоматического деплоя в staging -->

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
- Персональный token (classic) для CLI/API хранится у человека и дублирован в защищённом хранилище (1Password). Получите его перед началом работы и держите в переменной `GITHUB_PAT`, не сохраняйте в репозитории.
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
- Если пайплайн сломался, собирайте факты (ID workflow, выдержки из логов, команды) и прикладывайте в отчёт человеку.
- Никогда не скрывайте ошибки: лучше сразу описать проблему и предложить план её устранения.

### 3.4 Безопасность
- Не публикуйте токены за пределами приватного репозитория.
- Не запускайте `railway up/deploy` руками, не редактируйте переменные окружения без необходимости.
- Rollback или git revert выполняйте только после подтверждения человека или если этого требует автоматический workflow.

## 4. 🚀 Процесс Деплоя: Fast Track

Главный принцип: **"Минимум бюрократии на Staging, Максимум надежности на Production".**

### 4.1 Подготовка (Работа Агента)

Каждый агент работает в изолированной среде, чтобы не мешать другим.

1. **Start:** Агент запускается в режиме **Worktree** (Cursor).
2. **Sync:** Агент обязан начать с синхронизации: `git checkout staging && git pull origin staging`.
3. **Branch:** Создается ветка задачи: `git checkout -b feature/<название-задачи>`.
4. **Code:** Агент пишет код, проверяет его локально.

### 4.2 Доставка на Staging (Моментальная)

Мы убрали очереди и тяжелые тесты. Цель — как можно быстрее увидеть результат на сервере.

1. **Sync:** Перед финальным пушем попросить агента еще раз подтянуть staging к себе в ветку: `git pull origin staging`. Это убедит нас, что новая фича работает и с самыми свежими изменениями.
2. **Push:** Агент делает `git push origin feature/<название-задачи>`.
3. **Auto-PR:** GitHub Actions (`pr-from-feature.yml`) мгновенно создает Pull Request в staging.
4. **Light Check:** Запускается **только** Линтер (Syntax Check). Это занимает ~30-60 секунд.
5. **Auto-Merge:**
   - Если Линтер прошел (зеленый) ✅
   - И нет конфликтов файлов (GitHub сам проверит) ✅
   - Workflow `auto-merge-staging.yml` **сразу же мержит** PR в staging.
6. **Deploy:** Railway видит обновление в ветке staging и автоматически деплоит его (~2 минуты).

*Что если два агента запушили одновременно?*

GitHub смерджит обоих по очереди. Кто последний — тот и в топе. Railway выкатит кумулятивный результат.

### 4.3 Тестирование на Staging

1. Агент ждет завершения деплоя, проверяет логи Railway, если все ок то сообщает человеку что staging готов к ручным тестам человека.
2. Человек в ручную тестирует изменения в тестовом боте `@test_integer_ai_bot` и пишет агенту что нужно починить, если все ок дает добро сделать деплой в production.

### 4.4 Релиз в Production (Контролируемый)

Тут мы включаем "строгий режим". В прод едет только проверенный код.

1. **Report:** Человек дает команду ИИ агенту сделать деплой в production.

2. **Release PR:** ИИ агент запускает workflow Create Release PR (staging → main).

3. **Full CI:** На этом PR запускаются **ВСЕ** тесты (Unit, Integration, E2E). Это может занять 5-10 минут.

4. **PR Check:** ИИ агент проверяет Release PR, если тесты провалились или есть конфликты исправляет самостоятельно и создает PR заново, если все тесты прошли успешно и нет конфликтов то сообщает человеку что PR готов к merge.

5. **Human Review:**
   - Человек смотрит описание PR (Release Notes).
   - Человек убеждается, что все галочки зеленые (Tests Passed) и нет конфликтов.
   - Человек нажимает кнопку **"Squash and Merge"** вручную.

6. **Prod Deploy:** Railway автоматически деплоит ветку main в production, ИИ агент проверяет логи Railway чтобы убедиться что деплой прошел успешно и в логах нет ошибок, в случае успеха пишет человеку отчет об успешном деплое, в случае ошибок откатывает production к предыдущей рабочей версии и отправляет человеку отчет об ошибках.


---
Соблюдайте эти правила, оперативно обновляйте журнал действий и не забывайте согласовывать любые нетипичные шаги. Это гарантирует предсказуемые деплои и быстрый отклик на инциденты.
