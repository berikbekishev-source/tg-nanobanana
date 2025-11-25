"""
Сервис для управления генерацией контента
"""
import uuid
from decimal import Decimal
from typing import Optional, List, Dict, Any
from django.db import transaction as db_transaction
from django.utils import timezone

from botapp.models import TgUser, GenRequest, AIModel, BotErrorEvent
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.business.pricing import calculate_request_cost
from botapp.error_tracker import ErrorTracker


class GenerationService:
    """Сервис управления генерацией контента"""

    @staticmethod
    @db_transaction.atomic
    def create_generation_request(
        user: TgUser,
        ai_model: AIModel,
        prompt: str,
        quantity: int = 1,
        generation_type: str = 'text2image',
        input_images: Optional[List[str]] = None,
        generation_params: Optional[Dict[str, Any]] = None,
        duration: Optional[int] = None,
        video_resolution: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        input_image_file_id: Optional[str] = None,
        source_media: Optional[Dict[str, Any]] = None,
        parent_request: Optional[GenRequest] = None,
    ) -> GenRequest:
        """
        Создать запрос на генерацию с проверкой баланса и списанием средств

        Args:
            user: Пользователь
            ai_model: Модель для генерации
            prompt: Промт для генерации
            quantity: Количество генераций
            generation_type: Тип генерации
            input_images: Входные изображения (для режима Remix)
            generation_params: Дополнительные параметры генерации

        Returns:
            GenRequest: Созданный запрос на генерацию

        Raises:
            InsufficientBalanceError: Если недостаточно средств
            ValueError: Если параметры некорректны
        """
        # Проверяем параметры
        if quantity > ai_model.max_quantity:
            raise ValueError(f"Максимальное количество для {ai_model.display_name}: {ai_model.max_quantity}")

        if len(prompt) > ai_model.max_prompt_length:
            raise ValueError(f"Промт слишком длинный. Максимум: {ai_model.max_prompt_length} символов")

        if input_images and len(input_images) > ai_model.max_input_images:
            raise ValueError(f"Максимум изображений: {ai_model.max_input_images}")

        model_defaults = ai_model.default_params or {}
        params: Dict[str, Any] = dict(generation_params or {})
        params.setdefault("mode", generation_type)

        if duration is None:
            duration = params.get("duration") or model_defaults.get("duration")
        else:
            params.setdefault("duration", duration)

        if video_resolution is None:
            video_resolution = params.get("resolution") or model_defaults.get("resolution")
        else:
            params.setdefault("resolution", video_resolution)

        if aspect_ratio is None:
            aspect_ratio = params.get("aspect_ratio")
        if aspect_ratio is None and params.get("aspectRatio"):
            aspect_ratio = params.get("aspectRatio")
        if aspect_ratio is None:
            aspect_ratio = model_defaults.get("aspect_ratio")

        if aspect_ratio is not None:
            # Храним аспект в snake_case, чтобы перекрывать дефолты модели
            params["aspect_ratio"] = aspect_ratio

        if input_image_file_id:
            params.setdefault("input_image_file_id", input_image_file_id)

        media_source = dict(source_media or {})
        if input_image_file_id:
            media_source.setdefault("telegram_file_id", input_image_file_id)

        input_images_payload = input_images or []
        if not input_images_payload and media_source:
            input_images_payload = [media_source]

        cost_usd, total_cost_tokens = calculate_request_cost(
            ai_model,
            quantity=quantity,
            duration=duration,
            params=params,
        )

        can_generate, error_message = BalanceService.check_can_generate(
            user,
            ai_model,
            quantity=quantity,
            total_cost_tokens=total_cost_tokens,
        )
        if not can_generate:
            raise ValueError(error_message)

        try:
            transaction = BalanceService.charge_for_generation(
                user,
                ai_model,
                quantity=quantity,
                total_cost_tokens=total_cost_tokens,
            )
        except InsufficientBalanceError:
            raise

        # Создаем запрос на генерацию
        gen_request = GenRequest.objects.create(
            run_code=str(uuid.uuid4()),
            user=user,
            chat_id=user.chat_id,
            prompt=prompt,
            generation_type=generation_type,
            ai_model=ai_model,
            model=ai_model.api_model_name,  # Для обратной совместимости
            quantity=quantity,
            input_images=input_images_payload,
            generation_params=params,
            cost=total_cost_tokens.quantize(Decimal('0.01')),
            cost_usd=cost_usd,
            status='queued',
            transaction=transaction,
            parent_request=parent_request,
            duration=duration,
            video_resolution=video_resolution or "",
            aspect_ratio=aspect_ratio or "",
            source_media=media_source,
        )

        # Обновляем статистику пользователя
        if hasattr(user, 'settings'):
            user.settings.total_generations += 1
            if generation_type in ['text2image', 'image2image']:
                user.settings.total_images_generated += quantity
            elif generation_type in ['text2video', 'image2video']:
                user.settings.total_videos_generated += quantity
            user.settings.last_generation_at = timezone.now()
            user.settings.save()

        # Обновляем статистику модели
        ai_model.total_generations += 1
        ai_model.save()

        return gen_request

    @staticmethod
    def start_generation(gen_request: GenRequest) -> None:
        """
        Начать процесс генерации

        Args:
            gen_request: Запрос на генерацию
        """
        gen_request.status = 'processing'
        gen_request.started_at = timezone.now()
        gen_request.save()

    @staticmethod
    def complete_generation(
        gen_request: GenRequest,
        result_urls: List[str],
        file_sizes: Optional[List[int]] = None,
        duration: Optional[int] = None,
        video_resolution: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        provider_job_id: Optional[str] = None,
        provider_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Завершить генерацию успешно

        Args:
            gen_request: Запрос на генерацию
            result_urls: URL результатов
            file_sizes: Размеры файлов
            duration: Длительность видео (для видео)
            video_resolution: Разрешение видео
        """
        gen_request.status = 'done'
        gen_request.completed_at = timezone.now()
        gen_request.result_urls = result_urls
        gen_request.file_sizes = file_sizes or []

        if duration:
            gen_request.duration = duration
            gen_request.generation_params["duration"] = duration
        if video_resolution:
            gen_request.video_resolution = video_resolution
            gen_request.generation_params["resolution"] = video_resolution
        if aspect_ratio:
            gen_request.aspect_ratio = aspect_ratio
            gen_request.generation_params["aspect_ratio"] = aspect_ratio
        if provider_job_id:
            gen_request.provider_job_id = provider_job_id
        if provider_metadata:
            gen_request.provider_metadata = provider_metadata

        # Рассчитываем время обработки
        if gen_request.started_at:
            processing_time = (gen_request.completed_at - gen_request.started_at).total_seconds()
            gen_request.processing_time = processing_time

            # Обновляем среднее время генерации модели
            ai_model = gen_request.ai_model
            if ai_model:
                total_gens = ai_model.total_generations
                current_avg = ai_model.average_generation_time
                # Рассчитываем новое среднее время
                new_avg = ((current_avg * (total_gens - 1)) + processing_time) / total_gens
                ai_model.average_generation_time = new_avg
                ai_model.save()

        gen_request.save()

        # Начисляем опыт пользователю
        if hasattr(gen_request.user, 'settings'):
            settings = gen_request.user.settings
            settings.experience_points += 10 * gen_request.quantity
            # Проверяем повышение уровня (каждые 100 очков = новый уровень)
            new_level = settings.experience_points // 100
            if new_level > settings.user_level:
                settings.user_level = new_level
                # Можно добавить уведомление о повышении уровня
            settings.save()

    @staticmethod
    @db_transaction.atomic
    def fail_generation(gen_request: GenRequest, error_message: str, refund: bool = True) -> None:
        """
        Отметить генерацию как неудачную

        Args:
            gen_request: Запрос на генерацию
            error_message: Сообщение об ошибке
            refund: Нужно ли вернуть средства
        """
        gen_request.status = 'error'
        gen_request.error_message = error_message
        gen_request.completed_at = timezone.now()

        # Рассчитываем время обработки
        if gen_request.started_at:
            gen_request.processing_time = (gen_request.completed_at - gen_request.started_at).total_seconds()

        gen_request.save()

        # Обновляем статистику ошибок модели
        if gen_request.ai_model:
            gen_request.ai_model.total_errors += 1
            gen_request.ai_model.save()

        ErrorTracker.log(
            origin=BotErrorEvent.Origin.GENERATION,
            severity=BotErrorEvent.Severity.WARNING,
            handler="GenerationService.fail_generation",
            user=gen_request.user,
            chat_id=gen_request.chat_id,
            gen_request=gen_request,
            message=error_message,
            payload={
                "generation_type": gen_request.generation_type,
                "ai_model": gen_request.ai_model.display_name if gen_request.ai_model else None,
                "prompt": (gen_request.prompt or "")[:400],
            },
        )

        # Возвращаем средства если нужно
        if refund and gen_request.transaction:
            BalanceService.refund_generation(
                user=gen_request.user,
                original_transaction=gen_request.transaction,
                reason=error_message
            )

    @staticmethod
    def cancel_generation(gen_request: GenRequest, refund: bool = True) -> None:
        """
        Отменить генерацию

        Args:
            gen_request: Запрос на генерацию
            refund: Нужно ли вернуть средства
        """
        gen_request.status = 'cancelled'
        gen_request.completed_at = timezone.now()
        gen_request.save()

        # Возвращаем средства если нужно
        if refund and gen_request.transaction:
            BalanceService.refund_generation(
                user=gen_request.user,
                original_transaction=gen_request.transaction,
                reason="Генерация отменена"
            )

    @staticmethod
    def get_user_generations(
        user: TgUser,
        status: Optional[str] = None,
        generation_type: Optional[str] = None,
        limit: int = 50
    ) -> List[GenRequest]:
        """
        Получить генерации пользователя

        Args:
            user: Пользователь
            status: Фильтр по статусу
            generation_type: Фильтр по типу генерации
            limit: Максимальное количество

        Returns:
            List[GenRequest]: Список генераций
        """
        queryset = GenRequest.objects.filter(user=user)

        if status:
            queryset = queryset.filter(status=status)

        if generation_type:
            queryset = queryset.filter(generation_type=generation_type)

        return queryset.order_by('-created_at')[:limit]

    @staticmethod
    def get_pending_generations() -> List[GenRequest]:
        """
        Получить все генерации в очереди

        Returns:
            List[GenRequest]: Список генераций в очереди
        """
        return GenRequest.objects.filter(status='queued').order_by('created_at')

    @staticmethod
    def get_processing_generations() -> List[GenRequest]:
        """
        Получить все генерации в обработке

        Returns:
            List[GenRequest]: Список генераций в обработке
        """
        return GenRequest.objects.filter(status='processing').order_by('started_at')

    @staticmethod
    def retry_failed_generation(gen_request: GenRequest) -> GenRequest:
        """
        Повторить неудачную генерацию

        Args:
            gen_request: Оригинальный запрос

        Returns:
            GenRequest: Новый запрос на генерацию
        """
        if gen_request.status != 'error':
            raise ValueError("Можно повторить только неудачные генерации")

        # Создаем новый запрос с теми же параметрами
        new_request = GenerationService.create_generation_request(
            user=gen_request.user,
            ai_model=gen_request.ai_model,
            prompt=gen_request.prompt,
            quantity=gen_request.quantity,
            generation_type=gen_request.generation_type,
            input_images=gen_request.input_images,
            generation_params=gen_request.generation_params
        )

        return new_request
