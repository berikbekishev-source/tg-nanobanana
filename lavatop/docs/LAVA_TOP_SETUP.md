# Настройка Lava.top для приема платежей

## Шаг 1: Настройка Webhook в Lava.top

### Данные для заполнения формы Webhook:

1. **URL*** (обязательно):
   ```
   https://web-production-96df.up.railway.app/api/miniapp/lava-webhook
   ```

2. **Тип события**:
   - ✅ Результат платежа (оставьте как есть)

3. **Вид аутентификации для Webhook**:
   - Выберите: **"API key вашего сервиса"**

4. **API Key** (в поле после выбора типа аутентификации):
   ```
   lava_secret_key_123456
   ```
   ⚠️ **ВАЖНО:** Сгенерируйте свой уникальный секретный ключ! Не используйте этот пример в продакшене.

5. **Комментарий** (опционально):
   ```
   Webhook для NanoBanana bot
   ```

### Пример заполнения:

```
╔═══════════════════════════════════════════════════════════╗
║ Добавить Webhook                                          ║
╠═══════════════════════════════════════════════════════════╣
║ URL*:                                                     ║
║ https://web-production-96df.up.railway.app/api/miniapp/  ║
║ lava-webhook                                              ║
║                                                           ║
║ Тип события:                                              ║
║ [✓] Результат платежа                                     ║
║                                                           ║
║ Вид аутентификации для Webhook:                           ║
║ ( ) Basic                                                 ║
║ (•) API key вашего сервиса                                ║
║                                                           ║
║ API Key:                                                  ║
║ lava_secret_key_123456                                    ║
║                                                           ║
║ Комментарий:                                              ║
║ Webhook для NanoBanana bot                                ║
║                                                           ║
║             [Отмена]  [Сохранить]                         ║
╚═══════════════════════════════════════════════════════════╝
```

---

## Шаг 2: Добавить переменную окружения на Railway

1. Откройте ваш проект на Railway
2. Выберите сервис **"web"**
3. Перейдите в раздел **"Variables"**
4. Добавьте новую переменную:

```bash
LAVA_WEBHOOK_SECRET=lava_secret_key_123456
```

⚠️ **Используйте тот же ключ**, который указали в форме Lava.top!

---

## Шаг 3: Создать платежные ссылки для всех пакетов

У вас уже есть ссылка для 100 токенов:
```
https://app.lava.top/products/acfa45f0-6fa0-4f3c-b73e-f10b92d6d8fc
```

Создайте аналогичные товары в Lava.top для:

| Токены | Цена | Описание товара |
|--------|------|-----------------|
| 100 | $5 | ✅ Уже создано |
| 200 | $10 | 200 токенов для генерации |
| 500 | $25 | 500 токенов для генерации |
| 1000 | $50 | 1000 токенов для генерации |

После создания товаров, обновите файл:
`miniapp/payment_providers/lava_provider.py`

```python
LAVA_PAYMENT_LINKS = {
    100: "https://app.lava.top/products/acfa45f0-6fa0-4f3c-b73e-f10b92d6d8fc",
    200: "https://app.lava.top/products/ВАШ-ID-ДЛЯ-200",
    500: "https://app.lava.top/products/ВАШ-ID-ДЛЯ-500",
    1000: "https://app.lava.top/products/ВАШ-ID-ДЛЯ-1000",
}
```

---

## Шаг 4: Настроить параметры товара в Lava.top

Для каждого товара в настройках укажите:

### ⚙️ Настройки товара:

1. **Возможность передачи custom параметров**: ✅ Включено
2. **Параметры для передачи**:
   - `order_id` - ID транзакции из нашей БД
   - `email` - email пользователя

Это позволит передавать ID транзакции в URL для отслеживания.

---

## Шаг 5: Тестирование

### Локальное тестирование (опционально):

1. Используйте ngrok для создания публичного URL:
   ```bash
   ngrok http 8000
   ```

2. Временно обновите webhook URL в Lava.top на ngrok URL:
   ```
   https://your-random-id.ngrok.io/api/miniapp/lava-webhook
   ```

3. Сделайте тестовый платеж

### Продакшн тестирование:

1. Задеплойте код на Railway:
   ```bash
   git add .
   git commit -m "Add Lava.top payment integration"
   git push origin main
   ```

2. Дождитесь деплоя

3. Откройте Mini App в Telegram и попробуйте сделать оплату

---

## Как работает процесс оплаты:

```
1. Пользователь выбирает 100 токенов → $5
   ↓
2. Нажимает "Оплатить"
   ↓
3. Открывается ссылка Lava.top:
   https://app.lava.top/products/acfa45...?order_id=123&email=user@mail.com
   ↓
4. Пользователь оплачивает
   ↓
5. Lava.top отправляет webhook на:
   https://web-production-96df.up.railway.app/api/miniapp/lava-webhook
   ↓
6. Наш сервер:
   - Проверяет API ключ
   - Находит транзакцию по order_id
   - Начисляет токены на баланс
   - Обновляет статус транзакции
   ↓
7. Пользователь получает токены
```

---

## Проверка работы webhook

### Просмотр логов на Railway:

```bash
railway logs --service web
```

Вы увидите записи:
```
INFO Lava webhook received: {...}
INFO Payment 123 completed. Credited 5.0 tokens to user 987654321
```

### Проверка в базе данных:

```sql
-- Проверить транзакции
SELECT * FROM botapp_transaction
WHERE payment_method = 'card'
ORDER BY created_at DESC
LIMIT 10;

-- Проверить балансы пользователей
SELECT u.chat_id, u.username, b.balance, b.total_deposited
FROM botapp_tguser u
JOIN botapp_userbalance b ON b.user_id = u.id
ORDER BY b.updated_at DESC;
```

---

## Безопасность

✅ **Что уже реализовано:**
- Проверка API ключа в заголовках webhook
- Атомарные операции с балансом (защита от race conditions)
- Логирование всех платежей
- Валидация данных от Lava.top

⚠️ **Рекомендации:**
1. Используйте сложный случайный ключ для `LAVA_WEBHOOK_SECRET`
2. Не коммитьте секретные ключи в git
3. Регулярно проверяйте логи на подозрительную активность

---

## Устранение неполадок

### Webhook не приходит:

1. Проверьте URL webhook в Lava.top
2. Убедитесь, что Railway сервис запущен:
   ```bash
   railway status --service web
   ```
3. Проверьте логи:
   ```bash
   railway logs --service web --lines 100
   ```

### Ошибка 401 Unauthorized:

- Проверьте, что `LAVA_WEBHOOK_SECRET` на Railway совпадает с API ключом в Lava.top

### Токены не начисляются:

1. Проверьте логи webhook
2. Убедитесь, что пользователь существует в базе (запускал /start в боте)
3. Проверьте формат данных от Lava.top в логах

---

## Следующие шаги

После настройки Lava.top:

1. ✅ Создать уведомления в Telegram после успешной оплаты
2. ✅ Добавить историю платежей в бот
3. ✅ Настроить мониторинг платежей

---

**Статус:** ✅ Готово к использованию
**Дата:** 2025-10-25
**Автор:** Claude Code
