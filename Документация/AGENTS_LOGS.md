## 1. Deployments (Latest First)

| Status | Commit | Description | Date |
| :--- | :--- | :--- | :--- |
| 🔧 LOCAL | `pending` | **Fix Vertex AI Image Generation**: Добавлено детальное логирование всех попыток запросов к Vertex AI (credentials, URL, response). Логирование с префиксами [VERTEX], [IMAGE_GEN], [IMAGE_EDIT] для легкой диагностики. Приоритет Vertex AI сохранён. | 2025-11-21 |
| ✅ STAGING | `f08cf8f` | **UX Improvements & Remix Tweak**: 1) Allowed all Menu/Inline buttons to work from any FSM state (auto-clear state). 2) Increased Remix media group buffer to 2.0s for better reliability. | 2025-11-21 || ✅ STAGING | `7c51e41` | **Fix Remix Media Group (Unified Buffer)**: Implemented universal Redis buffer to collect all remix images (single or album) for 1.0s. Uses Lua script for atomic fetching. Fixes race conditions and double responses. | 2025-11-21 |
| ✅ STAGING | `a0e2b4c` | **Fix Remix Media Group (Robust)**: Added Lua script for atomic Redis operations to handle media groups correctly. Enhanced `pending_caption` logic to capture caption from any photo in the group. Fixed `min_needed` to 2. | 2025-11-21 |
| ✅ STAGING | `5655735` | **Fix Remix Media Group**: Added support for collecting photos from `media_group_id`. Auto-start generation when `min_needed` (2) photos + caption are received. Fixed issue where bot ignored multiple photos. | 2025-11-21 |

## 2025-11-20 09:54 UTC — разнесение БД staging/prod
- Ветка: feature/cleanup-unused-files-ai (worktree /Users/berik/Desktop/cleanup-unused-files-ai)
- Шаг: создал отдельный Supabase проект для staging (`tg-nanobanana-staging`, ref srquwlfweefqzpowdtiw, eu-west-1), прописал новый `DATABASE_URL` в Railway staging для web/worker/beat через GraphQL, прод не трогал
- Шаг: задокументировал разделение БД (AGENTS.md)
- Проверки: `supabase projects list --output json` (статус ACTIVE_HEALTHY), GraphQL `variableUpsert` на staging-сервисы
- Коммит/PR: будет оформлен после обновления доков (текущая ветка)
- Вопросы/блокеры: нет

## 2025-11-20 10:49 UTC — фикc Supabase для stg
- Ветка: feature/cleanup-unused-files-ai (worktree /Users/berik/Desktop/cleanup-unused-files-ai)
- Шаг: удалил неудачный stg-проект Supabase (`srquwlfweefqzpowdtiw`), создал новый `tg-nanobanana-stg` (`usacvdpwwjnkazkahfwv`, eu-west-1), обновил `DATABASE_URL` в Railway staging (web/worker/beat) на пулер `aws-1-eu-west-1.pooler.supabase.com`
- Шаг: проверил деплой — миграции прошли, web поднялся, `/api/health` -> OK
- Проверки: `railway logs --service web|worker|beat --environment staging`, `curl -sSf https://web-staging-70d1.up.railway.app/api/health`
- Коммит/PR: планируется добавить изменения в docs в текущую ветку
- Вопросы/блокеры: нет
- Статус: PR #197 по ветке feature/cleanup-unused-files-ai смержен (CI passed, auto-merge), деплой staging SUCCESS (deploy 0bcc7f5e…, /api/health ok)

## 2025-11-20 11:19 UTC — PR #199 (docs db split) ожидает мержа
- Ветка: feature/cleanup-unused-files-ai (worktree /Users/berik/Desktop/cleanup-unused-files-ai)
- Шаг: добавил записи о разнесении БД и логи деплоя в docs; PR #199 открыт (mergeable/dirty state из-за fast-track, base = staging)
- Проверки: CI open-pr green, остальные не запускались; /api/health на stg OK после предыдущего деплоя
- Коммит/PR: 2125bae7, 9601d7ca, 42ae7015, 1bfafc8b (в ветке)
- Вопросы/блокеры: требуется автомерж PR #199 в staging

## 2025-11-20 14:21 UTC — починка открытия страницы оплаты
- Ветка: feature/balance-payment-issue (worktree `../balance-payment-issue`)
- Шаги: скопировал `token_packages` из продовой Supabase в staging, добавил `xframe_options_exempt` для `/miniapp/`, пушнул, дождался авто-мержа в staging (auto-merge)
- Проверки: `curl -s https://web-staging-70d1.up.railway.app/api/miniapp/pricing` (200, 4 пакета), `curl -I https://web-staging-70d1.up.railway.app/miniapp/` (200, без `X-Frame-Options`), `/api/health` OK
- Результат: деплой на staging SUCCESS, миниапп оплаты открывается, готово к тестированию в боте

## 2025-11-20 15:18 UTC — правка MiniApp оплаты
- Ветка: feature/balance-payment-issue (worktree `../balance-payment-issue`)
- Шаги: убрал DENY для /miniapp/, добавил ссылку-фолбек и построение URL из env; добавил фолбек поиска пакета по количеству токенов в create-payment
- Проверки: `/miniapp/` 200, `/api/miniapp/pricing` 200 (4 пакета), тестовый POST /api/miniapp/create-payment с pack_100 → payment_url получен
- Деплой: PR #213 → staging (auto-merge, CI lint green)

## [2025-11-21] Staging Deployment: Логирование ошибок Vertex AI

**Агент:** Gemini 3 Pro
**Ветка:** feature/add-vertex-logging
**PR:** Auto-created
**Коммит:** 1ffe0d2

### Выполненные действия:
1. Добавлено логирование ошибок (403/404) при запросах к Vertex AI в `botapp/services.py`.
2. Код пушнут в `feature/add-vertex-logging`.

### Результат:
✅ Изменения отправлены в репозиторий. Ожидается автоматический деплой в Staging для проверки логов.

## [2025-11-21] Staging Deployment: Fix Remix Media Group (Robust)

**Агент:** Gemini 3 Pro Preview
**Ветка:** feature/fix-remix-mediagroup
**PR:** #226
**Коммит:** 5655735

### Выполненные действия:
1. Исправлена логика Remix при работе с альбомами и подписями.
2. Реализован механизм `pending_caption` для сохранения подписи, даже если она пришла с первым фото, а не последним.
3. Добавлен Lua-скрипт для атомарного чтения Redis, чтобы исключить гонку процессов при параллельной обработке фото.
4. Конфликт слияния разрешен и задеплоен.

### Результат:
✅ Staging обновлен.
- Альбомы (2+ фото) обрабатываются корректно.
- Если есть подпись к любому фото в серии → авто-старт.
- Если подписи нет → бот ждет ввода текста после загрузки всех фото.
