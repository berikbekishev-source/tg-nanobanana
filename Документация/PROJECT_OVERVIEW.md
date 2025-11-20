# Обзор проекта Telegram NanoBanana Bot

Цель: дать полное описание структуры репозитория, назначения папок и ключевых файлов для быстрой ориентации агентам и разработчикам.

## Корень
- `manage.py` — точка входа Django.
- `requirements.txt` — зависимости (production/dev).
- `docker-compose.yml` — локальный запуск сервисов (web/worker/beat/redis/postgres при необходимости).
- `Dockerfile.web`, `Dockerfile.worker`, `Dockerfile.beat` — сборка образов для web, Celery worker и scheduler.
- `railway.json` — конфигурация Railway.
- Служебные маркеры деплоя генерируются пайплайном автоматически (в репозитории не держим).
- `documentation.yaml` — экспорт OpenAPI (для lavatop).

## Конфиги и инфраструктура
- `config/` — настройки Django.
  - `asgi.py` — ASGI-энтрипоинт web-приложения.
  - `celery.py` — инициализация Celery.
  - `settings.py` + профильные настройки (`settings_sqlite.py`, `settings_prod.py`, при наличии) — конфигурация окружений.
  - `urls.py` — маршрутизация Django.
  - `env`-шаблоны, если присутствуют — пример переменных.
- `.github/` — CI/CD workflow (lint/auto-PR/другие сценарии).
- `.gitignore` — исключения.

## Бизнес-логика бота
- `botapp/` — основной Django app.
  - `models.py` — модели (пользователи, балансы, AI модели, заказы генерации, транзакции, настройки, промокоды, чат-лог, ошибки).
  - `admin.py` — админка по моделям.
  - `api.py` — webhook/HTTP API Django.
  - `tasks.py` — Celery задачи (обработка генерации, платежей, постпроцесс).
  - `handlers/` — aiogram-хендлеры (image/video generation, меню, платежи, reference prompt).
  - `providers/` — интеграции с внешними AI провайдерами (video/image).
  - `business/` — бизнес-сервисы (balance, pricing, generation, bonuses, analytics).
  - `keyboards.py`, `states.py` — клавиатуры и FSM состояния aiogram.
  - `chat_logger.py`, `aiogram_errors.py`, `error_tracker.py`, `services.py`, `signals.py` — инфраструктурные сервисы (лог чатов, ошибки, сигналы).
  - `migrations/` — миграции Django (включая Postgres-специфичные 0027–0028).
  - `reference_prompt/` — модели/сервис для генерации промтов по референсу.
  - `tests.py` — тесты (учитывать Postgres-зависимость некоторых миграций).

## Lavatop (миниапп/платежи)
- `lavatop/` — интеграция LavaPay/мини-приложение.
  - `api.py`, `webhook.py`, `models`/`schemas` (если есть) — обработка платежей и API.
  - `tests/` — тесты; `tests/archive`/`tests/manual` — архив/ручные примеры (не используются в CI).
  - `docs/` или файлы `*LAVA*` — справочные материалы.

## Dashboard / Templates / UI
- `dashboard/` — Django-просмотр для операторов/админок (views/templates/urls внутри).
- `templates/` — HTML-шаблоны (бот UI, админ-дополнения, miniapp).
- `static/` (если появится) — статика; в корне нет, но может быть внутри модулей.
- `lavatop/` может содержать свои шаблоны/статику.

## Документация
- `Документация/` — главный каталог инструкций.
  - `AGENTS.md` — правила работы ИИ-агентов.
  - `AGENTS_LOGS.md` — журнал действий агентов.
  - `PROJECT_OVERVIEW.md` — текущий файл с обзором проекта.
  - `DB_CLEANUP_PLAN.md` — рекомендации по очистке БД.
  - Прочие документы: интеграции (SORA, KLING, MIDJOURNEY), планы релиза, админ-гайды, pricing, integration notes.

## Miniapp / вспомогательные ресурсы
- `documentation.yaml` — возможный экспорт API/описание схем (использовать как справку).
- `lava_docs.html`, другие `*.MD` в корне/Документация — справочные материалы.

## Что важно помнить (технические нюансы)
- Миграции 0027–0028 в `botapp/migrations` используют Postgres (триггеры/DO $$); не гонять на sqlite.
- `TokenPackage` в `botapp/models.py` — `managed=False`, привязан к внешней таблице `token_packages` (Railway).
- Поля `UserSettings` (notify*/prefs) и реферальные поля `UserBalance` оставлены для будущего использования; не удалять без согласования.
- Легаси поле `GenRequest.model` сохранено для совместимости (исторический след), реструктурировать только после отдельного решения.
- Базы данных разнесены: **prod** — Supabase проект `eqgcrggbksouurhjxvzs` (пулер `aws-1-eu-north-1.pooler.supabase.com`), **staging** — отдельный проект `tg-nanobanana-stg` (`usacvdpwwjnkazkahfwv`, пулер `aws-1-eu-west-1.pooler.supabase.com`). `DATABASE_URL` задаётся переменными Railway по окружениям.
- Миграции выполняются на каждом деплое автоматически в своём окружении (`python manage.py migrate` из `railway.json`). Данные между stg/prod не синхронизируются; перенос данных — только вручную и по согласованию.

## Быстрый ориентир по деплою (staging/production)
- Ветки: `staging` → автодеплой Railway (staging бот), `main` → production бот.
- Рабочий процесс: feature → PR в `staging` (auto lint + auto-merge), затем тестирование, затем Release PR `staging → main` по команде.
