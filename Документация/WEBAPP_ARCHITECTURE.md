# Архитектура WebApp для генерации контента (Эталон Midjourney)

Этот документ описывает стандарт реализации WebApp-интерфейсов для AI-моделей в проекте NanoBanana. Используйте его как ТЗ при создании интерфейсов для Kling, Nano Banana, GPT Image и других моделей.

## 1. Общая концепция

Вместо ввода команд и настроек в чате, пользователь открывает WebApp (HTML-страницу внутри Telegram), где визуально настраивает параметры генерации.

**Поток данных:**
1.  **WebApp (Frontend):** Сбор данных -> Валидация -> Отправка.
2.  **Transport:**
    *   Основной: `Telegram.WebApp.sendData()` (данные приходят в `message.web_app_data`).
    *   Резервный: `POST /api/<model>/webapp/submit` (на случай сбоя Telegram API).
3.  **Backend (Handler):** Прием -> Парсинг JSON -> Проверка баланса -> Создание задачи Celery.

---

## 2. Требования к Frontend (`webapps/<model>/index.html`)

Файл должен быть самодостаточным (HTML + CSS + JS).

### 2.1. Интерфейс (UX)
*   **Стиль:** Темная тема, цвета из `:root` переменных (соответствуют стилю бота).
*   **Кнопка действия:**
    *   ИСПОЛЬЗОВАТЬ только нативную `tg.MainButton` (синяя кнопка внизу экрана Telegram).
    *   НЕ ИСПОЛЬЗОВАТЬ HTML-кнопки на самой странице для отправки формы.
    *   **Логика видимости:** Кнопка `MainButton` должна быть **скрыта** (`.hide()`), если поле промта пустое. Появляться (`.show()`) только при наличии текста.
*   **Ошибки:** Использовать `tg.showAlert("Текст ошибки")` для уведомлений (пустой промт, нет картинки и т.д.). Не выводить ошибки текстом внизу страницы (пользователь может не увидеть).

### 2.2. Структура Payload (JSON)
WebApp должен формировать JSON-объект для отправки:

```json
{
  "kind": "<model>_settings",     // Уникальный ID (напр. midjourney_settings, kling_settings)
  "taskType": "text2image",       // Тип задачи
  "prompt": "User prompt...",     // Текст запроса
  "modelSlug": "model-slug",      // Slug модели из БД
  "imageData": "base64...",       // (Опционально) Base64 изображения
  "params": {                     // Специфичные настройки модели
     "aspect_ratio": "16:9",
     "quality": "high",
     ...
  }
}
```

### 2.3. Реализация отправки (JS Pattern)
Обязательно использовать "Двойной канал" отправки для надежности:

```javascript
function sendData() {
    // 1. Валидация
    if (!state.prompt) {
        tg.showAlert("Введите промт");
        return;
    }

    const payload = { ... }; // Сбор данных

    // 2. Резервная отправка (REST Fallback)
    const userId = tg.initDataUnsafe?.user?.id;
    if (userId) {
        fetch('/api/<model>/webapp/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, data: payload })
        }).catch(console.error);
    }

    // 3. Основная отправка (Telegram)
    setTimeout(() => {
        tg.sendData(JSON.stringify(payload));
        tg.close();
    }, 500); // Небольшая задержка для гарантии ухода fetch
}
```

---

## 3. Требования к Backend

### 3.1. API Endpoint (`botapp/api.py`)
Для каждой модели (или универсально) должен быть endpoint, принимающий данные напрямую.

```python
@api.post("/<model>/webapp/submit")
async def model_webapp_submit(request):
    # Принимает {user_id, data}
    # Создает фейковый Update с WebAppData
    # Вызывает await dp.feed_update(bot, update)
```

### 3.2. Handler (`botapp/handlers/<model>_generation.py`)

Обработчик должен быть устойчивым к ошибкам формата данных.

**Чек-лист реализации хендлера:**
1.  **Фильтр:** `@router.message(F.web_app_data)`.
2.  **Robust JSON Parsing:**
    *   Данные могут прийти с экранированными кавычками (Dirty JSON).
    *   Данные могут быть дважды закодированы (String inside String).
    *   Использовать `try-except` и повторный парсинг при необходимости.
3.  **Валидация:** Проверить поле `kind` (чтобы не обработать чужие данные).
4.  **Баланс:**
    *   Использовать `BalanceService.check_can_generate(user, model, ...)` **ДО** создания задачи.
    *   Если вернул `False` -> отправить сообщение об ошибке и прервать.
5.  **Запуск:**
    *   Сформировать `GenerationRequest`.
    *   Отправить сообщение "Генерация началась".
    *   Запустить Celery задачу.

---

## 4. Пример реализации (Midjourney)

*   **Frontend:** `webapps/midjourney/index.html`
*   **Backend:** `botapp/handlers/image_generation.py` -> `handle_midjourney_webapp_data`
*   **Fallback:** `botapp/api.py` -> `midjourney_webapp_submit`

Используйте эти файлы как эталонный код (copy-paste & adapt).

