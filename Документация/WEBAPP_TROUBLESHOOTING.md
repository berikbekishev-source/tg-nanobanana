# Гайд по устранению проблем: Не работает кнопка "Сгенерировать" в WebApp

Этот документ создан на основе реального опыта отладки Midjourney WebApp. Если вы создали WebApp для новой модели, нажимаете кнопку, а бот молчит — следуйте этому алгоритму.

---

## Симптомы
*   Кнопка `MainButton` нажимается (визуальный эффект есть).
*   WebApp закрывается (или не закрывается).
*   Бот **НЕ** присылает сообщение "Генерация началась".
*   В логах `web` сервиса тишина или непонятные ошибки.

---

## Шаг 1: Проверка Frontend (JS работает?)

Первым делом убедитесь, что обработчик клика вообще вызывается. Telegram WebApp иногда "глотает" ошибки JS.

**Решение:**
Добавьте явный `alert` перед отправкой данных в `index.html`:

```javascript
function sendData() {
    try {
        // ... сбор данных ...
        tg.showAlert("Debug: Отправка данных..."); // <--- Добавьте это
        tg.sendData(JSON.stringify(payload));
    } catch (e) {
        tg.showAlert("Error: " + e.message);
    }
}
```
*Если алерта нет* — ошибка в JS коде до этого момента (например, опечатка в ID элемента).

---

## Шаг 2: Проблема "Telegram не доставляет данные" (Transport)

**Суть проблемы:** Иногда `tg.sendData()` срабатывает визуально, но Telegram не присылает update `web_app_data` на сервер бота. Причина часто кроется в сетевых задержках или особенностях клиента.

**Решение (ОБЯЗАТЕЛЬНОЕ):** Реализовать **Dual Channel (Fallback)**.
Отправлять данные параллельно через HTTP POST запрос прямо на сервер бота.

**Frontend (`index.html`):**
```javascript
// 1. Отправляем HTTP запрос
const userId = tg.initDataUnsafe?.user?.id;
fetch('/api/<model>/webapp/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, data: payload })
}).catch(console.error);

// 2. Отправляем через Telegram с задержкой
setTimeout(() => {
    tg.sendData(JSON.stringify(payload));
    tg.close();
}, 500);
```

**Backend (`botapp/api.py`):**
Добавьте эндпоинт, который принимает этот JSON и вручную скармливает его боту:
```python
@api.post("/<model>/webapp/submit")
async def model_submit(request):
    # ... create mock Update object ...
    await dp.feed_update(bot, update)
```

---

## Шаг 3: Проблема "Грязный JSON" (Parsing Error)

**Суть проблемы:** Данные в `message.web_app_data.data` приходят как строка. Иногда Telegram (или Fallback) экранирует кавычки, превращая JSON в `{\"key\": \"value\"}`. Стандартный `json.loads()` падает.
Также бывает "Double JSON" — строка внутри строки.

**Решение (Handler):** Используйте надежный парсинг.

```python
# botapp/handlers/<model>_generation.py

try:
    raw_data = message.web_app_data.data or '{}'
    
    # 1. Fix escaped quotes
    if raw_data.startswith('{\\"'):
         try: raw_data = raw_data.encode().decode('unicode_escape')
         except: pass
    
    # 2. Parse
    payload = json.loads(raw_data)
    
    # 3. Double check if payload is still a string
    if isinstance(payload, str):
        payload = json.loads(payload)
        
except json.JSONDecodeError:
    logging.error("Failed to parse WebApp data")
    return
```

---

## Шаг 4: Ошибки логики и типов данных

Если данные дошли и распарсились, бот может упасть тихо (в логах `web` будет traceback, но юзеру ничего не придет).

**Частые причины падения:**

1.  **`Decimal` is not JSON serializable:**
    При сохранении состояния в FSM (`state.update_data`), нельзя класть объекты `Decimal` (цена).
    *   *Ошибка:* `TypeError: Object of type Decimal is not JSON serializable`
    *   *Лечение:* `model_price=float(cost)`

2.  **Неверные атрибуты модели:**
    В коде часто путают `model.max_images` (старое поле) и `model.max_input_images` (новое поле).
    *   *Ошибка:* `AttributeError: 'AIModel' object has no attribute 'max_images'`
    *   *Лечение:* Проверьте `botapp/models.py` и используйте актуальные поля.

3.  **Проверка баланса:**
    Метода `BalanceService.check_balance` больше нет.
    *   *Ошибка:* `AttributeError: 'BalanceService' has no attribute 'check_balance'`
    *   *Лечение:* Используйте `BalanceService.check_can_generate(user, model, ...)` и обрабатывайте возвращаемый кортеж `(bool, str)`.

---

## Чек-лист для Агента

Если "кнопка не работает":
1.  [ ] Добавлен ли `tg.showAlert` в JS для отладки?
2.  [ ] Реализован ли `fetch` (fallback) на `/api/...`?
3.  [ ] Добавлен ли Robust JSON Parsing в хендлер?
4.  [ ] Конвертируется ли `Decimal` в `float` перед записью в FSM?
5.  [ ] Используется ли `max_input_images` вместо `max_images`?
6.  [ ] Смотрели ли вы логи `web` (`railway logs --service web`) на предмет Traceback?

---
*Следуйте этому гайду, и вы сэкономите часы отладки.*

