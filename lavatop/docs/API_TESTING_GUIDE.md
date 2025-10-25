# 📘 Руководство по тестированию Lava.top API

## 🔑 Авторизация

API ключ для тестирования:
```
HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb
```

### Способы авторизации:

1. **В заголовке Authorization:**
```http
Authorization: Bearer HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb
```

2. **В параметре запроса:**
```
?api_key=HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb
```

## 📦 Products (Продукты)

### GET /api/v2/products
**Описание:** Получение списка продуктов. Обновленная версия /api/v1/feed

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v2/products" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Accept: application/json"
```

**Ожидаемый ответ:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "prod_100",
      "name": "100 Tokens",
      "price": 5.00,
      "currency": "USD",
      "active": true
    }
  ]
}
```

### PATCH /api/v2/products/{productId}
**Описание:** Обновление продукта

**Тестирование:**
```bash
curl -X PATCH "https://api.lava.top/api/v2/products/prod_100" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "price": 5.50,
    "description": "Updated description"
  }'
```

## 💳 Invoices (Счета)

### POST /api/v2/invoice
**Описание:** Создание контракта на покупку контента (аналогичен /api/v1/invoice)

**Тестирование:**
```bash
curl -X POST "https://api.lava.top/api/v2/invoice" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 5.00,
    "currency": "USD",
    "order_id": "test_order_123",
    "description": "Payment for 100 tokens",
    "success_url": "https://your-app.com/success",
    "fail_url": "https://your-app.com/fail",
    "webhook_url": "https://your-app.com/webhook"
  }'
```

**Ожидаемый ответ:**
```json
{
  "status": "success",
  "data": {
    "id": "inv_abc123",
    "url": "https://pay.lava.top/form/inv_abc123",
    "expire": "2025-10-25T16:00:00Z"
  }
}
```

### GET /api/v1/invoices
**Описание:** Получение страницы контрактов API-ключа, использованного в запросе

**Параметры запроса:**
- `limit` - количество записей (default: 50)
- `offset` - смещение (default: 0)
- `status` - фильтр по статусу (pending, success, failed)

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v1/invoices?limit=10&offset=0" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### GET /api/v1/invoices/{id}
**Описание:** Получение контракта по идентификатору

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v1/invoices/inv_abc123" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### GET /api/v2/invoices
**Описание:** Получение страницы контрактов API-ключа, использованного в запросе

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v2/invoices" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### GET /api/v2/invoices/{id}
**Описание:** Получение контракта по идентификатору

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v2/invoices/inv_abc123" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## 📊 Reports (Отчеты)

### GET /api/v1/sales
**Описание:** Получение списка продаж партнёра

**Параметры:**
- `date_from` - начальная дата (YYYY-MM-DD)
- `date_to` - конечная дата (YYYY-MM-DD)
- `product_id` - фильтр по продукту

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v1/sales?date_from=2025-10-01&date_to=2025-10-25" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### GET /api/v1/sales/{productId}
**Описание:** Получение списка продаж партнёра по конкретному продукту

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v1/sales/prod_100" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## 🔄 Subscriptions (Подписки)

### DELETE /api/v1/subscriptions
**Описание:** Отмена подписки на продукт

**Тестирование:**
```bash
curl -X DELETE "https://api.lava.top/api/v1/subscriptions" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "subscription_id": "sub_123"
  }'
```

### GET /api/v1/subscriptions
**Описание:** Получение страницы подписок API-ключа, использованного в запросе

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v1/subscriptions" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### GET /api/v1/subscriptions/{id}
**Описание:** Получение подписки по идентификатору контракта

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v1/subscriptions/sub_123" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## 💝 Donate (Донаты)

### GET /api/v1/donate
**Описание:** Получение ссылки на донат аккаунта

**Тестирование:**
```bash
curl -X GET "https://api.lava.top/api/v1/donate" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## 🔔 Webhooks

### POST /example-of-webhook-route-contract
**Описание:** Пример API-метода, который должен создать сервис автора для приёма вебхуков от lava.top

**Структура webhook от Lava.top:**
```json
{
  "id": "payment_12345",
  "order_id": "test_order_123",
  "status": "success",
  "amount": 5.00,
  "currency": "USD",
  "buyer_email": "buyer@example.com",
  "product_id": "prod_100",
  "timestamp": "2025-10-25T15:30:00Z",
  "signature": "sha256_signature_here"
}
```

**Обработка webhook в вашем приложении:**
```python
@app.post("/api/miniapp/lava-webhook")
def handle_webhook(request):
    # 1. Проверка подписи
    signature = request.headers.get('X-Signature')
    if not verify_signature(request.body, signature):
        return {"error": "Invalid signature"}, 401

    # 2. Парсинг данных
    data = json.loads(request.body)

    # 3. Обработка статуса
    if data['status'] == 'success':
        # Найти транзакцию
        transaction = Transaction.get(order_id=data['order_id'])

        # Обновить статус
        transaction.status = 'completed'

        # Начислить токены
        user = transaction.user
        user.balance += calculate_tokens(data['amount'])

    return {"ok": True}, 200
```

## 🧪 Тестовые сценарии

### 1. Полный цикл платежа

```python
# 1. Создать invoice
invoice = create_invoice(amount=5.00, order_id="test_123")

# 2. Получить payment URL
payment_url = invoice['url']

# 3. Пользователь оплачивает по ссылке

# 4. Получить webhook о успешной оплате

# 5. Проверить статус invoice
status = get_invoice_status(invoice['id'])
assert status == 'success'
```

### 2. Тестирование продуктов

```python
# 1. Получить список продуктов
products = get_products()

# 2. Обновить цену продукта
update_product(product_id='prod_100', price=5.50)

# 3. Проверить обновление
product = get_product('prod_100')
assert product['price'] == 5.50
```

### 3. Тестирование отчетов

```python
# 1. Создать несколько тестовых платежей

# 2. Получить отчет по продажам
sales = get_sales_report(date_from='2025-10-01', date_to='2025-10-25')

# 3. Проверить суммы и количество
assert sales['total'] > 0
```

## 🚨 Обработка ошибок

### Коды ответов:
- `200 OK` - Успешный запрос
- `201 Created` - Ресурс создан
- `400 Bad Request` - Неверные параметры
- `401 Unauthorized` - Неверный API ключ
- `404 Not Found` - Ресурс не найден
- `429 Too Many Requests` - Превышен лимит запросов
- `500 Internal Server Error` - Ошибка сервера

### Формат ошибок:
```json
{
  "status": "error",
  "error": {
    "code": "INVALID_PARAMETERS",
    "message": "Amount must be greater than 0",
    "details": {
      "field": "amount",
      "value": -5
    }
  }
}
```

## 📝 Запуск тестов

### Python скрипт:
```bash
# Установить зависимости
pip install requests

# Запустить тесты
python lavatop/tests/test_lava_api.py
```

### Postman коллекция:
1. Импортировать endpoints в Postman
2. Добавить API ключ в переменные окружения
3. Запустить коллекцию тестов

### cURL команды:
```bash
# Сохранить API ключ
export LAVA_API_KEY="HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb"

# Запустить тесты
./test_lava_api.sh
```

## ⚠️ Важные замечания

1. **Безопасность:** Никогда не храните API ключ в коде
2. **Rate Limits:** Ограничение 60 запросов в минуту
3. **Webhook URL:** Должен быть публично доступен (HTTPS)
4. **Идемпотентность:** Обработчик webhook должен быть идемпотентным
5. **Таймауты:** Установите таймауты на запросы (30 секунд)
6. **Логирование:** Логируйте все платежные операции
7. **Тестовый режим:** Используйте тестовые карты для проверки

## 📚 Дополнительные ресурсы

- [Официальная документация Lava.top](https://lava.top/docs)
- [Примеры интеграций](https://github.com/lava-top/examples)
- [SDK для различных языков](https://lava.top/sdk)
- Поддержка: support@lava.top