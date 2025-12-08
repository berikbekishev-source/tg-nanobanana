# Инструкция для ИИ-агентов

Документ описывает проект Telegram NanoBanana Bot, правила работы ИИ-агентов и регламент деплоя.

- Сервисы и команды:
  - `web` (`29038dc3-c812-4b0d-9749-23cdd1b91863`) — `gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --workers 2` (Dockerfile.web).
  - `worker` (`aeb9b998-c05b-41a0-865c-5b58b26746d2`) — `celery -A config worker -l info --pool=prefork --concurrency=2` (Dockerfile.worker).
  - `beat` (`4e7336b6-89b9-4385-b0d2-3832cab482e0`) — `celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler` (Dockerfile.beat).
  - `redis` (`e8f15267-93da-42f2-a1da-c79ad8399d0f`) — управляемый сервис Railway.

## 1. Описание проекта

### 1.1 Общая информация

**Telegram NanoBanana Bot** — коммерческий Telegram-бот для генерации изображений и видео с использованием различных AI-моделей.

- **Репозиторий:** `https://github.com/berikbekishev-source/tg-nanobanana`
- **Стек:** Python 3.12, Django 5.2, Celery, Redis, PostgreSQL
- **Инфраструктура:** Railway (хостинг), Supabase (БД + Storage), GitHub Actions (CI/CD)

### 1.2 Структура каталогов

```
tg-nanobanana/
├── botapp/                     # Основная логика бота
│   ├── handlers/               # Обработчики Telegram-команд
│   │   ├── global_commands.py  # /start, /help, /balance
│   │   ├── image_generation.py # Генерация изображений
│   │   ├── video_generation.py # Генерация видео
│   │   ├── payment.py          # Платежи и пополнение
│   │   ├── menu.py             # Навигация по меню
│   │   └── reference_prompt.py # Анализ референсов
│   ├── providers/              # Интеграции с AI-провайдерами
│   │   └── video/
│   │       ├── vertex.py       # Google Veo (Vertex AI)
│   │       ├── openai_sora.py  # OpenAI Sora
│   │       ├── kling.py        # Kling AI
│   │       ├── midjourney.py   # Midjourney Video
│   │       ├── geminigen.py    # GeminiGen
│   │       └── useapi.py       # UseAPI (Kling, Midjourney)
│   ├── business/               # Бизнес-логика
│   │   ├── balance.py          # Управление балансом
│   │   ├── generation.py       # Логика генерации
│   │   ├── pricing.py          # Расчёт цен
│   │   ├── bonuses.py          # Бонусная система
│   │   └── analytics.py        # Аналитика
│   ├── reference_prompt/       # Модуль анализа референсов
│   │   ├── service.py          # Основной сервис
│   │   ├── downloader.py       # Загрузка медиа
│   │   └── pricing.py          # Ценообразование
│   ├── models.py               # Django-модели (TgUser, AIModel, GenRequest и др.)
│   ├── services.py             # Сервисный слой
│   ├── tasks.py                # Celery-задачи
│   ├── api.py                  # REST API эндпоинты
│   ├── keyboards.py            # Telegram-клавиатуры
│   └── admin.py                # Django Admin
├── config/                     # Конфигурация Django
│   ├── settings.py             # Настройки приложения
│   ├── celery.py               # Конфигурация Celery
│   ├── asgi.py                 # ASGI-приложение
│   └── urls.py                 # URL-маршруты
├── webapps/                    # Mini Apps (Telegram WebApp)
│   ├── veo/                    # Google Veo интерфейс
│   ├── sora2/                  # OpenAI Sora интерфейс
│   ├── kling/                  # Kling AI интерфейс
│   ├── midjourney/             # Midjourney интерфейс
│   ├── midjourney_video/       # Midjourney Video
│   ├── gpt-image/              # GPT Image интерфейс
│   ├── runway/                 # Runway интерфейс
│   ├── runway_aleph/           # Runway Aleph
│   └── nanobanana/             # Основной WebApp
├── dashboard/                  # Админ-панель статистики
├── lavatop/                    # Интеграция с платёжной системой
├── templates/                  # Django-шаблоны
├── Документация/               # Документация проекта
│   ├── AGENTS.md               # Этот файл
│   ├── AGENTS_LOGS.md          # Журнал действий агентов
│   └── *.md                    # Прочая документация
├── .github/workflows/          # GitHub Actions
│   ├── ci.yml                  # CI проверки
│   ├── auto-merge-staging.yml  # Авто-мердж в staging
│   ├── create-release-pr.yml   # Создание релизного PR
│   └── *.yml                   # Прочие workflows
├── Dockerfile.web              # Docker для web-сервиса
├── Dockerfile.worker           # Docker для Celery worker
├── docker-compose.yml          # Локальная разработка
├── requirements.txt            # Python-зависимости
└── manage.py                   # Django CLI
```

### 1.3 Railway-сервисы

| Сервис | Назначение | Команда запуска |
|--------|------------|-----------------|
| **web** | Django ASGI-сервер | `gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker` |
| **worker** | Celery worker | `celery -A config worker -l info --pool=prefork --concurrency=2` |
| **beat** | Celery beat scheduler | `celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler` |
| **redis** | Очереди и кэш | Managed service |

### 1.4 Окружения

| Git-ветка | Railway-окружение | Назначение |
|-----------|-------------------|------------|
| `staging` | staging | Тестирование, тестовый Telegram-бот |
| `main` | production | Продакшн, основной бот |

### 1.5 База данных (Supabase PostgreSQL)

**Основные таблицы:**

| Таблица | Назначение |
|---------|------------|
| `botapp_tguser` | Пользователи Telegram |
| `botapp_userbalance` | Балансы пользователей |
| `botapp_transaction` | Транзакции (пополнения, списания) |
| `botapp_aimodel` | AI-модели (настройки, цены) |
| `botapp_genrequest` | Запросы на генерацию |
| `botapp_chatthread` | Чат-диалоги |
| `botapp_chatmessage` | Сообщения в чатах |
| `botapp_promocode` | Промокоды |

### 1.6 Используемые инструменты

- **GitHub CLI (`gh`)** — работа с PR, issues, workflows
- **Railway CLI (`railway`)** — просмотр логов и статуса сервисов
- **Supabase** — БД и файловое хранилище
- **Docker** — локальная разработка

> **Все секреты и токены хранятся в переменных окружения Railway.** Для получения доступа обратитесь к администратору проекта.

---

## 2. Правила работы ИИ-агентов

### 2.1 Обязательные требования перед началом работы

1. **Планирование.** Перед выполнением любой задачи агент обязан:
   - Составить детальный план действий
   - Согласовать план с человеком
   - Приступать к реализации только после явного одобрения

2. **Изолированная среда.** Каждый агент работает в отдельном git worktree:
   ```bash
   git fetch origin staging
   git worktree list  # проверить занятые имена
   git worktree add worktrees/<уникальное-имя> -b feature/<уникальное-имя> origin/staging
   cd worktrees/<уникальное-имя>
   ```

3. **Подтверждение готовности.** После создания worktree агент сообщает:
   - Путь к worktree (`pwd`)
   - Имя ветки (`git branch --show-current`)
   - Последний коммит (`git log -1 --oneline`)

### 2.2 Принципы разработки

1. **Язык.** Вся коммуникация и комментарии в коде — только на русском языке.

2. **Качество кода.** Запрещены:
   - Костыльные решения и хардкод
   - Временные заглушки без плана их устранения
   - Код, нарушающий существующую архитектуру

3. **Масштабируемость.** Все решения должны быть:
   - Системными и расширяемыми
   - Соответствующими существующим паттернам проекта
   - Документированными при необходимости

4. **Самостоятельность.** Агент выполняет задачи максимально самостоятельно, используя доступные инструменты. Обращение к человеку — только при реальной необходимости.

### 2.3 Работа с Git

1. **Коммиты.** Каждое значимое изменение фиксируется отдельным коммитом:
   ```bash
   git add .
   git commit -m "feat: описание изменения"
   ```

2. **Запрет на пуш без разрешения.** Перед выполнением `git push` агент обязан:
   - Сообщить о готовности к пушу
   - Дождаться явного разрешения от человека

3. **Сохранность кода.** Важные изменения коммитятся немедленно, чтобы исключить их потерю.

### 2.4 Рабочий процесс

1. **Пошаговое выполнение:**
   - Один шаг → фиксация результата → краткий отчёт → следующий шаг

2. **Тестирование:**
   - Запускать доступные тесты перед завершением задачи
   - При отсутствии тестов — описать способ ручной проверки

3. **Проверка работоспособности:**
   - Проверять логи сервисов (web, worker, beat)
   - Проверять `/api/health` перед отчётом об успехе

4. **Журналирование:**
   - После каждого значимого действия — запись в `Документация/AGENTS_LOGS.md`
   - Формат: дата, ветка, действие, ссылка на коммит/PR

### 2.5 Запреты

| Действие | Причина |
|----------|---------|
| `railway deploy`, `railway up` | Деплой только через GitHub Actions |
| `git stash` при конфликтах | Приводит к потере контекста |
| `git push --force` | Риск потери истории |
| Изменение переменных окружения | Только через Railway Dashboard |
| Публикация токенов | Безопасность |
| Rollback без согласования | Риск нарушения работы |

### 2.6 Отчётность

- Для каждого действия фиксировать: ветка, выполненные команды, результат
- При ошибках: собирать факты (ID workflow, логи, команды) и предлагать план устранения
- Никогда не скрывать ошибки — лучше сразу сообщить и предложить решение

---

## 3. Регламент деплоя

### 3.1 Принцип Fast Track Pipeline

**"Push First, Fix Later (if needed). Минимум ручного слияния."**

GitHub автоматически выполняет merge через Auto-merge и Update Branch. Агенту не нужно делать `git merge staging` вручную, если нет конфликтов.

### 3.2 Деплой в Staging (2-3 минуты)

#### Шаг 1: Push feature-ветки
```bash
git push origin feature/<название>
```

**Автоматически происходит:**
- GitHub Actions создаёт PR `feature/* → staging`
- GitHub проверяет актуальность ветки
- При отсутствии конфликтов — Auto-merge
- Railway запускает deploy

#### Шаг 2: Мониторинг PR
```bash
gh pr view --json state,mergeable,statusCheckRollup,url
```

**Возможные статусы `mergeable`:**
- `MERGEABLE` — всё в порядке, ожидайте авто-мердж
- `CONFLICTING` — есть конфликты, требуется ручное разрешение
- `UNKNOWN` — GitHub обрабатывает, повторить через 10 сек

#### Шаг 3: Разрешение конфликтов (только при `CONFLICTING`)
```bash
git fetch origin staging
git merge origin/staging
# Разрешить конфликты вручную (найти <<<<<<< и >>>>>>>)
git add .
git commit -m "merge: resolve conflicts with staging"
git push origin feature/<название>
```

**Запрещено при конфликтах:**
- `git checkout --theirs`
- `git stash`

#### Шаг 4: Проверка деплоя
```bash
# Подождать ~2 минуты
railway logs --service web | tail -20
curl https://web-staging-70d1.up.railway.app/api/health
```

### 3.3 Деплой в Production (10-15 минут)

#### Шаг 1: Получение разрешения
Человек тестирует staging и даёт команду на деплой в production.

#### Шаг 2: Создание Release PR
```bash
gh workflow run create-release-pr.yml \
  -f release_title="Release: <описание>" \
  -f release_notes="Список изменений: ..."
```

#### Шаг 3: Мониторинг CI
```bash
gh pr view <PR_NUMBER> --json state,mergeable,statusCheckRollup
```

#### Шаг 4: Merge
После прохождения всех проверок агент сообщает человеку. **Merge в `main` выполняет человек.**

#### Шаг 5: Проверка production
```bash
railway logs --service web --environment production | tail -20
```

### 3.4 Диагностика Railway

```bash
# Статус проекта
railway status

# Логи сервисов
railway logs --service web
railway logs --service worker
railway logs --service beat

# Переменные окружения (только просмотр)
railway variables --service web
```

### 3.5 Журнал деплоя

После каждого деплоя обновить `Документация/AGENTS_LOGS.md`:

```markdown
## [YYYY-MM-DD] Staging Deployment: <описание>

**Агент:** <имя агента>
**Ветка:** feature/<название>
**PR:** #<номер> (Status: MERGED)

### Выполненные действия:
1. Push в GitHub
2. PR Status: MERGEABLE (Auto-merged) / CONFLICTING (Resolved manually)
3. Railway deployment: ✅ SUCCESS

### Результат:
✅ Staging готов к тестированию
```

---

## Контакты

При возникновении вопросов или проблем обращайтесь к администратору проекта.
