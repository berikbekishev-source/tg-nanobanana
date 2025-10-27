# Telegram Mini App - Страница оплаты токенов

## Описание

Telegram Mini App для пополнения баланса пользователей бота. Позволяет выбрать количество токенов и оплатить их через карту VISA/MasterCard.

## Структура файлов

```
miniapp/
├── __init__.py
├── api.py                  # API endpoints для платежей
├── views.py                # Django views
├── README.md               # Эта документация
├── static/
│   ├── index.html         # Главная страница Mini App
│   ├── styles.css         # CSS стили
│   └── payment.js         # JavaScript логика
├── templates/
└── payment_providers/
    └── __init__.py
```

## Возможности

1. **Выбор количества токенов**
   - 100 токенов = $5
   - 200 токенов = $10
   - 500 токенов = $25
   - 1000 токенов = $50

2. **Интеграция с Telegram**
   - Автоматическое получение данных пользователя из Telegram
   - Валидация init_data от Telegram Web App
   - Адаптация под тему Telegram

3. **Способ оплаты**
   - Карта VISA/MasterCard (KZ/CHF)

4. **Безопасность**
   - Валидация данных от Telegram Web App
   - CSRF защита
   - Проверка подписи init_data

## API Endpoints

### POST /api/miniapp/create-payment
Создание платежа для пополнения баланса

**Request Body:**
```json
{
  "email": "user@example.com",
  "credits": 100,
  "amount": 5.0,
  "currency": "USD",
  "payment_method": "card",
  "user_id": 123456789,
  "init_data": "query_id=..."
}
```

**Response:**
```json
{
  "success": true,
  "payment_url": "https://payment.example.com/...",
  "payment_id": "123"
}
```

### GET /api/miniapp/payment-status/{payment_id}
Проверка статуса платежа

**Response:**
```json
{
  "success": true,
  "status": "pending",  // или "completed", "failed"
  "amount": 5.0,
  "created_at": "2025-10-24T12:00:00Z"
}
```

### POST /api/miniapp/payment-webhook
Webhook для обработки callback от платежной системы

## Использование

### 1. Запуск локально

```bash
# Установить зависимости
pip install -r requirements.txt

# Запустить сервер
python manage.py runserver
```

Откройте: http://localhost:8000/miniapp/

### 2. Интеграция с ботом

В коде бота используйте:

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(
        text="💳 Пополнить баланс",
        web_app=WebAppInfo(url=f"{PUBLIC_BASE_URL}/miniapp/")
    )]
])
```

### 3. Настройка переменных окружения

Добавьте в `.env`:

```env
PUBLIC_BASE_URL=https://your-domain.com
TELEGRAM_BOT_TOKEN=your_bot_token
```

## TODO: Интеграция платежной системы

Текущая версия включает базовую структуру. Для полной интеграции необходимо:

1. **Выбрать платежный провайдер:**
   - Stripe
   - Kaspi.kz
   - PayPal
   - Другие

2. **Реализовать в `miniapp/payment_providers/`:**
   - Создание платежа
   - Обработка webhook
   - Обновление статуса транзакции
   - Начисление токенов

3. **Обновить `miniapp/api.py`:**
   - Заменить TODO в `create_payment()`
   - Реализовать `payment_webhook()`

## Дизайн

Дизайн выполнен в темной теме согласно макету:
- Черный фон (#1a1a1a)
- Серые карточки (#2d2d2d)
- Белые активные элементы
- Адаптивная верстка для мобильных устройств

## Безопасность

- Валидация всех входных данных
- Проверка подписи Telegram init_data
- CSRF защита на всех endpoints
- Использование HTTPS в продакшене

## Лицензия

Внутренний проект tg-nanobanana
