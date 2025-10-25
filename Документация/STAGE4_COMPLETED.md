# ✅ Этап 4: Генерация видео — ЗАВЕРШЕН

## 📊 Что сделано

### 1. Поддержка Veo (Vertex AI)
- Реализован провайдер `botapp/providers/video/vertex.py` с методом `predictLongRunning`.
- Добавлены alias-ы имён моделей и опрос долгих операций.
- Обработаны ошибки квот, IAM и неверных параметров.

### 2. Цикл генерации видео
- `botapp/tasks.generate_video_task` инициирует запрос, отслеживает операцию, загружает mp4 в Supabase Storage и отправляет пользователю через Telegram.
- Сервис `GenerationService` закрывает запрос со статусами `processing/done/error`, ведёт учёт транзакции и возвратов.
- Задача выполняется в Celery worker (`worker-production-cebd.up.railway.app`) с очередью `default`.

### 3. Хранение в БД и Supabase
- Модель `GenRequest` хранит метаданные (job_id, duration, resolution, aspect_ratio, result_urls).
- Supabase bucket `video_veo3` содержит итоговые ролики; ссылки делаются публичными.
- Исправлено ограничение `provider_job_id` → `CharField(max_length=512)` (миграция `0009_alter_genrequest_provider_job_id.py`).

## 🎬 Как работает функция «Сгенерировать видео»

1. Пользователь выбирает модель Veo и отправляет текстовый или remix-запрос.
2. `GenerationService.start_generation()` создаёт запись `GenRequest`, резервирует токены, фиксирует транзакцию.
3. Celery-воркер выполняет `generate_video_task`:
   - Формирует payload из prompt и параметров.
   - Получает access token по `GOOGLE_APPLICATION_CREDENTIALS_JSON`.
   - Вызывает Vertex AI `predictLongRunning`, далее `fetchPredictOperation` до завершения.
   - Загружает результат в Supabase Storage (путь `videos/<UUID>.mp4>`).
   - Обновляет `GenRequest` и отправляет ролик в Telegram с подписью и inline-меню.
4. При ошибке — выполняется `GenerationService.fail_generation()`, делается refund и пользователю отправляется уведомление.

## 🧪 Проверка работоспособности

```bash
# Логи воркера
railway logs --service worker --lines 100

# Проверка последнего запроса в БД
DATABASE_URL=postgresql://... .venv/bin/python manage.py shell -c "
from botapp.models import GenRequest
req = GenRequest.objects.order_by('-created_at').first()
print(req.status, req.provider_job_id, req.result_urls)
"
```

Ожидаемо:
- В логах видим успешные ответы Vertex AI, Supabase и Telegram: `Task ... succeeded`.
- В БД `status='done'`, `provider_job_id` содержит длинный идентификатор операции, `result_urls` — публичный Supabase URL.

## 🚀 Рекомендации дальше

1. Настроить лимиты и мониторинг Google Cloud, чтобы контролировать квоты Veo.
2. Добавить ретраи/уведомления при выдаче Veo `429` или `403`.
3. Реализовать UI в боте для отображения истории видеогенераций.
4. Вынести конфиг длительности/разрешения в настройки модели для гибкости.

---

**Этап 4 успешно завершён!** 🎉 Видео генерируется, сохраняется и доставляется пользователям стабильным образом.
