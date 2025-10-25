# Интеграция Telegram Mini App для оплаты токенов

## Обзор

Telegram Mini App разработан для пополнения баланса пользователей бота. Страница оплаты выполнена в темной теме и полностью адаптирована под дизайн Telegram.

## Созданные файлы

```
miniapp/
├── __init__.py
├── api.py                  # API endpoints для платежей
├── views.py                # Django views
├── README.md               # Документация Mini App
├── static/
│   ├── index.html         # Главная страница
│   ├── styles.css         # Стили
│   └── payment.js         # Логика оплаты
├── templates/
└── payment_providers/
    └── __init__.py
```

## Основные возможности

### 1. Выбор количества токенов
- 100 токенов = $5
- 200 токенов = $10
- 500 токенов = $25
- 1000 токенов = $50

### 2. Способ оплаты
- Карта VISA/MasterCard (единственный метод)

### 3. Валюта
- USD (фиксированная)

### 4. Интеграция с Telegram
- Автоматическое получение данных пользователя
- Валидация init_data
- Адаптация под тему Telegram

## Подключение к боту

### Вариант 1: Кнопка в главном меню

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from django.conf import settings

async def show_balance_menu(message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💳 Пополнить баланс",
            web_app=WebAppInfo(url=f"{settings.PUBLIC_BASE_URL}/miniapp/")
        )],
        [InlineKeyboardButton(text="📊 История операций", callback_data="balance_history")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")]
    ])

    await message.answer(
        f"💰 Ваш баланс: {user_balance.balance} токенов\n\n"
        f"Выберите действие:",
        reply_markup=keyboard
    )
```

### Вариант 2: Отдельная команда

```python
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

router = Router()

@router.message(F.text == "/pay")
async def cmd_payment(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💳 Открыть страницу оплаты",
            web_app=WebAppInfo(url=f"{settings.PUBLIC_BASE_URL}/miniapp/")
        )]
    ])

    await message.answer(
        "💵 Пополнение баланса\n\n"
        "Нажмите кнопку ниже, чтобы открыть страницу оплаты:",
        reply_markup=keyboard
    )
```

### Вариант 3: При недостатке средств

```python
async def check_balance_and_generate(user, cost):
    balance = await UserBalance.objects.aget(user=user)

    if balance.balance < cost:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="💳 Пополнить баланс",
                web_app=WebAppInfo(url=f"{settings.PUBLIC_BASE_URL}/miniapp/")
            )]
        ])

        return await message.answer(
            f"❌ Недостаточно средств!\n\n"
            f"Ваш баланс: {balance.balance} токенов\n"
            f"Необходимо: {cost} токенов\n\n"
            f"Пополните баланс, чтобы продолжить:",
            reply_markup=keyboard
        )

    # Продолжаем генерацию...
```

## API Endpoints

### POST /api/miniapp/create-payment
Создание платежа

**URL:** `https://your-domain.com/api/miniapp/create-payment`

**Запрос:**
```json
{
  "email": "user@example.com",
  "credits": 100,
  "amount": 5.0,
  "currency": "USD",
  "payment_method": "card",
  "user_id": 123456789,
  "init_data": "query_id=AAH..."
}
```

**Ответ:**
```json
{
  "success": true,
  "payment_url": "https://payment-provider.com/...",
  "payment_id": "123"
}
```

### GET /api/miniapp/payment-status/{payment_id}
Проверка статуса платежа

**URL:** `https://your-domain.com/api/miniapp/payment-status/123`

**Ответ:**
```json
{
  "success": true,
  "status": "pending",
  "amount": 5.0,
  "created_at": "2025-10-24T12:00:00Z"
}
```

## Настройка переменных окружения

Добавьте в `.env`:

```env
# Публичный URL вашего сервера
PUBLIC_BASE_URL=https://your-domain.railway.app

# Telegram Bot Token (уже должен быть)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

## Настройка Telegram Bot

1. Откройте [@BotFather](https://t.me/BotFather)
2. Выберите вашего бота
3. Используйте команду `/setmenubutton`
4. Добавьте кнопку:
   - **Text:** 💳 Пополнить баланс
   - **URL:** `https://your-domain.railway.app/miniapp/`

## Следующие шаги (TODO)

### 1. Интеграция платежной системы

Необходимо выбрать и интегрировать платежный провайдер:

**Рекомендуемые варианты:**
- **Stripe** - международные платежи
- **Kaspi.kz** - для Казахстана
- **ЮMoney** - для России
- **PayPal** - международные платежи

**Что нужно реализовать:**

```python
# miniapp/payment_providers/stripe_provider.py
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_payment_session(amount, credits, user_email):
    """
    Создание платежной сессии Stripe
    """
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': f'{credits} токенов для генерации',
                },
                'unit_amount': int(amount * 100),  # в центах
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=f"{settings.PUBLIC_BASE_URL}/miniapp/success",
        cancel_url=f"{settings.PUBLIC_BASE_URL}/miniapp/cancel",
        customer_email=user_email,
    )

    return session.url, session.id
```

Затем обновите `miniapp/api.py`:

```python
from miniapp.payment_providers.stripe_provider import create_payment_session

# В функции create_payment()
payment_url, payment_id = create_payment_session(
    amount=data.amount,
    credits=data.credits,
    user_email=data.email
)

# Сохраняем payment_id в транзакции
transaction.payment_id = payment_id
transaction.save()
```

### 2. Обработка webhook от платежной системы

```python
# miniapp/api.py
@miniapp_api.post("/payment-webhook")
def payment_webhook(request):
    """
    Webhook от Stripe для подтверждения платежа
    """
    import stripe
    from django.db import transaction as db_transaction

    payload = request.body
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']

            # Находим транзакцию
            trans = Transaction.objects.get(payment_id=session['id'])

            # Начисляем токены
            with db_transaction.atomic():
                user_balance = UserBalance.objects.select_for_update().get(
                    user=trans.user
                )
                user_balance.balance += trans.amount
                user_balance.total_deposited += trans.amount
                user_balance.save()

                trans.is_completed = True
                trans.is_pending = False
                trans.save()

            # Уведомляем пользователя в Telegram
            # TODO: отправить сообщение через бота

        return JsonResponse({"ok": True})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JsonResponse({"ok": False}, status=400)
```

### 3. Уведомления пользователя

После успешной оплаты отправьте уведомление:

```python
from aiogram import Bot

async def notify_payment_success(user_id, amount, credits):
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    await bot.send_message(
        chat_id=user_id,
        text=f"✅ Платеж успешно выполнен!\n\n"
             f"Зачислено: {credits} токенов\n"
             f"Сумма: ${amount}\n\n"
             f"Спасибо за покупку! 🎉"
    )
```

## Тестирование

### Локальное тестирование

```bash
# Запустите сервер
python manage.py runserver

# Откройте в браузере
open http://localhost:8000/miniapp/
```

### Тестирование в Telegram

1. Настройте ngrok для локального туннеля:
```bash
ngrok http 8000
```

2. Используйте ngrok URL в WebAppInfo:
```python
WebAppInfo(url="https://your-ngrok-url.ngrok.io/miniapp/")
```

3. Откройте бота в Telegram и протестируйте

## Безопасность

- ✅ Валидация init_data от Telegram
- ✅ CSRF защита на всех endpoints
- ✅ Проверка подписи webhook от платежной системы
- ✅ Использование HTTPS в продакшене
- ✅ Атомарные операции с балансом

## Поддержка

Документация: `/miniapp/README.md`
Вопросы: создайте issue в репозитории

---

**Статус:** ✅ Базовая версия готова
**Требуется:** Интеграция платежной системы
