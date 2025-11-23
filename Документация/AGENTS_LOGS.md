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
