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

| Git ветка | Railway окружение | Назначение |
|-----------|-------------------|------------|
| `staging` | `staging`         | Автотесты, тестовый Telegram-бот (@test_integer_ai_bot). |
| `main`    | `production`      | Продакшн и основной бот (@tg_nanobanana_bot). |

- Сервисы: `web` (Django), `worker` (Celery), `beat` (Scheduler), `redis`.

### 1.4 Документация
- Все инструкции в `Документация/*.md`.
- Журнал действий агентов: `Документация/AGENTS_LOGS.md` (опционально, если требуется).

## 2. Доступы к инструментам

### 2.1 GitHub
- Репозиторий: `git@github.com:berikbekishev-source/tg-nanobanana.git`.
- Критичные секреты (Secret Variables): `ADMIN_GH_TOKEN`, `RAILWAY_API_TOKEN`.

### 2.2 Railway
- Управление через GitHub Actions. Ручные деплои (`railway up`) запрещены.
- Логи можно смотреть через CLI: `railway logs --service web`.

### 2.3 Telegram-боты
- **Staging:** `@test_integer_ai_bot` (Токен: `7869...`).
- **Production:** `@tg_nanobanana_bot` (Токен: `8238...`).

## 3. Правила работы ИИ агента (Fast Track)

### 3.1 Основные принципы
1.  **Русский язык:** Вся коммуникация и комментарии на русском.
2.  **Изоляция:** Работайте только в своих ветках (`feature/`).
3.  **Скорость:** Staging предназначен для быстрой проверки. Не бойтесь его сломать, но обязаны быстро починить.
4.  **Безопасность:** Production — священная зона. Туда попадает только проверенный код.

### 3.2 Рабочий процесс (Pipeline)

**Шаг 1: Начало работы**
1.  Агент запускается в **Worktree**.
2.  Синхронизируется с актуальным кодом:
    ```bash
    git checkout staging
    git pull origin staging
    ```
3.  Создает ветку задачи:
    ```bash
    git checkout -b feature/<название-задачи>
    ```

**Шаг 2: Разработка и Доставка на Staging**
1.  Пишите код, проверяйте локально (если возможно).
2.  Пушьте изменения:
    ```bash
    git add .
    git commit -m "feat: описание"
    git push origin feature/<название-задачи>
    ```
3.  **Автоматика (GitHub):**
    - Создается Pull Request в `staging`.
    - Запускается **Линтер** (Syntax Check, ~1 мин).
    - Если ошибок нет и конфликтов нет — **PR мержится автоматически**.
4.  **Деплой (Railway):**
    - Railway автоматически деплоит ветку `staging` (~2-3 мин).

**Шаг 3: Тестирование**
1.  Дождитесь деплоя (можно проверить `curl https://web-staging-70d1.up.railway.app/api/health` или просто подождать 3 мин).
2.  Проверьте свою фичу в боте `@test_integer_ai_bot`.
3.  Если нашли баг — исправьте в той же ветке и повторите пуш.

**Шаг 4: Релиз в Production**
1.  Сообщите человеку: "Фича проверена на staging. Готов к релизу."
2.  Человек (или агент по команде) запускает workflow `Create Release PR` (`staging` → `main`).
3.  GitHub запускает **полные тесты** (Full CI).
4.  После успеха человек вручную мержит PR.
5.  Railway деплоит `main` в Production.
6.  Система мониторинга (`post-deploy-monitor`) проверит здоровье продакшена и при сбое сделает откат.

### 4. Действия при сбоях
- **Линтер упал:** Исправьте синтаксические ошибки (flake8) и запушьте снова.
- **Мердж конфликт:** Выполните в worktree:
  ```bash
  git pull origin staging
  # решите конфликты
  git push origin feature/<название>
  ```
- **Staging не отвечает:** Проверьте логи `railway logs`. Скорее всего, ошибка в коде при запуске.
- **Production упал:** Система сама откатит релиз. Проанализируйте логи и отчет в Telegram.

---
Соблюдайте эти правила для быстрой и безопасной работы.

