# План безопасного деплоя через ветку `staging`

Документ фиксирует целевую схему безопасного деплоя, используемые инструменты и текущее состояние внедрения. Все команды и действия описаны для репозитория `berikbekishev-source/tg-nanobanana` и проекта Railway `Telegram_bot`.

## Цели

- Параллельная разработка несколькими ИИ‑агентами без риска сломать продакшен.
- Автоматические проверки (CI) и смоки перед выкладкой на прод.
- Быстрый откат, наблюдаемость и минимум ручных действий.

## Архитектура окружений

- production (`main`) — боевое окружение Railway, текущая публикация бота.
- staging (`staging`) — тестовое окружение Railway для ручных и авто‑смоков.
- Разные переменные окружения, отдельный Telegram‑бот и секрет вебхука для `staging`.

## GitHub: ветки и автоматизация

- Ветки: `main` (prod), `staging` (pre‑prod), feature‑ветки (любой префикс).
- Защита веток (`main` и `staging`):
  - только через Pull Request;
  - ≥1 обязательный review;
  - required status check: `CI and Smoke / build-test`;
  - linear history, resolution дискуссий, запрет force‑push.
- Автоматизация (воркфлоу в `.github/workflows/`):
  - `ci.yml` — сборка, Django checks, сборка Docker‑образов, smokes `/api/health` для `staging`/`main` (берут адреса из `Actions → Variables`).
  - `pr-from-feature.yml` — авто‑создание PR → `staging` при пуше в feature‑ветку.
  - `auto-approve.yml` — авто‑ревью ботом и включение auto‑merge при зелёном CI (для PR в `staging` и `main`).
  - `post-deploy-monitor.yml` — смоки и анализ логов после деплоя `main`; при фейле откатывает коммит и шлёт уведомления в Telegram.
  - `setup-branch-protection.yml` — применение правил защиты веток (push + ручной запуск).
  - `set-telegram-webhook.yml` — установка вебхука Telegram для `staging`/`production` (по секретам).

### Доступ к GitHub для агентов

- Используется отдельный бот‑аккаунт с Fine‑grained PAT.
- Секрет: `ADMIN_GH_TOKEN` (Actions → Secrets).
- Секреты для мониторинга: `TELEGRAM_MONITOR_BOT_TOKEN`, `TELEGRAM_MONITOR_CHAT_ID`.
- Обязательные настройки (включены): Workflow permissions = Read&Write, Allow Actions to create/approve PRs = On, Allow auto-merge = On.
- Переменные (Actions → Variables): `RAILWAY_API_TOKEN`, `PRODUCTION_BASE_URL`, `STAGING_BASE_URL`.

## Railway: сервисы и переменные

- Окружения: `production` и `staging` (создано).
- Сервисы в `staging`: `web`, `worker`, `beat`, плагин `REDIS_URL` (созданы и синхронизированы с production).
- Привязка источника:
  - Repo: `berikbekishev-source/tg-nanobanana`
  - Branch: `staging`
  - Web: Dockerfile.web; Start: `gunicorn -k uvicorn.workers.UvicornWorker config.asgi:application --bind 0.0.0.0:$PORT --workers 2`
  - Worker: Dockerfile.worker; Start: `celery -A config.celery:app worker -Q default -l INFO`
  - Beat: Dockerfile.worker; Start: `celery -A config.celery:app beat -l INFO`

### Переменные окружения (staging)

- Обязательные: `DATABASE_URL`, `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`, `SUPABASE_VIDEO_BUCKET`.
- Telegram: `TELEGRAM_BOT_TOKEN` (тестовый) — установлено; `TG_WEBHOOK_SECRET` — установлено.
- Прочие: `DJANGO_DEBUG=true` (web/worker) — установлено; `PUBLIC_BASE_URL` — заполняется после выдачи домена web в staging.

## Наблюдаемость и смоки

- Смоки `/api/health` включены в `ci.yml` и запускаются автоматически после деплоя на `staging`/`main` (используют `STAGING_BASE_URL`/`PRODUCTION_BASE_URL`).
- Рекомендуется включить Sentry (`SENTRY_DSN`, `SENTRY_ENVIRONMENT=staging|production`).
- После деплоя в `main` отдельный воркфлоу `post-deploy-monitor.yml` делает ретраи `/api/health`, забирает логи Railway (`web/worker/beat`), шлёт отчёт в Telegram и при фейле выполняет `git revert`.

## Онбординг нового агента (быстрый старт)

1) Ознакомьтесь с этим документом и `Документация/AGENTS.md` (правила, переменные, токены, Railway).
2) Для локальной проверки:
   - Python 3.11+, `pip install -r requirements.txt`.
   - Создайте `.env` по образцу `.env.example` (для локали можно использовать SQLite/Redis docker).
   - Либо поднимите через `docker-compose up` (web/worker/beat/redis).
3) Разработка фичи:
   - Создайте feature‑ветку от `staging`, делайте малые атомарные коммиты.
   - Не коммитьте секреты. Комментарии в коде — на русском.
   - Перед пушем убедитесь, что проходят: `python manage.py check` и `makemigrations --check`.
4) Пуш: просто `git push` в feature — PR → `staging` создастся автоматически. Дождитесь зелёного `build-test`.
5) Стадия `staging`:
   - Авто‑деплой, затем смоки `/api/health`.
   - После ручного теста создайте PR `staging → main` (по подтверждению человека).
6) Релиз prod: после merge в `main` автодеплой на Railway и фоновый `post-deploy-monitor`.

Если CI/ветки ведут себя необычно — используйте `setup-branch-protection.yml` (Run workflow) чтобы переустановить правила защиты.

### Процесс релиза `staging → main`

1. Агент‑разработчик пушит фичу в feature‑ветку — создаётся PR в `staging`, проходит CI (`CI and Smoke`) и auto‑merge.
2. Railway автодеплоит `staging`, вы выполняете ручные смоки в тестовом боте.
3. После вашего подтверждения агент вручную создаёт PR `staging → main`.
4. На PR в `main` снова срабатывают `CI and Smoke` + `auto-approve.yml`, которые дают merge только при зелёном статусе.
5. Пуш в `main` вызывает деплой Railway. После завершения воркфлоу `post-deploy-monitor.yml` проверяет `/api/health`, выгружает логи `web/worker/beat`, пишет в Telegram (`TELEGRAM_MONITOR_BOT_TOKEN` + `TELEGRAM_MONITOR_CHAT_ID`). Если check падает, джоб `rollback` делает `git revert` проблемного коммита и также уведомляет вас.
6. После успешного мониторинга можно продолжать следующую фичу; в случае отката агент повторяет фиксы от `staging`.

## Роллбек

- Вернуться на предыдущую версию: `git revert` → PR → merge (автодеплой). При необходимости временно ослабить защиту веток через `setup-branch-protection.yml` и включить обратно после мержа фикса.

### Экстренный откат (пример)

```bash
# Откатить последний коммит feature/PR
git revert <bad-commit-sha>
git push origin <branch>
# Авто‑PR обновится, после CI смёрджится и задеплоится.
```

---

## Статус выполнения

### Сделано

- Создана ветка `staging` и включена защита веток `main`/`staging` (PR only, review, required checks, linear history).
- Добавлены и починены воркфлоу: `ci.yml`, `setup-branch-protection.yml`, `pr-from-feature.yml`, `auto-approve.yml`, `post-deploy-monitor.yml`, `set-telegram-webhook.yml`.
- Включена авто‑схема: feature → PR в `staging` → auto‑approve/auto‑merge → деплой на `staging`; выпуск в `main` инициируется вручную через PR, после чего `post-deploy-monitor` следит за продом и при необходимости откатывает.
- Создано окружение Railway `staging` и синхронизирована архитектура (web/worker/beat/REDIS_URL).
- На `staging` заданы: `TELEGRAM_BOT_TOKEN` (тестовый), `TG_WEBHOOK_SECRET`, `DJANGO_DEBUG=true` (web/worker).
- В GitHub Variables добавлено: `RAILWAY_API_TOKEN`, `PRODUCTION_BASE_URL`; `STAGING_BASE_URL` — временная заглушка до публикации домена web.
- Воркфлоу `CI and Smoke` и `Set Telegram Webhook` обновлены: смоки и установка вебхука теперь читают `STAGING_BASE_URL`/`PRODUCTION_BASE_URL` из GitHub Variables (а не secrets), также исправлена передача `allowed_updates` при запросе в Telegram API.

### В работе / осталось сделать

  - `staging` — проверить и (при необходимости) заполнить:
    - `DATABASE_URL` (стейджинговая БД), `SUPABASE_*` (желательно отдельные бакеты), `REDIS_URL` (должен прокидываться плагином), `PUBLIC_BASE_URL` (после появления домена web).
  - Получить домен web в `staging` и записать `STAGING_BASE_URL` в GitHub Variables. Пока стоит заглушка `https://staging.example.invalid`.
  - Установить вебхук Telegram для `staging` (workflow `Set Telegram Webhook`, env=staging) и убедиться, что `/api/telegram/webhook` отвечает c 200.
  - Подключить Sentry (опционально) и добавить `SENTRY_ENVIRONMENT=staging`.
  - Прогнать смоки `/api/health` и короткий чек‑лист ручных тестов в тестовом боте.

### Чек‑лист ручных тестов (staging)

- `/api/health` отвечает 200 c `{ "ok": true }`.
- Установлен webhook Telegram (`Set Telegram Webhook`), и при событии бот попадает в `worker` (логи без ошибок).
- Генерация изображения:
  - Команда/кнопка запуска в боте работает, создаётся `GenRequest` со статусами `queued → processing → done`.
  - Изображение грузится в Supabase (`supabase_upload_png`), ссылка возвращается и отправляется в бот.
- Генерация видео (если включено): воркфлоу задач, склейка/загрузка (по доступным провайдерам), отправка в бот.
- База и Redis: нет ошибок подключения в логах, Celery видит брокер.
- Ошибки (если возникают) фиксируются в Sentry (при заданном `SENTRY_DSN`).

---

## Быстрые инструкции агентам

1) Разработка: пушьте в feature‑ветку — PR в `staging` создастся автоматически, бот поставит review и включит auto‑merge после зелёного CI.
2) Проверка: деплой и смоки на `staging` выполняются автоматически. После ручного теста создаём PR `staging → main` и ждём зелёный `CI and Smoke`.
3) Вебхук Telegram: через Actions → `Set Telegram Webhook` (выберите `staging` или `production`).
4) Защита веток: если нужно временно ослабить правила (например, для починки CI) — Actions → `Setup Branch Protection` → Run workflow, затем верните строгие правила.

### Команды Railway CLI (опционально)

```bash
# Авторизация
export RAILWAY_TOKEN="<token>"
railway status

# Логи
railway logs --service web --tail 100
railway logs --service worker --tail 100
railway logs --service beat --tail 100

# Переменные (пример)
railway variables --service web
railway variables --set DJANGO_DEBUG=true --service web

# Редеплой
railway redeploy --service web --yes
```

---

## Приложение: референсы

- Репозиторий: https://github.com/berikbekishev-source/tg-nanobanana
- Railway Project: Telegram_bot (ID `866bc61a-0ef1-41d1-af53-26784f6e5f06`)
- Окружения: production (`2eee50d8-402e-44bf-9035-8298efef91bc`), staging (`9e15b55d-8220-4067-a47e-191a57c2bcca`)
- Сервисы: web (`29038dc3-c812-4b0d-9749-23cdd1b91863`), worker (`aeb9b998-c05b-41a0-865c-5b58b26746d2`), beat (`4e7336b6-89b9-4385-b0d2-3832cab482e0`)
