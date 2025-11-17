# Журнал действий ИИ-агентов

В этот файл записывайте каждый выполненный шаг, чтобы другой агент мог продолжить работу c того же места.

## Формат записи
```
## 2025-11-11 — <краткое название задачи>
- Ветка: feature/<task>
- Шаг: что сделано (команда/скрипт/деплой)
- Проверки: какие проверки/логи просмотрены
- Коммит/PR: ссылка
- Следующий шаг: что планируется
```

Фиксируйте даже промежуточные действия (например, «дождался auto-merge PR #12», «проверил railway logs web»). Это обязательная часть процесса.

## Что обязательно указывать для каждого деплоя
- Кто и когда занял стенд (`STAGING_STATUS.md` должен ссылаться на соответствующую запись).
- Номер PR/коммит, который выкатили на staging.
- Команды, которые запускались при проверке (`railway status`, `railway logs web|worker|beat`, `curl -sf "$STAGING_BASE_URL/api/health"`).
- Факт уведомления человека о готовности стенда к ручному тестированию.
- Если деплой не удался — кратко опишите проблему и ссылки на логи, чтобы следующий агент понимал контекст.
## 2025-11-12 — проверка незадеплоенных изменений
- Ветка: feature/admin-dashboard
- Шаг: изучил Документация/AGENTS.md и собрал diff ветки относительно origin/staging (`git log origin/staging..HEAD`)
- Проверки: локальный git лог
- Коммит/PR: n/a
- Следующий шаг: при появлении доступа сверить деплой через Railway и подготовить обновление стейджинга

## 2025-11-12 — фиксация коммита деплоя staging
- Ветка: feature/admin-dashboard
- Шаг: запросил деплой через Railway GraphQL (`curl`/`python3`) и сверил с веткой (`git fetch origin staging`)
- Проверки: Railway GraphQL (serviceInstances.latestDeployment.meta.commitHash), git ревизия `origin/staging`
- Коммит/PR: n/a
- Следующий шаг: нет — окружение уже на последнем коммите `c4fa51a`

## 2025-11-12 — починка истории чатов в админке
- Ветка: feature/admin-dashboard
- Шаг: изучил причину 500 при открытии `История`, подключил каталог `templates/` в настройках, добавил тест на вью
- Проверки: `python manage.py shell` (загрузка шаблона), `manage.py test botapp.tests.AdminChatThreadViewTests` (не прошёл из-за отсутствия зависимостей aiogram/Pillow в окружении)
- Коммит/PR: n/a
- Следующий шаг: подготовить коммит с фиксом и дождаться ревью/CI

## 2025-11-12 — перезапуск CI для admin-dashboard
- Ветка: feature/admin-dashboard
- Шаг: закрыл и снова открыл PR #37, чтобы перезапустить auto-approve/CI перед выкатом на staging
- Проверки: `gh pr status` (контроль наличия PR и статуса проверок)
- Коммит/PR: https://github.com/berikbekishev-source/tg-nanobanana/pull/37
- Следующий шаг: дождаться merge в `staging`, проверить деплой и подготовить ручное тестирование

## 2025-11-12 — деплой фикса истории на staging
- Ветка: feature/admin-dashboard → staging
- Шаг: смержил PR #37 (squash 9711117), дождался автодеплоя Railway
- Проверки: `gh run list` (CI №19293752415 — success), `railway status --json` (commit 9711117 для web/worker/beat), `railway logs --service web|worker|beat --tail 200`, `curl https://web-staging-70d1.up.railway.app/api/health`
- Коммит/PR: https://github.com/berikbekishev-source/tg-nanobanana/pull/37
- Следующий шаг: ручное тестирование истории чатов в админке

## 2025-11-12 — редизайн истории чатов
- Ветка: feature/admin-dashboard
- Шаг: переработал шаблон/стили диалога (баблы как в Telegram, предпросмотр медиа, кнопки навигации), починил конфликт имён контекста (`chat_messages` вместо `messages`), добавил отображение аватаров/меток и обновил тест `AdminChatThreadViewTests`
- Проверки: `python manage.py check`, `ALLOWED_HOSTS=localhost,127.0.0.1,testserver python manage.py shell … client.get('/admin/botapp/chatthread/1/dialog/')` (ручной просмотр HTML)
- Коммит/PR: pending (будет новый push в feature/admin-dashboard)
- Следующий шаг: закоммитить изменения, запустить CI и выкатить на staging для ручного теста

## 2025-11-12 — починка статики для истории чатов
- Ветка: feature/admin-dialog-ui
- Шаг: подключил WhiteNoise, включил `collectstatic` в Dockerfile, настроил `STATIC_URL=/static/` и убрал дубли в `STATICFILES_DIRS`, чтобы кастомные стили admin загружались на staging
- Проверки: `python manage.py collectstatic --noinput`, `python manage.py check`, `python manage.py test botapp.tests.AdminChatThreadViewTests` (упало: test_postgres уже существует в Supabase env)
- Коммит/PR: pending (готовлю PR с фиксом UI)
- Следующий шаг: закоммитить изменения, занять staging, проверить деплой и подтвердить готовность к ручному тесту

## 2025-11-12 — внедрение мониторинга ошибок
- Ветка: release/deploy-pipeline-main
- Шаг: добавил модель `BotErrorEvent`, сервис `ErrorTracker`, интеграции с webhook/aiogram/Celery/GenerationService, документацию и env-переменные `ERROR_ALERT_*`
- Проверки: локальная попытка `python3 manage.py migrate` (падает на старом SQLite из-за SQL `DROP INDEX IF EXISTS`, что не влияет на PostgreSQL окружения)
- Коммит/PR: pending
- Следующий шаг: подготовить деплой на staging после ревью

## 2025-11-12 13:45 UTC — e2e тест пайплайна деплоя
- Ветка: feature/deploy-pipeline-e2e-20251112-181415 → staging
- Шаги:
  - Создал фичу с минимальной правкой (botapp/__init__.py) и STAGING_STATUS.md (бронировал стенд)
  - Открыл PR #48 в staging; дождался зелёного CI и смержил (squash)
  - Подтвердил автодеплой на staging: смоки прошли, Railway web/worker/beat — Success
  - Освободил стенд (PR #50), зафиксировал статус
  - Создал PR #51 staging → main (ожидает ручной merge человеком)
- Проверки:
  - gh pr checks 48/50/51 — success (build-test, staging-smoke)
  - gh run list --branch staging — CI success (push)
  - Railway статус (из статусов PR): web-staging-70d1.up.railway.app, web/worker/beat — Success
- Коммиты/PR: staging@23d4be6 (merge #48), PR #50, PR #51
- Следующий шаг: человек жмёт Merge в PR #51; затем проверить prod CI + post-deploy-monitor и health
## 2025-11-12 — автоматический collectstatic на web-сервисе
- Ветка: feature/admin-static
- Шаг: обновил `railway.json`, чтобы web-сервис перед миграциями запускал `./.venv/bin/python manage.py collectstatic --noinput`; теперь WhiteNoise видит стили до старта gunicorn
- Проверки: `railway ssh --service web "python manage.py collectstatic --noinput"` (ручной прогон на текущем деплое), `railway status --json` (commit df1ceb6 для web/worker/beat), `curl https://web-staging-70d1.up.railway.app/api/health`
- Коммит/PR: pending
- Следующий шаг: задеплоить фикс на staging, убедиться, что history view загружается без 500 и со стилями

## 2025-11-12 — внедрение мониторинга ошибок (ErrorTracker)
- Ветка: feature/error-monitoring
- Шаг: добавил модель `BotErrorEvent`, миграцию, сервис `ErrorTracker`, глобальный обработчик aiogram, интеграцию в webhook/Celery/бизнес-слой/reference_prompt, документацию и команду `prune_bot_errors`
- Проверки: `python3 manage.py check`, `python3 manage.py makemigrations --check --dry-run`
- Коммит/PR: pending
- Следующий шаг: подготовить PR → staging, после деплоя проверить логи web/worker/beat и health, затем передать стенд на ручные тесты
## 2025-11-17 — e2e тест деплоя на staging
- Ветка: feature/staging-deploy-test-20251117
- Шаг: обновил docstring в `botapp/__init__.py`, добавил комментарий в `Документация/AGENTS.md`, починил совместимость `NinjaAPI` через `config/ninja_api.py`, после зелёного CI занял стенд (`bin/staging-status reserve --agent "Codex" --ref "PR #59, f5aa73b"`), смержил PR `#59` через `bin/deploy-staging 59`
- Проверки: 
  - `bin/deploy-staging 59` (первый прогон упал на health-check 502, сразу повторил проверки вручную после окончания деплоя)
  - `railway status --json | jq '…select(.environmentId=="9e15b55d-8220-4067-a47e-191a57c2bcca")…'` — web/worker/beat = SUCCESS, commit `9312cf6`
  - `railway logs --service web|worker|beat --environment staging --lines 80` — web: единичный `Telegram webhook error` (JSONDecodeError на пустом body), worker/beat без ошибок
  - `curl -fsS https://web-staging-70d1.up.railway.app/api/health | jq '.'` → `{"ok": true}`
- Коммит/PR: https://github.com/berikbekishev-source/tg-nanobanana/pull/59 (merge commit 9312cf6 в staging)
- Следующий шаг: освободить стенд и передать на ручное тестирование
