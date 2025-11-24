## [2025-11-23] Documentation & Finalization

**Агент:** Agent (Session 9K9rh)  
**Ветка:** chore-debug-telegram-send-9K9rh  
**PR:** #308  
**Коммит:** (Latest HEAD)

### Выполненные действия:
1. **Security & Cleanup:**
   - Восстановлена проверка `X-Telegram-Bot-Api-Secret-Token`.
   - Удалены отладочные `print`.
2. **UI/UX WebApp:**
   - Удалена дублирующая кнопка "Сгенерировать".
   - Реализована динамическая видимость `MainButton`.
   - Внедрены `tg.showAlert` для валидации.
3. **Documentation:**
   - Создан файл `Документация/WEBAPP_ARCHITECTURE.md` (ТЗ для масштабирования).

### Результат:
Staging полностью обновлен. Файл архитектуры доступен в репозитории.

## [2025-11-23] Kling WebApp: REST-стандарт и фиксы провайдера

**Агент:** Codex  
**Ветка:** feature/agent-codex-rules-railway-08  
**PR:** #315 (auto-merge → staging)  
**Коммиты:** 6e6ffecf, bcc29be5, 2b24212c

### Выполненные действия:
1. Привёл Kling WebApp к обязательному REST-потоку для inline-кнопок: отправка через `fetch /api/kling/webapp/submit`, `MainButton` с прогрессом, валидация/ошибки через `tg.showAlert`.
2. Убрал `tg.sendData` (не работает с inline), оставил единственный канал через REST.
3. Исправил `generate_video_task`: не передаём `last_frame_*` для провайдера Kling, устранил ошибку `unexpected keyword argument 'last_frame_media'`.
4. Разрешил конфликты со свежим staging (обновления Veo/handlers), проверил успешную генерацию и доставку видео в staging.

### Результат:
- Staging содержит актуальный REST-флоу для Kling WebApp и стабильный вызов Kling провайдера; генерация проходит, видео доставляется пользователю.


## [2025-11-23] Sora2 WebApp: кнопка, цена и отправка

**Агент:** Codex  
**Ветка:** feature/sora2-webapp-fix  
**PR:** (не создан)  
**Коммит:** 4d2e1ac2 (локально, не пушен)

### Выполненные действия:
1. Привёл WebApp Sora 2 к поведению Midjourney: MainButton отображается при наличии промта, цена выводится на кнопке и в шапке.
2. Добавил tg.sendData с алертом «Отправка данных…» и REST-фолбек `/api/sora2/webapp/submit`, убрал зависимость от CSRF и жёсткой проверки userId.
3. Инициализация выставляет цену по query/start_param, скрывает блок загрузки по умолчанию.

### Результат:
- UI и отправка Sora 2 работают как в эталонном Midjourney; данные уходят через sendData + резервный REST.


## [2025-11-24] Staging Deployment: Fix Kling WebApp Generation

**Агент:** Antigravity
**Ветка:** feature/fix-kling-webapp
**PR:** #336 (Status: MERGEABLE)

### Выполненные действия:
1.  Обнаружена проблема с зависанием запроса при закрытии WebApp в Kling.
2.  Внесены изменения в `webapps/kling/index.html`: добавлен `keepalive: true` и таймаут 15с.
3.  Push в GitHub.

### Результат:
✅ Ожидается деплой на Staging.

## [2025-11-24] Debugging Kling WebApp

**Агент:** Antigravity
**Ветка:** feature/fix-kling-webapp
**PR:** #336

### Проблема:
Пользователь сообщает, что кнопка не работает. Логи сервера показывают, что запросы пользователя не доходят (хотя curl работает).

### Действия:
1.  Добавлен `window.onerror` для вывода ошибок JS в alert.
2.  Убран `AbortController` (заменен на Promise.race) для совместимости.
3.  Добавлен try-catch вокруг всей функции отправки.

### Цель:
Увидеть ошибку на клиенте (через alert) или заставить запрос пройти.
