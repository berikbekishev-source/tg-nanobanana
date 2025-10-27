# 🧪 Настройка тестового режима Lava.top

## 📋 Подготовка к тестированию без реальных платежей

### 1. Настройка в личном кабинете Lava.top

1. **Войдите в личный кабинет:**
   ```
   https://lava.top/login
   ```

2. **Активируйте тестовый режим:**
   - Настройки → API → Тестовый режим
   - Включите опцию "Test Mode"
   - Сохраните изменения

3. **Создайте тестовый продукт:**
   - Продукты → Добавить продукт
   - Название: "TEST - 100 Tokens"
   - Цена: $5.00
   - Отметьте "Тестовый продукт"

4. **Настройте webhook для тестов:**
   - Webhooks → Добавить webhook
   - URL: Ваш webhook endpoint
   - События: Payment Success, Payment Failed
   - Включите "Отправлять тестовые вебхуки"

### 2. Методы получения реальных вебхуков

#### Вариант A: Использование Railway (Продакшн)

```bash
# Получите публичный URL вашего приложения
railway status

# URL для вебхуков будет:
https://your-app.railway.app/api/miniapp/lava-webhook
```

#### Вариант B: Локальное тестирование с ngrok

```bash
# 1. Установите ngrok
brew install ngrok/ngrok/ngrok

# 2. Запустите локальный сервер
python manage.py runserver

# 3. Запустите ngrok туннель
ngrok http 8000

# 4. Используйте ngrok URL для вебхуков
https://abc123.ngrok.io/api/miniapp/lava-webhook
```

#### Вариант C: Использование webhook.site

```bash
# 1. Откройте webhook.site
https://webhook.site

# 2. Скопируйте уникальный URL
https://webhook.site/unique-id

# 3. Используйте его для тестирования
```

### 3. Тестовые карты Lava.top

Lava.top предоставляет специальные тестовые карты для симуляции различных сценариев:

| Номер карты | Результат | CVV | Срок |
|-------------|-----------|-----|------|
| 4111 1111 1111 1111 | Успешный платеж | 123 | 12/25 |
| 4000 0000 0000 0002 | Отклонено банком | 123 | 12/25 |
| 4000 0000 0000 0069 | Недостаточно средств | 123 | 12/25 |
| 4000 0000 0000 0127 | Требуется 3D Secure | 123 | 12/25 |
| 4000 0000 0000 3055 | Таймаут платежа | 123 | 12/25 |

### 4. API endpoints для тестового режима

При работе в тестовом режиме добавляйте заголовок:
```
X-Test-Mode: true
```

### 5. Запуск тестов

#### Быстрый тест с Railway:

```bash
# 1. Установите переменные окружения
export LAVA_API_KEY="HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb"
export RAILWAY_PUBLIC_DOMAIN="your-app.railway.app"

# 2. Запустите тест
python lavatop/tests/test_real_webhooks.py

# 3. Выберите вариант 1 (Railway webhook)
```

#### Локальный тест с ngrok:

```bash
# 1. Запустите Django сервер
python manage.py runserver

# 2. В новом терминале запустите тест
python lavatop/tests/test_real_webhooks.py

# 3. Выберите вариант 2 (Local + ngrok)
```

### 6. Проверка вебхуков

#### Мониторинг в Railway:

```bash
# Следите за логами в реальном времени
railway logs --service web | grep "Lava webhook"

# Или через веб-интерфейс
railway open
```

#### Локальный мониторинг:

```bash
# Django логи покажут входящие запросы
tail -f logs/payment.log
```

### 7. Типичный сценарий тестирования

```python
# 1. Создание тестового платежа
POST /api/miniapp/create-payment
{
  "email": "test@example.com",
  "credits": 100,
  "amount": 5.00,
  "currency": "USD"
}

# 2. Получение payment_url
{
  "payment_url": "https://pay.lava.top/form/test_123",
  "payment_id": "test_123"
}

# 3. Оплата тестовой картой (в браузере или автоматически)
# Используйте карту: 4111 1111 1111 1111

# 4. Получение вебхука от Lava.top
POST /api/miniapp/lava-webhook
{
  "order_id": "test_123",
  "status": "success",
  "amount": 5.00,
  "test_mode": true
}

# 5. Проверка обновления баланса
GET /api/miniapp/payment-status/test_123
{
  "status": "completed",
  "tokens_credited": 100
}
```

### 8. Автоматизированное тестирование

#### Создайте bash скрипт для полного цикла:

```bash
#!/bin/bash
# test_payment_flow.sh

echo "🚀 Starting payment test flow..."

# 1. Создаем платеж
PAYMENT_RESPONSE=$(curl -s -X POST \
  http://localhost:8000/api/miniapp/create-payment \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "credits": 100,
    "amount": 5.00
  }')

PAYMENT_ID=$(echo $PAYMENT_RESPONSE | jq -r '.payment_id')
echo "✅ Payment created: $PAYMENT_ID"

# 2. Симулируем оплату (если API поддерживает)
curl -X POST \
  https://api.lava.top/test/complete-payment \
  -H "Authorization: Bearer $LAVA_API_KEY" \
  -H "X-Test-Mode: true" \
  -d "{\"payment_id\": \"$PAYMENT_ID\"}"

echo "✅ Payment completed in test mode"

# 3. Ждем вебхук
echo "⏳ Waiting for webhook..."
sleep 5

# 4. Проверяем статус
STATUS=$(curl -s \
  http://localhost:8000/api/miniapp/payment-status/$PAYMENT_ID \
  | jq -r '.status')

if [ "$STATUS" = "completed" ]; then
  echo "✅ Test passed! Payment completed successfully"
else
  echo "❌ Test failed! Status: $STATUS"
fi
```

### 9. Отладка проблем с вебхуками

#### Если вебхуки не приходят:

1. **Проверьте доступность URL:**
   ```bash
   curl -X POST https://your-webhook-url \
     -H "Content-Type: application/json" \
     -d '{"test": true}'
   ```

2. **Проверьте логи Lava.top:**
   - Личный кабинет → Webhooks → История отправок

3. **Проверьте сетевые настройки:**
   - Firewall не блокирует входящие соединения
   - SSL сертификат валидный (для HTTPS)

4. **Используйте webhook.site для диагностики:**
   - Временно перенаправьте вебхуки на webhook.site
   - Проверьте, что Lava.top отправляет запросы

### 10. CI/CD интеграция

#### GitHub Actions:

```yaml
name: Test Payment System

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Setup Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt

    - name: Run payment tests
      env:
        LAVA_API_KEY: ${{ secrets.LAVA_API_KEY }}
        TEST_MODE: true
      run: |
        python lavatop/tests/test_real_webhooks.py
```

## 📊 Мониторинг тестов

### Dashboard для отслеживания:

1. **Количество тестовых платежей**
2. **Успешность вебхуков**
3. **Время отклика**
4. **Ошибки обработки**

### Логирование:

```python
import logging

logger = logging.getLogger('payment.test')

# Логируем каждый этап
logger.info(f"Test payment created: {payment_id}")
logger.info(f"Webhook received: {webhook_data}")
logger.info(f"Balance updated: {new_balance}")
```

## ✅ Чек-лист для тестирования

- [ ] Тестовый режим активирован в Lava.top
- [ ] Webhook URL доступен публично
- [ ] API ключ настроен правильно
- [ ] Тестовые карты работают
- [ ] Вебхуки приходят и обрабатываются
- [ ] Баланс обновляется корректно
- [ ] Транзакции сохраняются в БД
- [ ] Уведомления отправляются пользователю
- [ ] Ошибки обрабатываются корректно
- [ ] Логи записываются правильно

## 🆘 Поддержка

- **Lava.top Support:** support@lava.top
- **API Documentation:** https://lava.top/docs/api
- **Test Console:** https://lava.top/test-console