"""
Обработчики генерации изображений
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from asgiref.sync import sync_to_async

from botapp.states import BotStates
from botapp.keyboards import (
    get_image_models_keyboard,
    get_model_info_message,
    get_cancel_keyboard,
    get_main_menu_inline_keyboard,
    get_image_mode_keyboard,
)
from botapp.models import TgUser, AIModel, BotErrorEvent
from botapp.business.generation import GenerationService
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.business.pricing import get_base_price_tokens
from botapp.tasks import generate_image_task
from botapp.error_tracker import ErrorTracker

router = Router()
logger = logging.getLogger(__name__)


@router.message(StateFilter("*"), F.text == "🎨 Создать изображение")
async def create_image_start(message: Message, state: FSMContext):
    """
    Шаг 1: Выбор модели генерации изображений
    """
    # Сбрасываем состояние, если оно было
    await state.clear()

    # Получаем активные модели для изображений
    models = await sync_to_async(list)(
        AIModel.objects.filter(type='image', is_active=True).order_by('order')
    )

    if not models:
        await message.answer(
            "😔 К сожалению, сейчас нет доступных моделей для генерации изображений.\n"
            "Попробуйте позже.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    # Отправляем список моделей с inline кнопкой меню
    await message.answer(
        "🎨 **Выберите модель для генерации изображений:**",
        reply_markup=get_image_models_keyboard(models),
        parse_mode="Markdown"
    )

    # Устанавливаем состояние выбора модели
    await state.set_state(BotStates.image_select_model)


@router.callback_query(StateFilter("*"), F.data.startswith("img_model:"))
async def select_image_model(callback: CallbackQuery, state: FSMContext):
    """
    Шаг 2: После выбора модели показываем информацию и ждем промт
    """
    await callback.answer()

    # Сбрасываем состояние перед выбором новой модели
    await state.clear()

    # Получаем slug модели из callback data
    model_slug = callback.data.split(":")[1]

    # Получаем модель из БД
    try:
        model = await sync_to_async(AIModel.objects.get)(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        await callback.message.answer(
            "❌ Модель не найдена или недоступна.",
            reply_markup=get_main_menu_inline_keyboard()
        )
        return

    # Сохраняем выбранную модель в состояние
    await state.update_data(selected_model=model_slug, model_id=model.id)

    # Проверяем баланс пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=callback.from_user.id)
    balance = await sync_to_async(BalanceService.get_balance)(user)
    model_cost = await sync_to_async(get_base_price_tokens)(model)

    if balance < model_cost:
        await callback.message.answer(
            f"❌ **Недостаточно токенов**\n\n"
            f"Ваш баланс: ⚡ {balance:.2f} токенов\n"
            f"Стоимость генерации: ⚡ {model_cost:.2f} токенов\n\n"
            f"Необходимо пополнить баланс на ⚡ {model_cost - balance:.2f} токенов",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()
        return

    # Сохраняем данные для генерации
    await state.update_data(
        model_slug=model_slug,
        model_id=model.id,
        model_name=model.display_name,
        model_provider=model.provider,
        model_price=float(model_cost),
        max_images=model.max_input_images,
        supports_images=model.supports_image_input,
        image_mode=None,
        remix_images=[],
        edit_base_id=None,
    )

    info_message = (
        get_model_info_message(model, base_price=model_cost)
        + "\n\nРежимы:\n"
        "• Создать из текста — промт без изображений\n"
        "• Отредактировать — одно изображение + промт\n"
        "• Ремикс — 2-4 изображения + промт"
    )

    await state.set_state(BotStates.image_select_mode)
    await callback.message.answer(
        info_message,
        reply_markup=get_image_mode_keyboard(),
    )


async def _start_generation(message: Message, state: FSMContext, prompt: str):
    """
    Internal helper to start generation process.
    Used by both text prompt handler and auto-start from caption.
    """
    data = await state.get_data()
    mode = data.get("image_mode") or "text"
    remix_images = data.get("remix_images") or []
    edit_base_id = data.get("edit_base_id")

    # Проверяем длину промта
    try:
        model = await sync_to_async(AIModel.objects.get)(id=data['model_id'])
    except (AIModel.DoesNotExist, KeyError):
        await message.answer("Ошибка: модель не найдена. Начните заново.")
        await state.clear()
        return

    if len(prompt) > model.max_prompt_length:
        await message.answer(
            f"❌ Промт слишком длинный!\n"
            f"Максимальная длина: {model.max_prompt_length} символов\n"
            f"Ваш промт: {len(prompt)} символов",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Получаем пользователя
    user = await sync_to_async(TgUser.objects.get)(chat_id=message.from_user.id)

    # Создаем запрос на генерацию через сервис
    generation_type = 'text2image'
    input_entries: List[Dict[str, Any]] = []
    if mode == "edit":
        if not edit_base_id:
            await message.answer(
                "Отправьте изображение для редактирования, затем текстовый промт.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        generation_type = 'image2image'
        input_entries = [
            {"telegram_file_id": edit_base_id},
        ]
    elif mode == "remix":
        min_required = 2
        max_allowed = max(min_required, min(data.get("max_images", 4), 4))
        if len(remix_images) < min_required:
            await message.answer(
                f"Для режима «Ремикс» нужно минимум {min_required} изображений. Загрузите ещё и повторите попытку.",
                reply_markup=get_cancel_keyboard(),
            )
            return
        generation_type = 'image2image'
        input_entries = [
            {"telegram_file_id": file_id, "type": "subject"}
            for file_id in remix_images[:max_allowed]
        ]
    else:
        input_entries = []

    try:
        gen_request = await sync_to_async(GenerationService.create_generation_request)(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,  # По умолчанию 1 изображение
            generation_type=generation_type,
            input_images=input_entries,
            generation_params={"image_mode": mode},
        )

        # Отправляем информационное сообщение с деталями
        await message.answer(
            f"🎨 **Генерация началась!**\n\n"
            f"Модель: {data['model_name']}\n"
            f"Промт: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n\n"
            f"⏳ Обычно это занимает 10-30 секунд...\n"
            f"Я отправлю вам результат, как только он будет готов!",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline_keyboard()
        )

        # Запускаем задачу генерации
        generate_image_task.delay(gen_request.id)

        # Очищаем состояние
        await state.clear()

    except InsufficientBalanceError as e:
        await message.answer(
            f"❌ {str(e)}",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await state.clear()

    except Exception as e:
        await message.answer(
            f"❌ Произошла ошибка: {str(e)}",
            reply_markup=get_main_menu_inline_keyboard()
        )
        await ErrorTracker.alog(
            origin=BotErrorEvent.Origin.TELEGRAM,
            severity=BotErrorEvent.Severity.WARNING,
            handler="image_generation._start_generation",
            chat_id=message.chat.id,
            payload={
                "mode": mode,
                "model_id": data.get("model_id"),
                "prompt_length": len(prompt) if prompt else 0,
                "has_remix_images": bool(remix_images),
                "has_edit_base": bool(edit_base_id),
            },
            exc=e,
        )
        await state.clear()


@router.message(BotStates.image_wait_prompt, F.text)
async def receive_image_prompt(message: Message, state: FSMContext):
    """
    Получаем текстовый промт для генерации
    """
    await _start_generation(message, state, message.text)


@router.message(BotStates.image_wait_prompt, F.photo)
async def receive_image_for_prompt(message: Message, state: FSMContext):
    """
    Получаем изображения или маску в зависимости от выбранного режима.
    Поддерживает отправку альбомов (media_group) и авто-старт при наличии подписи (caption).
    """
    data = await state.get_data()
    mode = data.get("image_mode") or "text"
    pending_caption = data.get("pending_caption")

    if not data.get('supports_images'):
        await message.answer(
            "❌ Эта модель не поддерживает входные изображения.\n"
            "Отправьте текстовый промт или выберите другую модель.",
            reply_markup=get_cancel_keyboard()
        )
        return

    if mode == "text":
        await message.answer(
            "Вы выбрали режим «Создать из текста». Отправьте промт без изображений или выберите другой режим.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    photo = message.photo[-1]
    max_images = max(1, data.get('max_images', 4))

    if mode == "edit":
        await state.update_data(edit_base_id=photo.file_id)
        # Если есть подпись, используем её как промт сразу
        if message.caption:
            await _start_generation(message, state, message.caption)
        elif pending_caption:
            # Если вдруг был сохранен промт ранее (маловероятно для edit, но для порядка)
            await _start_generation(message, state, pending_caption)
        else:
            await message.answer(
                "🖼️ Изображение получено. Теперь отправьте текстовый промт.",
                reply_markup=get_cancel_keyboard(),
            )
        return

    # Режим remix
    remix_images = data.get('remix_images', [])
    chat_id = message.chat.id

    # Если есть подпись в текущем сообщении, запоминаем её в локальную переменную
    # (но сохранять в стейт будем только в блоке обработки, чтобы избежать гонки)
    current_caption = message.caption

    # Универсальная буферизация для режима Remix
    # Используем chat_id как ключ группировки, чтобы ловить и альбомы, и быстрые одиночные отправки
    redis = state.storage.redis
    key_images = f"remix_buffer_imgs:{chat_id}"
    key_caption = f"remix_buffer_cap:{chat_id}"

    # Сохраняем file_id в Redis-список
    await redis.rpush(key_images, photo.file_id)
    await redis.expire(key_images, 60)

    # Если пришла подпись - сохраняем её в Redis (перезаписываем, считаем актуальной последнюю/любую)
    if current_caption:
        await redis.set(key_caption, current_caption, ex=60)

    # Небольшая задержка, чтобы собрать пачку сообщений
    # Для альбомов (media_group) ставим задержку больше, чтобы точно собрать все фото
    delay = 2.0 if message.media_group_id else 0.5
    await asyncio.sleep(delay)

    # Используем Lua-скрипт для атомарного получения и удаления списка
    lua_script = """
    local list = redis.call('LRANGE', KEYS[1], 0, -1)
    if #list > 0 then
        redis.call('DEL', KEYS[1])
    end
    return list
    """
    
    try:
        stored_images = await redis.eval(lua_script, 1, key_images)
    except Exception as e:
        logger.error(f"Redis eval error: {e}")
        stored_images = []

    if not stored_images:
        # Значит другой обработчик (воркер) уже забрал данные и обрабатывает их
        return
    
    # Этот воркер - "победитель", он обрабатывает всю пачку
    
    # 1. Забираем caption из Redis (если был)
    stored_caption = await redis.get(key_caption)
    if stored_caption:
        stored_caption = stored_caption.decode('utf-8')
        await redis.delete(key_caption)
        # Обновляем pending_caption, если нашли новый
        pending_caption = stored_caption
    
    # 2. Декодируем image ids
    new_images = [img_id.decode('utf-8') if isinstance(img_id, bytes) else img_id for img_id in stored_images]
    
    # 3. Получаем АКТУАЛЬНЫЙ стейт заново, так как за время sleep он мог измениться (маловероятно при такой схеме, но надежнее)
    # Но так как мы единственные кто пишет в remix_images через этот буфер, можно брать из data, 
    # но лучше перестраховаться, если вдруг были какие-то другие операции.
    # data = await state.get_data() -> уже есть.
    # remix_images = data.get('remix_images', []) -> уже есть.
    # Просто добавляем.
    
    remix_images.extend(new_images)
    remix_images = list(dict.fromkeys(remix_images)) # Уник
    
    # 4. Сохраняем обновленный список и pending_caption в стейт
    await state.update_data(remix_images=remix_images, pending_caption=pending_caption)
    
    # 5. Проверяем условия авто-старта
    # Для ремикса всегда нужно минимум 2 изображения
    min_needed = 2
    
    if len(remix_images) >= min_needed and pending_caption:
        # Есть и картинки и промт - запускаем
        await _start_generation(message, state, pending_caption)
        return
        
    # 6. Если автостарт не сработал - отправляем статус (ОДИН РАЗ на пачку)
    msg_text = ""
    if len(remix_images) >= max_images:
            msg_text = f"✅ Загружено {len(remix_images)} изображений (максимум). Отправьте текстовый промт."
    elif len(remix_images) < min_needed:
            msg_text = f"✅ Загружено {len(remix_images)} изображений. Нужно минимум {min_needed}. Загрузите ещё."
    else:
            msg_text = f"✅ Загружено {len(remix_images)} изображений. Можно добавить ещё или отправить промт."
            
    await message.answer(msg_text, reply_markup=get_cancel_keyboard())
    return


@router.callback_query(StateFilter("*"), F.data == "main_menu")
async def handle_main_menu_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик inline кнопки "Главное меню"
    """
    await callback.answer()

    # Очищаем состояние
    await state.clear()
    await state.set_state(BotStates.main_menu)

    # Импортируем функцию главного меню из menu.py
    from django.conf import settings
    from botapp.keyboards import get_main_menu_keyboard

    PAYMENT_URL = getattr(settings, 'PAYMENT_MINI_APP_URL', 'https://example.com/payment')

    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_menu_keyboard(PAYMENT_URL)
    )


@router.callback_query(StateFilter("*"), F.data.startswith("image_mode:"))
async def select_image_mode(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора режима генерации изображений."""
    await callback.answer()
    mode = callback.data.split(":", maxsplit=1)[1]

    data = await state.get_data()
    # Если данных нет (стерся стейт), но кнопку нажали - пытаемся восстановить или просим заново
    if not data:
         await callback.message.answer(
            "⚠️ Сессия устарела. Пожалуйста, выберите модель заново.",
            reply_markup=get_main_menu_inline_keyboard()
        )
         return
         
    supports_images = data.get("supports_images", False)
    max_images = data.get("max_images", 0)

    if mode in {"edit", "remix"} and (not supports_images or max_images <= 0):
        await callback.message.answer(
            "❌ Этот режим доступен только для моделей, поддерживающих загрузку изображений. Выберите «Создать из текста».",
            reply_markup=get_image_mode_keyboard(),
        )
        return

    if mode == "remix" and max_images < 2:
        await callback.message.answer(
            "❌ Для режима «Ремикс» требуется поддержка минимум 2 изображений. Выберите другой режим.",
            reply_markup=get_image_mode_keyboard(),
        )
        return

    await state.update_data(
        image_mode=mode,
        remix_images=[],
        edit_base_id=None,
    )

    if mode == "text":
        await callback.message.answer(
            "✍️ Отправьте текстовый промт для генерации изображения.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return

    if mode == "edit":
        await callback.message.answer(
            "🪄 Режим редактирования.\nОтправьте изображение, затем текстовый промт. Маска не требуется.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return

    if mode == "remix":
        await callback.message.answer(
            f"🎭 Режим ремикса.\nЗагрузите от 2 до {max_images} изображений (одним за другим), затем отправьте текстовый промт.",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(BotStates.image_wait_prompt)
        return