# ✅ Что осталось сделать для полной работы системы оплаты

**Статус:** Базовая интеграция с Lava.top готова на 80%

---

## 1. ✅ ВЫПОЛНЕНО

- ✅ Создан Telegram Mini App (HTML, CSS, JS)
- ✅ Разработаны Django API endpoints
- ✅ Интегрирован Lava.top webhook
- ✅ Создан webhook в Lava.top
- ✅ Добавлен API ключ на Railway: `LAVA_WEBHOOK_SECRET=lava_webhook_secret_ABC123xyz789`
- ✅ Обновлены `.env` и `.env.example`
- ✅ Реализована логика начисления токенов
- ✅ Атомарные операции с балансом

---

## 2. ❌ ОСТАЛОСЬ СДЕЛАТЬ (КРИТИЧНО)

### 2.1. Создать товары в Lava.top для остальных пакетов

Сейчас есть только для 100 токенов. Нужно создать:

| Пакет | Цена | Статус |
|-------|------|--------|
| 100 токенов | $5 | ✅ https://app.lava.top/products/acfa45f0-6fa0-4f3c-b73e-f10b92d6d8fc |
| 200 токенов | $10 | ❌ Нужно создать |
| 500 токенов | $25 | ❌ Нужно создать |
| 1000 токенов | $50 | ❌ Нужно создать |

**Инструкция:**
1. Зайдите на https://app.lava.top
2. Создайте 3 новых товара (200, 500, 1000 токенов)
3. Скопируйте ссылки на товары

### 2.2. Обновить файл с платежными ссылками

После создания товаров обновите:
`miniapp/payment_providers/lava_provider.py`

```python
LAVA_PAYMENT_LINKS = {
    100: "https://app.lava.top/products/acfa45f0-6fa0-4f3c-b73e-f10b92d6d8fc",
    200: "https://app.lava.top/products/ВАШ-ID-ДЛЯ-200-ТОКЕНОВ",  # ← Вставьте сюда
    500: "https://app.lava.top/products/ВАШ-ID-ДЛЯ-500-ТОКЕНОВ",  # ← Вставьте сюда
    1000: "https://app.lava.top/products/ВАШ-ID-ДЛЯ-1000-ТОКЕНОВ", # ← Вставьте сюда
}
```

### 2.3. Задеплоить изменения на Railway

```bash
git add .
git commit -m "Add Lava.top payment integration"
git push origin main
```

Railway автоматически задеплоит изменения.

---

## 3. ❌ ЖЕЛАТЕЛЬНО СДЕЛАТЬ

### 3.1. Уведомления в Telegram после оплаты

Когда пользователь успешно оплатил, отправить ему сообщение в Telegram:

**Где:** `miniapp/api.py` в функции `lava_webhook()` после строки 230

**Что добавить:**
```python
# TODO: Отправить уведомление пользователю в Telegram
# Можно использовать Celery задачу

# Пример:
from botapp.tasks import send_payment_notification
send_payment_notification.delay(
    chat_id=trans.user.chat_id,
    credits=credits_amount,
    amount=trans.amount
)
```

**Создать Celery задачу:**
`botapp/tasks.py`

```python
@shared_task
def send_payment_notification(chat_id: int, credits: float, amount: float):
    """Отправить уведомление об успешной оплате"""
    from aiogram import Bot
    from django.conf import settings

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    message = (
        f"✅ Платеж успешно выполнен!\n\n"
        f"💰 Зачислено: {credits} токенов\n"
        f"💵 Сумма: ${amount}\n\n"
        f"Спасибо за покупку! 🎉\n"
        f"Используйте /balance чтобы увидеть баланс"
    )

    import asyncio
    asyncio.run(bot.send_message(chat_id=chat_id, text=message))
```

### 3.2. Кнопка пополнения баланса в боте

Добавить в обработчики бота кнопку для открытия Mini App:

**Где:** `botapp/handlers/balance.py` (или создать новый файл)

```python
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from django.conf import settings

router = Router()

@router.message(F.text == "/pay")
async def cmd_payment(message: Message):
    """Команда для пополнения баланса"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💳 Пополнить баланс",
            web_app=WebAppInfo(url=f"{settings.PUBLIC_BASE_URL}/miniapp/")
        )]
    ])

    await message.answer(
        "💵 Пополнение баланса\n\n"
        "Выберите количество токенов и оплатите удобным способом:",
        reply_markup=keyboard
    )
```

### 3.3. История платежей

Показывать историю платежей пользователя в боте:

```python
@router.message(F.text == "/transactions")
async def cmd_transactions(message: Message):
    """История транзакций"""
    user = await TgUser.objects.aget(chat_id=message.from_user.id)
    transactions = Transaction.objects.filter(
        user=user,
        type='deposit'
    ).order_by('-created_at')[:10]

    text = "📊 Ваши последние пополнения:\n\n"

    async for trans in transactions:
        status = "✅" if trans.is_completed else "⏳"
        text += f"{status} ${trans.amount} - {trans.created_at.strftime('%d.%m.%Y %H:%M')}\n"

    await message.answer(text)
```

### 3.4. Проверка формата данных от Lava.top

Возможно, нужно будет скорректировать `parse_webhook_data()` в `miniapp/payment_providers/lava_provider.py` после первого реального платежа.

**Что сделать:**
1. Сделать тестовый платеж на 100 токенов
2. Посмотреть логи Railway: `railway logs --service web`
3. Проверить какие данные приходят от Lava.top
4. При необходимости обновить парсинг

---

## 4. 📋 ОПЦИОНАЛЬНО (УЛУЧШЕНИЯ)

### 4.1. Промокоды
- Поддержка промокодов при оплате
- Скидки и бонусы

### 4.2. Реферальная система
- Начисление бонусов за рефералов
- Реферальные ссылки

### 4.3. Админ панель
- Просмотр всех платежей
- Статистика по оплатам
- Ручное начисление/списание токенов

### 4.4. Мониторинг
- Sentry для отслеживания ошибок
- Метрики платежей в Grafana
- Алерты при проблемах с платежами

---

## 5. 🧪 ТЕСТИРОВАНИЕ

### Чек-лист перед продакшн-запуском:

- [ ] Создали все 4 товара в Lava.top
- [ ] Обновили `lava_provider.py` со всеми ссылками
- [ ] Задеплоили на Railway
- [ ] Проверили, что webhook получает данные
- [ ] Сделали тестовый платеж на 100 токенов
- [ ] Проверили, что токены начислились
- [ ] Проверили логи - нет ошибок
- [ ] Добавили кнопку в бота
- [ ] Протестировали все пакеты (100, 200, 500, 1000)

### Как протестировать:

1. Откройте бота
2. Используйте команду `/pay` (после добавления обработчика)
3. Нажмите кнопку "💳 Пополнить баланс"
4. Выберите 100 токенов
5. Введите email
6. Нажмите "Оплатить"
7. Оплатите на Lava.top
8. Проверьте, что токены начислились: `/balance`

---

## 6. 🚨 TROUBLESHOOTING

### Проблема: Webhook не приходит

**Решение:**
```bash
# Проверьте логи
railway logs --service web --lines 100

# Убедитесь, что сервис запущен
railway status --service web

# Проверьте URL webhook в Lava.top
```

### Проблема: Ошибка 401 Unauthorized

**Решение:**
- Проверьте, что API ключ на Railway совпадает с ключом в Lava.top
- `railway variables --service web | grep LAVA`

### Проблема: Токены не начисляются

**Решение:**
1. Проверьте логи webhook: `railway logs --service web | grep "Lava webhook"`
2. Убедитесь, что пользователь существует в БД (запускал `/start`)
3. Проверьте баланс в БД напрямую

---

## 7. 📞 ПОЛЕЗНЫЕ КОМАНДЫ

```bash
# Посмотреть логи webhook
railway logs --service web | grep "Lava"

# Проверить переменные окружения
railway variables --service web

# Посмотреть последние транзакции в БД
railway run --service web python manage.py shell
>>> from botapp.models import Transaction
>>> Transaction.objects.filter(type='deposit').order_by('-created_at')[:5]

# Задеплоить изменения
git add .
git commit -m "Update payment links"
git push origin main
```

---

**Приоритет:**
1. ⭐⭐⭐ Критично: Пункт 2 (создать товары, задеплоить)
2. ⭐⭐ Важно: Пункт 3.1-3.2 (уведомления, кнопка в боте)
3. ⭐ Желательно: Пункт 3.3-3.4 (история, проверка данных)

---

**Дата:** 2025-10-25
**Статус:** 80% готово, осталось создать товары и задеплоить
