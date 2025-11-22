## [2025-11-22] Staging Deployment: Fix WebApp Generation (Webhook Issue)

**Агент:** Gemini 3 Pro
**Ветка:** feature/fix-webapp-gen
**Worktree:** /Users/berik/Desktop/fix-webapp-gen

### Проблема:
При нажатии кнопки "Сгенерировать" в WebApp Midjourney ничего не происходило.
Причина: Бот не получал updates от Telegram (включая `web_app_data`), так как вебхук не устанавливался при старте контейнера.
Прошлый агент использовал Dockerfile, который игнорировал `railway.json` (где была команда `set_webhook`), а сам Dockerfile команду не содержал. Также `start_web.sh` использовал пути к `.venv`, которых нет в Docker-образе (system python).

### Исправление:
1.  **start_web.sh**: Убраны префиксы `./.venv/bin/`, скрипт переведен на использование системного python.
2.  **Dockerfile.web**: 
    - Добавлен `chmod +x start_web.sh`.
    - `CMD` изменен на `["./start_web.sh"]`.
    
Теперь при каждом старте контейнера выполняется `python manage.py set_webhook`.

### Результат:
✅ Код закоммичен. Ожидается деплой в Staging для проверки работы WebApp.
