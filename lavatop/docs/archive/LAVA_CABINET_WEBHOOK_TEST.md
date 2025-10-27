# 🔔 Тестирование вебхуков через личный кабинет Lava.top

## Пошаговая инструкция для отправки тестового вебхука

### 1. Войдите в личный кабинет Lava.top

```
https://lava.top/login
```

Используйте ваш API ключ или логин/пароль для входа.

### 2. Перейдите в раздел Webhooks

В личном кабинете найдите один из разделов:
- **Настройки → Webhooks**
- **API → Webhooks**
- **Инструменты → Webhooks**
- **Developer → Webhooks**

### 3. Найдите функцию тестирования

Ищите кнопки или ссылки:
- **"Test Webhook"** / "Тестировать вебхук"
- **"Send Test"** / "Отправить тест"
- **"Trigger Test"** / "Запустить тест"
- **"Send Sample"** / "Отправить пример"
- **"Test Connection"** / "Проверить соединение"

### 4. Настройте тестовый вебхук

#### Укажите URL вашего webhook endpoint:

**Для Railway (продакшн):**
```
https://web-production-96df.up.railway.app/api/miniapp/lava-webhook
```

**Для локальной разработки (через ngrok):**
```
https://your-ngrok-id.ngrok.io/api/miniapp/lava-webhook
```

#### Выберите тип события:
- **payment.success** - успешный платеж
- **payment.failed** - неудачный платеж
- **payment.pending** - платеж в обработке

### 5. Типичное расположение функции тестирования

#### Вариант A: На странице списка вебхуков
```
Webhooks → [Ваш webhook] → Actions → Test
                                  ↓
                            [Test Webhook]
```

#### Вариант B: На странице редактирования вебхука
```
Webhooks → Edit → [Test Connection] кнопка
```

#### Вариант C: В разделе инструментов разработчика
```
Developer Tools → Webhook Tester → Send Test Event
```

### 6. Пример интерфейса (типичный вид)

```
┌─────────────────────────────────────────┐
│ Webhook Settings                        │
├─────────────────────────────────────────┤
│ URL: [_________________________________] │
│      https://web-production-96df...      │
│                                         │
│ Events: ☑ Payment Success              │
│         ☑ Payment Failed               │
│         ☐ Subscription Created         │
│                                         │
│ [Save] [Test Webhook] [View Logs]      │
└─────────────────────────────────────────┘
```

### 7. Что искать в интерфейсе

Ключевые слова и иконки:
- 🔔 Bell icon (уведомления)
- 🧪 Test tube icon (тестирование)
- ⚡ Lightning bolt (события)
- 📤 Outbox arrow (отправка)
- "Ping" / "Echo" / "Test"

### 8. Тестовые данные, которые обычно отправляются

```json
{
  "id": "test_webhook_12345",
  "type": "payment.success",
  "test": true,
  "data": {
    "order_id": "test_order_123",
    "amount": 5.00,
    "currency": "USD",
    "status": "success",
    "customer_email": "test@example.com",
    "payment_method": "card",
    "created_at": "2025-10-25T12:00:00Z"
  },
  "signature": "test_signature_abc123"
}
```

### 9. Альтернативные способы в личном кабинете

#### A. Через историю платежей:
```
Payments → [Select Payment] → Actions → Resend Webhook
```

#### B. Через API консоль:
```
API Console → POST /webhooks/test → Execute
```

#### C. Через журнал событий:
```
Events Log → [Select Event] → Replay
```

### 10. Проверка получения вебхука

#### Для Railway:
```bash
# Смотрите логи в реальном времени
railway logs --service web | grep "webhook"

# Или через веб-интерфейс
railway open
```

#### В личном кабинете Lava.top:
Обычно есть раздел с логами отправки:
```
Webhooks → Delivery Logs
         → Last Response: 200 OK ✅
         → Response Time: 245ms
         → Response Body: {"ok": true}
```

## 🎯 Быстрая проверка

1. **Откройте два окна:**
   - Личный кабинет Lava.top
   - Railway logs (или ваши логи)

2. **В Lava.top:**
   - Найдите кнопку Test Webhook
   - Нажмите её

3. **В логах должно появиться:**
```
Lava webhook received: {...}
Payment test_123 completed
```

## ⚠️ Если не можете найти функцию тестирования

### Создайте тестовый платеж вручную:

1. **В разделе Payments/Invoices:**
   - Create Test Payment
   - Или используйте Sandbox mode

2. **Или через API Console в кабинете:**
```javascript
// Если есть встроенная консоль API
api.createTestPayment({
  amount: 5.00,
  webhook_url: "https://your-webhook-url"
})
```

## 📞 Контакты поддержки

Если не можете найти функцию тестирования:
- **Email:** support@lava.top
- **Telegram:** @lavatop_support
- **Вопрос:** "Как отправить тестовый webhook из личного кабинета?"

## 🔍 Скриншоты для поиска

Ищите элементы интерфейса похожие на:
- Кнопка "Test" рядом с URL вебхука
- Выпадающее меню "Actions" с опцией "Send Test"
- Вкладка "Testing" или "Debug"
- Иконка молнии (⚡) для быстрых действий