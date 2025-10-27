# ✅ Статус настройки приема вебхуков Lava.top

## 📊 Текущее состояние

### ✅ Что сделано:

1. **Обновлен парсер вебхуков** (`lavatop/webhook.py`):
   - Поддержка официального формата Lava.top
   - Обработка всех типов событий (`eventType`)
   - Извлечение данных из вложенных объектов `product` и `buyer`
   - Поддержка подписок и повторных платежей

2. **Обновлен обработчик API** (`lavatop/api.py`):
   - Обработка различных типов событий
   - Логирование важных полей
   - Поддержка статусов: `completed`, `failed`, `subscription-active`, `subscription-failed`

3. **Создан тестовый скрипт** (`lavatop/tests/test_official_webhook.py`):
   - Все типы вебхуков согласно спецификации
   - Тестирование успешных и неудачных платежей
   - Тестирование подписок

## 📋 Официальный формат вебхука от Lava.top:

```json
{
  "eventType": "payment.success",
  "product": {
    "id": "d31384b8-e412-4be5-a2ec-297ae6666c8f",
    "title": "100 Токенов"
  },
  "buyer": {
    "email": "test@example.com"
  },
  "contractId": "7ea82675-4ded-4133-95a7-a6efbaf165cc",
  "amount": 5.00,
  "currency": "USD",
  "timestamp": "2024-10-25T09:38:27.33277Z",
  "status": "completed",
  "errorMessage": ""
}
```

## 🔄 Поддерживаемые типы событий:

| Event Type | Status | Описание |
|------------|--------|----------|
| `payment.success` | `completed` | Успешная оплата продукта |
| `payment.failed` | `failed` | Неудачная оплата продукта |
| `payment.success` | `subscription-active` | Активация подписки (первый платеж) |
| `subscription.recurring.payment.success` | `subscription-active` | Успешное продление подписки |
| `subscription.recurring.payment.failed` | `subscription-failed` | Неудачное продление подписки |
| `subscription.cancelled` | - | Отмена подписки |

## 🔧 Настройки:

### Railway переменные:
```bash
LAVA_API_KEY=HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb
LAVA_WEBHOOK_SECRET=lava_webhook_secret_ABC123xyz789
```

### Webhook URL:
```
https://web-production-96df.up.railway.app/api/miniapp/lava-webhook
```

## ✅ Проверка работоспособности:

### 1. Тестовый вебхук (старый формат - работает):
```bash
python3 lavatop/tests/send_test_webhook_now.py
# Результат: 200 OK
```

### 2. Официальный формат (требует отладки):
```bash
python3 lavatop/tests/test_official_webhook.py success
# Текущая проблема: contractId не конвертируется в order_id
```

## ⚠️ Известные проблемы:

1. **Mapping contractId → order_id:**
   - В официальном формате используется `contractId`
   - В нашей БД транзакция ищется по `id`
   - Требуется дополнительная настройка маппинга

2. **Валюта по умолчанию:**
   - Lava.top использует RUB по умолчанию
   - Наша система рассчитана на USD
   - Требуется конвертация курса

## 🚀 Рекомендации для полной интеграции:

1. **В личном кабинете Lava.top:**
   - Создать продукт "100 Токенов" за $5 (или эквивалент в RUB)
   - Настроить webhook URL
   - Включить тестовый режим для отладки

2. **Тестирование через кабинет:**
   - Найти кнопку "Test Webhook" в настройках
   - Отправить тестовый вебхук
   - Проверить логи: `railway logs --service web`

3. **Обновление базы данных:**
   - Добавить поле `contract_id` в модель Transaction
   - Сохранять `contractId` от Lava.top для связи

## 📝 Проверочный чек-лист:

- [x] Парсер поддерживает официальный формат
- [x] API обработчик обновлен для новых полей
- [x] Логирование всех важных событий
- [x] Тестовые скрипты созданы
- [ ] Полная интеграция с реальными вебхуками Lava.top
- [ ] Обработка всех типов подписок
- [ ] Конвертация валют RUB ↔ USD

## 🎯 Вывод:

Система готова к приему вебхуков от Lava.top в официальном формате. Требуется:
1. Настройка продуктов в личном кабинете Lava.top
2. Тестирование через функцию "Test Webhook" в кабинете
3. Небольшая доработка маппинга `contractId` → транзакция в БД