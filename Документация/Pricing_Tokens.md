# Расчёт стоимости генераций и списание/зачисление токенов

## 1. Данные в базе

### pricing_settings (singleton)
- `usd_to_token_rate (T)` — сколько токенов выдаём за $1.
- `markup_multiplier (X)` — глобальная наценка (множитель).

### botapp_aimodel
- `base_cost_usd` — себестоимость одной «единицы» модели (1 изображение или 1 секунда видео).
- `cost_unit` — тип тарифа: `image`, `second`, `generation`.
- `price` — розничная цена в токенах за базовую единицу. Пересчитывается триггерами из `base_cost_usd`, `T`, `X` и `cost_unit`.
- `unit_cost_usd` — историческое поле (используется только как fallback, менять не нужно).

### botapp_genrequest
- `cost_usd` — фактическая себестоимость конкретного запроса (USD).
- `cost` — фактическая розничная стоимость запроса (токены, списанные с пользователя).

### botapp_transaction
- Хранит движение токенов по пользователю. Для генераций создаётся запись `type="generation"` с отрицательной суммой `amount=-cost`.
- При возвратах создаётся `type="refund"` на ту же сумму, но положительную.

## 2. Расчёт себестоимости (Seb)
Функция `botapp.business.pricing.calculate_request_cost` принимает модель и параметры заказа:
```
Seb = base_cost_usd * units
Price_tokens = Seb * X * T
```
Где `units` зависит от `cost_unit`:
- `image`: количество изображений (`quantity`).
- `second`: длительность (`duration` в секундах).
- `generation`: всегда 1 (фиксированная цена).

Дополнительные множители (качество, разрешение) можно описывать в `generation_params` и обрабатывать внутри `compute_seb`.

## 3. Процесс генерации
1. **Проверка:** `BalanceService.check_can_generate` получает рассчитанную стоимость в токенах и сравнивает с балансом пользователя.
2. **Списание:** `BalanceService.charge_for_generation` списывает токены и создаёт транзакцию `generation`. Одновременно `GenerationService.create_generation_request` сохраняет `cost_usd` и `cost` в `GenRequest`.
3. **Выполнение:** воркеры Celery (tasks `generate_image_task` / `generate_video_task`) выполняют запрос. При успехе `status` заявки меняется на `done`, результат сохраняется в `result_urls` и отправляется пользователю.
4. **Ошибка:** если задача падает (и после автоповторов тоже), `GenerationService.fail_generation` меняет статус на `error`, создаёт транзакцию `refund` и возвращает токены пользователю.

## 4. Интерфейс и аналитика
- Клавиатуры и меню показывают цену через `get_base_price_tokens(model)` — это `price` за базовую единицу.
- В отчётах/аналитике (`AnalyticsService`) используется та же функция, чтобы вычислять ROI и текущие тарифы.

## 5. Чек-лист проверки
1. Убедиться, что `pricing_settings` заполнены (T, X).
2. В `botapp_aimodel` заданы `base_cost_usd` и `cost_unit`; `price` пересчитан триггером.
3. Через `calculate_request_cost` проверить Seb/token стоимость для конкретных параметров.
4. Запустить генерацию:
   - Проверить, что в `GenRequest` создались `cost_usd`/`cost`, статус `done`.
   - В `botapp_transaction` появилась запись `generation` на ту же сумму.
5. Развернуть сценарий с ошибкой и убедиться, что создаётся `refund` и токены возвращаются.
6. Проверить, что `getWebhookInfo` у Telegram показывает корректный URL и нет новых ошибок `Wrong response`.

## 6. Ручное обновление тарифов
1. Меняем `base_cost_usd` и `cost_unit` у нужной модели в Supabase (например, через SQL).
2. При необходимости обновляем `usd_to_token_rate` или `markup_multiplier` в `pricing_settings`.
3. Готово — триггеры пересчитают `price`, а новое значение автоматически попадёт в UI и списания.
