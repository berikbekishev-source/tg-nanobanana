# 📋 План реализации Telegram бота tg-nanobanana

## 📌 Описание проекта
Телеграм бот для генерации изображений и видео через AI модели с системой монетизации, рассчитанный на 100,000 MAU.

## 🎯 Целевой функционал

### Основные функции:
1. **Навигационное меню** с кнопками:
   - Создать видео
   - Создать изображение
   - Мой баланс (цены)
   - Пополнить баланс

2. **Генерация изображений:**
   - Выбор модели (NanoBanana и другие)
   - Описание модели и стоимости
   - Поддержка текстовых запросов и Remix режима (до 4 изображений)

3. **Генерация видео:**
   - Выбор модели (Veo3.1 Fast и другие)
   - Генерация из текста или изображения
   - Видео 720p до 8 секунд

4. **Система баланса:**
   - Отображение текущего баланса
   - История транзакций
   - Пополнение через Mini App

5. **Telegram Mini App:**
   - Интерфейс пополнения баланса
   - Поддержка различных платежных методов

## 🔍 Результаты аудита текущего проекта

### ✅ Сильные стороны:
- Рабочая базовая архитектура для генерации изображений через Gemini API
- Асинхронная обработка через Celery с Redis
- Webhook интеграция с Telegram
- Хранилище файлов в Supabase Storage
- Готовая инфраструктура для Railway деплоя
- Чистое разделение логики (handlers, services, tasks)

### ❌ Требует доработки:
1. Отсутствие навигационного меню
2. Нет системы баланса
3. Нет поддержки видео
4. Примитивная FSM структура
5. Ограниченные модели БД
6. Нет Mini App для оплаты
7. Слабое логирование и мониторинг
8. Отсутствие тестов
9. Нет системы подключения новых моделей
10. Недостаточное масштабирование для 100k MAU

## 📊 Детальный план реализации

### Этап 1: Расширение базы данных (2-3 дня)

#### Новые модели Django:

**AIModel** - каталог доступных моделей
```python
class AIModel(models.Model):
    slug = models.SlugField(unique=True)  # 'nano-banana', 'veo3-fast'
    name = models.CharField(max_length=100)  # Отображаемое имя
    type = models.CharField(choices=['image', 'video'])
    description = models.TextField()  # Описание для пользователя
    price = models.DecimalField()  # Цена в токенах
    provider = models.CharField()  # 'gemini', 'vertex', 'veo'
    config = models.JSONField()  # Настройки модели
    is_active = models.BooleanField(default=True)
    order = models.IntegerField()  # Порядок отображения
```

**UserBalance** - расширение профиля пользователя
```python
class UserBalance(models.Model):
    user = models.OneToOneField(TgUser, on_delete=models.CASCADE)
    balance = models.DecimalField(default=0, decimal_places=2)
    total_spent = models.DecimalField(default=0)
    referral_code = models.CharField(unique=True, null=True)
    referred_by = models.ForeignKey('self', null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Transaction** - история транзакций
```python
class Transaction(models.Model):
    TYPES = [('deposit', 'Пополнение'), ('generation', 'Генерация'), ('bonus', 'Бонус')]
    user = models.ForeignKey(TgUser, on_delete=models.CASCADE)
    type = models.CharField(choices=TYPES)
    amount = models.DecimalField()
    balance_after = models.DecimalField()
    description = models.TextField()
    payment_method = models.CharField(null=True)  # 'yoomoney', 'card', 'crypto'
    payment_id = models.CharField(null=True)  # ID платежа
    generation_request = models.ForeignKey(GenRequest, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Обновление GenRequest:**
```python
# Добавить новые поля:
input_images = models.JSONField(null=True)  # Для режима Remix
generation_type = models.CharField(choices=['text2image', 'image2image', 'text2video', 'image2video'])
cost = models.DecimalField()  # Фактическая стоимость
duration = models.IntegerField(null=True)  # Длительность видео в секундах
```

### Этап 2: FSM и навигационное меню (3-4 дня)

#### Структура FSM состояний:
```python
class BotStates(StatesGroup):
    # Главное меню
    main_menu = State()

    # Генерация изображений
    image_select_model = State()
    image_wait_prompt = State()
    image_processing = State()

    # Генерация видео
    video_select_model = State()
    video_wait_prompt = State()
    video_processing = State()

    # Баланс
    balance_view = State()
    payment_method = State()
    payment_processing = State()
```

#### Клавиатуры меню:
- Главное меню с основными разделами
- Кнопка "Главное меню" доступна везде
- Динамические кнопки выбора моделей
- Inline кнопки для быстрых действий

### Этап 3: Система баланса и тарификации (2-3 дня)

#### Компоненты:
1. **Сервис баланса** (`botapp/business/balance.py`)
   - Атомарные операции пополнения/списания
   - Поддержка отложенных транзакций (pending → complete)
   - Возвраты и история транзакций

2. **Декоратор проверки баланса** (`botapp/business/decorators.py`)
   - Асинхронная проверка и мгновенное списание перед генерацией

3. **Бонусная система** (`botapp/business/bonuses.py`)
   - Приветственный бонус и бонус за первое пополнение
   - Реферальные выплаты
   - Ежедневные награды (серия до 7 дней)

4. **Тесты и миграции**
   - Юнит-тесты для `BalanceService` (`botapp/tests.py`)
   - Миграции `0004` (Promocode.used_by) и `0005` (daily_reward_* в UserSettings)

### Этап 4: Интеграция генерации видео (3-4 дня)

#### Компоненты:
1. **Провайдеры видео** (`botapp/providers/video/`)
   - Базовый интерфейс и регистрация новых моделей
   - Реализация Veo 3.1 Fast через Vertex AI REST API (`vertex.py`)
   - Получение OAuth токена из сервис-аккаунта и polling операций
2. **Обновленные Celery задачи** (`botapp/tasks.py`)
   - Скачивание входных изображений из Telegram
   - Отправка результата в Supabase, формирование финального отчёта
   - Обработка ошибок провайдера и повторные попытки
3. **Хранение видео** в Supabase Storage (`supabase_upload_video`)
   - Отдельная папка `videos/` и публичные ссылки
   - Новая переменная окружения `SUPABASE_VIDEO_BUCKET`
4. **Расширенная модель данных**
   - `GenRequest`: поля `aspect_ratio`, `provider_job_id`, `provider_metadata`, `source_media`
   - Миграции `0006`, `0007` для хранения метаданных и обновления Veo настроек
5. **FSM и UX видео-ветки**
   - Сообщения по ТЗ (выбор модели → инструкции → старт)
   - Поддержка режимов txt2video и img2video
   - TODO: прогресс-бар и обновления статуса по операции
6. **Настройки Vertex AI**
   - Используются `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`

### Этап 5: Telegram Mini App (4-5 дней)

#### Структура:
```
miniapp/
├── static/
│   ├── index.html       # Основная страница
│   ├── payment.js       # Логика оплаты
│   └── styles.css       # Стили интерфейса
├── api.py              # API endpoints
└── payment_providers/  # Интеграции платежей
```

#### Платежные методы:
1. ЮMoney (основной)
2. Криптовалюты (TON, USDT)
3. Банковские карты

### Этап 6: Система провайдеров моделей (2-3 дня)

#### Архитектура:
```python
# botapp/providers/base.py
class BaseProvider(ABC):
    @abstractmethod
    async def generate(self, prompt, **kwargs):
        pass

# Реализации для каждого провайдера
# - GeminiProvider
# - VertexProvider
# - VeoProvider
```

#### Управление моделями:
- Динамическая регистрация провайдеров
- Конфигурация через админку
- A/B тестирование моделей

### Этап 7: Масштабирование для 100k MAU (3-4 дня)

#### Оптимизации базы данных:
- Индексы на критичные поля
- Партиционирование таблиц
- Read replicas
- Connection pooling

#### Redis оптимизации:
- Redis Cluster для FSM
- Кэширование моделей и тарифов
- Rate limiting по пользователям

#### Celery масштабирование:
- Приоритетные очереди
- Автомасштабирование воркеров
- Оптимизация задач

#### Инфраструктура Railway:
```yaml
web:
  replicas: 3-10 (auto)
  cpu: 1-2 vCPU
  memory: 2-4 GB

worker:
  replicas: 5-20 (auto)
  cpu: 2 vCPU
  memory: 4 GB

redis:
  type: Redis Cluster Pro
```

### Этап 8: Тестирование и документация (2-3 дня)

#### Покрытие тестами:
- Unit тесты handlers
- Интеграционные тесты API
- Тесты провайдеров
- Тесты платежей
- Load testing

#### Документация:
- API документация (OpenAPI)
- Руководство администратора
- Deployment guide
- Troubleshooting guide

## 🚀 График выполнения

### Неделя 1 (Критические задачи):
- ✅ День 1-2: Миграция БД и новые модели
- ✅ День 3-4: FSM структура и меню
- ✅ День 5-6: Система баланса базовая

### Неделя 2 (Основной функционал):
- ✅ День 7-9: Интеграция видео
- ✅ День 10-12: Mini App и платежи
- ✅ День 13-14: Тестирование интеграций

### Неделя 3 (Масштабирование):
- ✅ День 15-16: Система провайдеров
- ✅ День 17-19: Оптимизация и масштабирование
- ✅ День 20-21: Финальное тестирование и документация

## 📈 Метрики успеха

### Производительность:
- Время отклика API < 200ms
- Генерация изображения < 10 сек
- Генерация видео < 30 сек
- Обработка платежа < 5 сек

### Масштабируемость:
- 100,000 MAU
- 10,000 одновременных пользователей
- 1,000,000 генераций в месяц
- 50,000 транзакций в день

### Надежность:
- Uptime > 99.9%
- Автовосстановление при сбоях
- Резервное копирование каждые 6 часов
- RPO < 1 час, RTO < 15 минут

### Бизнес-метрики:
- Конверсия в первую генерацию > 60%
- Конверсия в платеж > 20%
- Retention Day 7 > 40%
- ARPU > $5

## 🛠️ Технические требования

### Безопасность:
- Все платежи через HTTPS
- Токены в переменных окружения
- Rate limiting на все endpoints
- SQL injection защита
- XSS защита в Mini App

### Мониторинг:
- Sentry для ошибок
- Prometheus + Grafana для метрик
- Алерты в Telegram для критических событий
- Логирование всех транзакций

### Резервное копирование:
- Автоматический backup БД каждые 6 часов
- Backup конфигураций ежедневно
- Хранение backup 30 дней
- Тестирование восстановления еженедельно

## ⚠️ Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|------------|---------|-----------|
| Перегрузка API моделей | Высокая | Критично | Rate limiting, очереди с приоритетами, fallback модели |
| Проблемы с платежами | Средняя | Высоко | Множественные провайдеры, ручная проверка, retry логика |
| DDoS атаки | Средняя | Критично | Cloudflare, rate limiting, captcha при подозрительной активности |
| Утечка данных | Низкая | Критично | Шифрование данных, аудит доступа, RBAC, регулярные security audits |
| Превышение бюджета API | Средняя | Высоко | Квоты пользователей, мониторинг расходов, алерты по бюджету |
| Недоступность Supabase | Низкая | Высоко | Резервное S3 хранилище, локальный кэш |
| Баги после релиза | Средняя | Средне | Feature flags, canary deployment, rollback план |

## ✅ Чек-лист готовности к продакшену

### База данных и модели:
- [ ] Все модели созданы и мигрированы
- [ ] Индексы оптимизированы
- [ ] Backup настроен и протестирован
- [ ] Read replicas настроены

### Функционал бота:
- [ ] FSM полностью реализован
- [ ] Все меню работают корректно
- [ ] Генерация изображений стабильна
- [ ] Генерация видео интегрирована
- [ ] Система баланса протестирована

### Платежи и Mini App:
- [ ] Mini App развернут
- [ ] Все платежные методы работают
- [ ] SSL сертификат установлен
- [ ] Webhook для платежей настроен

### Масштабирование:
- [ ] Auto-scaling настроен
- [ ] Load balancing работает
- [ ] CDN подключен
- [ ] Кэширование оптимизировано

### Мониторинг и безопасность:
- [ ] Sentry интегрирован
- [ ] Метрики собираются
- [ ] Алерты настроены
- [ ] Security audit пройден

### Документация и тесты:
- [ ] API документирован
- [ ] Админ guide написан
- [ ] Unit тесты > 80% coverage
- [ ] Load testing пройден

### Deployment:
- [ ] CI/CD pipeline настроен
- [ ] Rollback процедура готова
- [ ] Environment variables secure
- [ ] Health checks работают

## 📝 Команда и ресурсы

### Необходимые специалисты:
- Backend разработчик (Python/Django)
- Frontend разработчик (для Mini App)
- DevOps инженер
- QA инженер
- UI/UX дизайнер (опционально)

### Инфраструктурные ресурсы:
- Railway Pro план
- Supabase Pro план
- Redis Cloud
- Cloudflare (CDN + DDoS защита)
- Мониторинг сервисы

### Бюджет на API:
- Google Cloud credits для Gemini/Veo
- Резерв на 1M генераций/месяц
- Платежные комиссии ~2.5%

## 🎯 Следующие шаги

1. **Немедленно:**
   - Создать новую ветку для разработки
   - Настроить dev окружение
   - Начать с моделей БД

2. **Первая неделя:**
   - Реализовать критический функционал
   - Провести первое тестирование
   - Получить обратную связь

3. **После MVP:**
   - A/B тестирование функций
   - Оптимизация конверсии
   - Добавление новых моделей AI

## 📞 Контакты и поддержка

- **Документация проекта:** `/docs`
- **Issue tracker:** GitHub Issues
- **Мониторинг:** Grafana Dashboard
- **Логи:** Railway Logs / Sentry

---

*Последнее обновление: 2025-10-24*
*Версия плана: 1.0.0*
