# Интеграция Midjourney (через KIE.AI)

Мы используем KIE.AI как прокси к Midjourney. Тот же API и ключ, что и для Kling, позволяет запускать text2image и image2image задания. В рамках проекта добавлена модель `midjourney-v7-fast` (провайдер `midjourney`), она появляется в списке доступных AI-моделей автоматически после применения миграций.

## Переменные окружения

Добавьте их в Railway (`worker`) или `.env`:

| Переменная | Описание |
| --- | --- |
| `KIE_API_KEY` | Глобальный ключ KIE.AI. Используется и для Midjourney, и для Kling (можно хранить один раз). |
| `MIDJOURNEY_KIE_API_KEY` | (Опционально) отдельный ключ. Если не задан, берётся `KIE_API_KEY`. |
| `MIDJOURNEY_KIE_BASE_URL` | Базовый URL KIE (`https://api.kie.ai`). |
| `MIDJOURNEY_KIE_TEXT_MODEL` | Модель для text2image. По умолчанию `midjourney/v6-text-to-image`. |
| `MIDJOURNEY_KIE_IMAGE_MODEL` | Модель для image2image. По умолчанию `midjourney/v6-image-to-image`. |
| `MIDJOURNEY_KIE_POLL_INTERVAL` / `MIDJOURNEY_KIE_POLL_TIMEOUT` | Интервал опроса и таймаут ожидания задачи (секунды). |
| `MIDJOURNEY_KIE_REQUEST_TIMEOUT` | Таймаут HTTP-запросов к KIE (секунды). |

## Как работает генерация

1. **Создание задачи.** Для каждого изображения вызывается `POST https://api.kie.ai/api/v1/jobs/createTask` с JSON:
   ```json
   {
     "model": "midjourney/v6-text-to-image",
     "input": {
       "prompt": "<user prompt>",
       "aspect_ratio": "1:1",
       "quality": "standard",
       "negative_prompt": "...",
       "cfg_scale": 0.5
     }
   }
   ```
   - `midjourney_options` из `generation_params` попадают внутрь `input`.
   - Для режима `image2image` первое входное изображение конвертируется в PNG и загружается в Supabase (`supabase_upload_png`). KIE получает публичный URL в поле `image_url`.
2. **Опрос статуса.** Раз в `MIDJOURNEY_KIE_POLL_INTERVAL` секунд дергаем `GET /api/v1/jobs/recordInfo?taskId=...`. Ждём статусы `waiting/queuing/generating` → `success`. Если `state=fail`, сообщение из `failMsg` прилетает пользователю.
3. **Получение результата.** В ответе `data.resultJson` лежит JSON `{"resultUrls": ["https://..."]}`. Мы скачиваем первый URL и отправляем изображение в телеграм + сохраняем в Supabase, как и в остальных провайдерах.

Каждое изображение генерируется отдельной задачей KIE, поэтому `quantity>1` запускает несколько последовательных `createTask`.

## Поддерживаемые параметры

В `generation_params` можно указать:

| Поле | Описание |
| --- | --- |
| `aspect_ratio` | Соотношение сторон (`1:1`, `16:9`, `9:16`, `3:2`, `2:3`). |
| `quality` | `standard` или `high`. |
| `negative_prompt` | Текст, чего избегать (до 2500 символов). |
| `cfg_scale` | От 0 до 1 (шаг 0.1). |
| `chaos`, `seed`, `style`, `mode` | Пробрасываются как есть в `input`. |
| `midjourney_options` | Произвольный словарь, который мержится в `input` без изменений. Полезно для параметров, которые появятся в будущем. |

## Модель в каталоге

Миграция `0026_alter_aimodel_provider.py` создаёт AI-модель:

```
Slug: midjourney-v7-fast
Name: Midjourney V6
Provider: midjourney
Supports image input: yes (1 файл)
Цена: 79 токенов
```

Вы можете отредактировать цену, описание и порядок отображения в админке (`/admin/botapp/aimodel/`).

## Типичные ошибки

| Сообщение | Что значит |
| --- | --- |
| `Midjourney (KIE) createTask error ...` | KIE вернул ошибку на этапе создания задания. Проверьте ключ/лимиты. |
| `Midjourney (KIE) не вернул ссылки на изображения` | В ответе отсутствует `resultUrls`. Такое бывает, если задача упала, но state ещё не `fail`. Попробуйте позже. |
| `Не удалось загрузить изображение в Supabase ...` | Для режима img2image не получилось сохранить файл. Убедитесь, что `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` заданы и bucket `bot-images` существует. |
| `KIE.AI recordInfo error ...` | KIE вернул не 200 при опросе статуса (часто из-за истёкшего taskId или неверного API key). |

## Чек-лист

1. Настройте `KIE_API_KEY` (или `MIDJOURNEY_KIE_API_KEY`) в Railway.
2. Примените миграции (`python3 manage.py migrate` выполняется автоматически при деплое).
3. Убедитесь, что Supabase buckets `images` и `videos` доступны (для загрузки исходников/результатов).
4. Активируйте модель `Midjourney V6` в админке, задайте цену/порядок.
5. Протестируйте оба режима: text2image и image2image (добавьте фотографию + промт).
