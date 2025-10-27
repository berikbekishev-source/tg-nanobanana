"""
FSM состояния для навигации по боту
"""
from aiogram.fsm.state import State, StatesGroup


class BotStates(StatesGroup):
    """Основные состояния бота"""

    # Главное меню
    main_menu = State()

    # Генерация изображений
    image_select_model = State()       # Выбор модели для изображений
    image_wait_prompt = State()         # Ожидание промта и/или изображений
    image_wait_images = State()         # Ожидание изображений для режима Remix
    image_confirm_generation = State()  # Подтверждение генерации
    image_processing = State()          # Процесс генерации

    # Генерация видео
    video_select_model = State()        # Выбор модели для видео
    video_select_format = State()       # Выбор формата (соотношение сторон)
    video_wait_prompt = State()         # Ожидание промта или изображения
    video_confirm_generation = State()  # Подтверждение генерации
    video_processing = State()          # Процесс генерации видео
    video_extend_prompt = State()       # Ожидание промта для продления видео

    # Баланс и платежи
    balance_view = State()              # Просмотр баланса
    balance_history = State()           # История транзакций
    payment_select_method = State()     # Выбор метода оплаты
    payment_enter_amount = State()      # Ввод суммы
    payment_enter_promocode = State()   # Ввод промокода
    payment_processing = State()        # Обработка платежа
    payment_mini_app = State()          # Mini App для оплаты

    # Настройки
    settings_menu = State()             # Меню настроек
    settings_language = State()         # Выбор языка
    settings_notifications = State()    # Настройка уведомлений

    # Реферальная система
    referral_info = State()             # Информация о реферальной программе
    referral_stats = State()            # Статистика рефералов

    # Помощь и поддержка
    help_menu = State()                 # Меню помощи
    support_ticket = State()            # Создание тикета поддержки


class GenerationStates(StatesGroup):
    """Дополнительные состояния для генерации"""

    # Параметры генерации изображений
    image_set_quantity = State()        # Установка количества изображений
    image_set_style = State()           # Выбор стиля (если доступно)
    image_advanced_settings = State()   # Продвинутые настройки

    # Параметры генерации видео
    video_set_duration = State()        # Установка длительности
    video_set_resolution = State()      # Выбор разрешения
    video_set_fps = State()             # Выбор FPS


class AdminStates(StatesGroup):
    """Состояния для администраторов"""

    admin_menu = State()                # Админ меню
    admin_broadcast = State()           # Рассылка сообщений
    admin_stats = State()               # Статистика бота
    admin_user_management = State()     # Управление пользователями
    admin_model_management = State()    # Управление AI моделями
