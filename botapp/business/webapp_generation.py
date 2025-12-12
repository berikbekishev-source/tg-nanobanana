"""
Бизнес-логика обработки WebApp данных для генерации видео.
Синхронные функции для использования в Celery задачах.
"""
import base64
import logging
import os
import subprocess
import tempfile
from decimal import Decimal
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen
from urllib.error import URLError

from django.conf import settings

from botapp.models import TgUser, AIModel, GenRequest, BotErrorEvent
from botapp.business.generation import GenerationService
from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.business.pricing import get_base_price_tokens
from botapp.services import supabase_upload_png
from botapp.error_tracker import ErrorTracker
from botapp.telegram_utils import send_message, get_main_menu_keyboard_dict
from botapp.keyboards import get_generation_start_message
from botapp.chat_logger import ChatLogger
from botapp.generation_text import (
    format_image_start_message,
    resolve_format_and_quality,
    resolve_image_mode_label,
)

logger = logging.getLogger(__name__)

# Максимальные размеры изображений
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 МБ
MAX_VIDEO_DURATION_SECONDS = 10  # Максимальная длительность видео для Kling O1


def _get_ffmpeg_exe() -> str:
    """Получить путь к ffmpeg из imageio-ffmpeg или системного."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def _get_video_duration(file_path: str) -> Optional[float]:
    """Получить длительность видео в секундах через ffprobe."""
    ffmpeg_exe = _get_ffmpeg_exe()
    # ffprobe обычно рядом с ffmpeg
    ffprobe_exe = ffmpeg_exe.replace("ffmpeg", "ffprobe") if "ffmpeg" in ffmpeg_exe else "ffprobe"

    try:
        result = subprocess.run(
            [
                ffprobe_exe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError) as exc:
        logger.warning("Не удалось получить длительность видео через ffprobe: %s", exc)

    # Fallback: попробуем через ffmpeg
    try:
        result = subprocess.run(
            [
                ffmpeg_exe,
                "-i", file_path,
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # ffmpeg выводит duration в stderr
        import re
        match = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", result.stderr)
        if match:
            h, m, s, ms = match.groups()
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("Не удалось получить длительность видео через ffmpeg: %s", exc)

    return None


def _trim_video_ffmpeg(input_path: str, output_path: str, max_duration: float) -> bool:
    """Обрезать видео до указанной длительности через ffmpeg."""
    ffmpeg_exe = _get_ffmpeg_exe()
    try:
        result = subprocess.run(
            [
                ffmpeg_exe,
                "-y",  # Перезаписывать без вопросов
                "-i", input_path,
                "-t", str(max_duration),
                "-c", "copy",  # Без перекодирования (быстро)
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("Ошибка обрезки видео ffmpeg: %s", exc)
        return False


def _trim_video_if_needed(video_url: str, max_duration: float = MAX_VIDEO_DURATION_SECONDS) -> Optional[str]:
    """
    Скачать видео, проверить длительность и обрезать при необходимости.

    Args:
        video_url: URL исходного видео
        max_duration: Максимальная длительность в секундах

    Returns:
        Новый URL (Supabase) если видео было обрезано, иначе исходный URL.
        None при ошибке.
    """
    from botapp.services import supabase_upload_video

    temp_dir = None
    try:
        # Скачиваем видео
        logger.info("[Video Trim] Downloading video from %s", video_url[:100])
        with urlopen(video_url, timeout=60) as response:
            video_data = response.read()

        if not video_data:
            logger.warning("[Video Trim] Empty video data")
            return video_url

        # Создаём временную директорию
        temp_dir = tempfile.mkdtemp(prefix="video_trim_")
        input_path = os.path.join(temp_dir, "input.mp4")
        output_path = os.path.join(temp_dir, "output.mp4")

        # Сохраняем исходное видео
        with open(input_path, "wb") as f:
            f.write(video_data)

        # Проверяем длительность
        duration = _get_video_duration(input_path)
        if duration is None:
            logger.warning("[Video Trim] Could not get duration, using original video")
            return video_url

        logger.info("[Video Trim] Video duration: %.2f sec (max: %.2f)", duration, max_duration)

        # Если видео короче или равно лимиту, возвращаем исходный URL
        if duration <= max_duration:
            logger.info("[Video Trim] Video within limit, no trimming needed")
            return video_url

        # Обрезаем видео
        logger.info("[Video Trim] Trimming video to %.2f seconds", max_duration)
        if not _trim_video_ffmpeg(input_path, output_path, max_duration):
            logger.error("[Video Trim] FFmpeg trimming failed")
            return video_url  # Возвращаем исходное видео, пусть API сам разбирается

        # Читаем обрезанное видео
        with open(output_path, "rb") as f:
            trimmed_data = f.read()

        if not trimmed_data:
            logger.error("[Video Trim] Trimmed video is empty")
            return video_url

        # Загружаем в Supabase
        logger.info("[Video Trim] Uploading trimmed video (%d bytes)", len(trimmed_data))
        upload_result = supabase_upload_video(trimmed_data, "video/mp4")

        new_url = _extract_public_url(upload_result)
        if not new_url:
            logger.error("[Video Trim] Failed to get public URL for trimmed video")
            return video_url

        logger.info("[Video Trim] Successfully trimmed and uploaded video: %s", new_url[:100])
        return new_url

    except URLError as exc:
        logger.error("[Video Trim] Failed to download video: %s", exc)
        return video_url
    except Exception as exc:
        logger.error("[Video Trim] Unexpected error: %s", exc)
        return video_url
    finally:
        # Очищаем временные файлы
        if temp_dir and os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


def _convert_to_png_bytes(raw: bytes, mime: str) -> bytes:
    """Конвертирует изображение в PNG формат."""
    try:
        from PIL import Image
        img = Image.open(BytesIO(raw))
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return raw


def _extract_public_url(upload_result) -> Optional[str]:
    """Извлекает публичный URL из результата загрузки Supabase."""
    if isinstance(upload_result, str):
        return upload_result
    if isinstance(upload_result, dict):
        return upload_result.get("publicUrl") or upload_result.get("public_url")
    if hasattr(upload_result, "public_url"):
        return upload_result.public_url
    return None


def _extract_allowed_aspect_ratios(model: AIModel) -> List[str]:
    """Извлекает допустимые соотношения сторон из модели."""
    allowed_params = model.allowed_params or {}
    aspect_param = allowed_params.get("aspect_ratio")

    if isinstance(aspect_param, list):
        return aspect_param
    if isinstance(aspect_param, dict):
        options = aspect_param.get("options") or aspect_param.get("values")
        if isinstance(options, list):
            return options

    return ["16:9", "9:16", "1:1"]


def _send_error_message(chat_id: int, text: str) -> None:
    """Отправляет сообщение об ошибке пользователю и логирует его."""
    try:
        send_message(chat_id, text, reply_markup=get_main_menu_keyboard_dict())
        # Логируем исходящее сообщение об ошибке
        ChatLogger.log_outgoing_text(chat_id, text)
    except Exception as exc:
        logger.error("Не удалось отправить сообщение об ошибке: %s", exc)


def _send_start_message(chat_id: int, text: str) -> None:
    """Отправляет сообщение о начале генерации (без клавиатуры) и логирует его."""
    try:
        send_message(chat_id, text, reply_markup=None)
        # Логируем исходящее сообщение о старте генерации
        ChatLogger.log_outgoing_text(chat_id, text)
    except Exception as exc:
        logger.error("Не удалось отправить стартовое сообщение: %s", exc)


class WebAppGenerationError(Exception):
    """Базовое исключение для ошибок обработки WebApp."""
    pass


class WebAppValidationError(WebAppGenerationError):
    """Ошибка валидации данных WebApp."""
    pass


def process_kling_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Kling WebApp и запустить генерацию.

    Args:
        user_id: ID пользователя Telegram
        payload: Данные из WebApp

    Returns:
        ID созданного GenRequest или None при ошибке
    """
    from botapp.tasks import generate_video_task

    # Получаем пользователя
    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    # Получаем модель
    # Для webapp не требуем is_active=True, т.к. некоторые модели скрыты из общего списка
    # но доступны через webapp (например kling-v2-1-master)
    model_slug = payload.get("modelSlug") or "kling-v2-5-turbo"
    try:
        model = AIModel.objects.get(slug=model_slug)
    except AIModel.DoesNotExist:
        logger.warning(f"[Kling WebApp] Model not found: {model_slug}")
        _send_error_message(user_id, "❌ Модель Kling недоступна. Выберите её заново из списка моделей.")
        return None

    if model.provider != "kling":
        _send_error_message(user_id, "❌ Эта WebApp работает только с моделью Kling.")
        return None

    # Валидация промпта
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне Kling и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "kling_settings", model_slug, prompt)

    # Тип генерации
    generation_type = (payload.get("generationType") or "text2video").lower()
    if generation_type not in {"text2video", "image2video"}:
        generation_type = "text2video"

    logger.info(f"[Kling WebApp] Starting: model_slug={model_slug}, generation_type={generation_type}, has_imageData={bool(payload.get('imageData'))}")

    # Длительность
    try:
        duration_value = int(float(payload.get("duration") or 5))
    except (TypeError, ValueError):
        duration_value = 5
    if duration_value not in {5, 10}:
        duration_value = 5

    # CFG Scale
    try:
        cfg_scale_value = max(0.0, min(1.0, round(float(payload.get("cfgScale") or 0.5), 1)))
    except (TypeError, ValueError):
        cfg_scale_value = 0.5

    # Aspect ratio
    defaults = model.default_params or {}
    allowed_aspects = _extract_allowed_aspect_ratios(model)
    requested_aspect = payload.get("aspectRatio") or payload.get("aspect_ratio") or defaults.get("aspect_ratio") or "16:9"
    aspect_ratio = requested_aspect if requested_aspect in allowed_aspects else allowed_aspects[0]

    # Определяем режим качества (std/pro)
    # Для kling-v2-1-master mode не поддерживается
    quality_mode = None
    if model_slug != "kling-v2-1-master":
        quality_mode = (payload.get("mode") or "std").lower()
        if quality_mode not in {"std", "pro"}:
            quality_mode = "std"

    # enable_audio для kling-v2-6
    enable_audio = payload.get("enableAudio") is True or payload.get("enable_audio") is True
    if model_slug == "kling-v2-6" and enable_audio:
        quality_mode = "pro"

    params = {
        "duration": duration_value,
        "cfg_scale": cfg_scale_value,
        "aspect_ratio": aspect_ratio,
    }

    # mode только если поддерживается
    if quality_mode is not None:
        params["mode"] = quality_mode

    # enable_audio если включено
    if enable_audio:
        params["enable_audio"] = True

    source_media = None

    # Обработка изображения для image2video
    if generation_type == "image2video":
        # Приоритет: imageUrl (presigned upload) > imageData (base64)
        image_url = payload.get("imageUrl")
        mime = payload.get("imageMime") or "image/png"
        file_name = payload.get("imageName") or "image.png"
        image_size = 0

        if image_url:
            # Новый способ: изображение уже загружено через presigned URL
            logger.info(f"[Kling WebApp] Using presigned imageUrl for user {user_id}")
            image_size = payload.get("imageSize") or 0
        else:
            # Старый способ: base64 данные, загружаем в Supabase
            image_b64 = payload.get("imageData")
            if not image_b64:
                _send_error_message(user_id, "❌ Загрузите изображение в WebApp для режима Image → Video.")
                return None

            try:
                raw = base64.b64decode(image_b64)
            except Exception:
                _send_error_message(user_id, "❌ Не удалось прочитать изображение. Загрузите файл ещё раз.")
                return None

            if len(raw) > MAX_IMAGE_BYTES:
                _send_error_message(user_id, "❌ Изображение слишком большое. Максимум 10 МБ.")
                return None

            image_size = len(raw)

            # Конвертируем и загружаем в Supabase
            png_bytes = _convert_to_png_bytes(raw, mime)
            try:
                upload_obj = supabase_upload_png(png_bytes)
            except Exception as exc:
                logger.error("Ошибка загрузки в Supabase: %s", exc)
                ErrorTracker.log(
                    origin=BotErrorEvent.Origin.CELERY,
                    severity=BotErrorEvent.Severity.WARNING,
                    handler="webapp_generation.process_kling_webapp",
                    chat_id=user_id,
                    payload={"reason": "supabase_upload_failed"},
                    exc=exc,
                )
                _send_error_message(user_id, "❌ Не удалось загрузить изображение. Попробуйте ещё раз.")
                return None

            image_url = _extract_public_url(upload_obj)
            if not image_url:
                _send_error_message(user_id, "❌ Не удалось получить ссылку на изображение. Попробуйте снова.")
                return None

        params["image_url"] = image_url
        source_media = {
            "file_name": file_name,
            "mime_type": mime,
            "storage_url": image_url,
            "size_bytes": image_size,
            "source": "kling_webapp",
        }

        # Обработка конечного изображения (tail) - только для v2-5-turbo и v2-1
        # Приоритет: imageTailUrl (presigned) > imageTailData (base64)
        tail_image_url = payload.get("imageTailUrl")
        tail_image_b64 = payload.get("imageTailData")

        if (tail_image_url or tail_image_b64) and model_slug not in {"kling-v2-1-master", "kling-v2-6"}:
            tail_mime = payload.get("imageTailMime") or "image/png"
            tail_file_name = payload.get("imageTailName") or "tail_image.png"
            tail_size = 0

            if tail_image_url:
                # Новый способ: tail image уже загружен через presigned URL
                logger.info(f"[Kling WebApp] Using presigned imageTailUrl for user {user_id}")
                tail_size = payload.get("imageTailSize") or 0
            else:
                # Старый способ: base64 данные
                try:
                    tail_raw = base64.b64decode(tail_image_b64)
                except Exception:
                    _send_error_message(user_id, "❌ Не удалось прочитать конечное изображение. Загрузите файл ещё раз.")
                    return None

                if len(tail_raw) > MAX_IMAGE_BYTES:
                    _send_error_message(user_id, "❌ Конечное изображение слишком большое. Максимум 10 МБ.")
                    return None

                tail_size = len(tail_raw)

                # Конвертируем и загружаем tail image в Supabase
                tail_png_bytes = _convert_to_png_bytes(tail_raw, tail_mime)
                try:
                    tail_upload_obj = supabase_upload_png(tail_png_bytes)
                except Exception as exc:
                    logger.error("Ошибка загрузки tail image в Supabase: %s", exc)
                    ErrorTracker.log(
                        origin=BotErrorEvent.Origin.CELERY,
                        severity=BotErrorEvent.Severity.WARNING,
                        handler="webapp_generation.process_kling_webapp",
                        chat_id=user_id,
                        payload={"reason": "supabase_upload_failed", "image_type": "tail"},
                        exc=exc,
                    )
                    _send_error_message(user_id, "❌ Не удалось загрузить конечное изображение. Попробуйте ещё раз.")
                    return None

                tail_image_url = _extract_public_url(tail_upload_obj)
                if not tail_image_url:
                    _send_error_message(user_id, "❌ Не удалось получить ссылку на конечное изображение. Попробуйте снова.")
                    return None

            params["image_tail"] = tail_image_url
            # При наличии tail image принудительно ставим pro
            params["mode"] = "pro"
            quality_mode = "pro"

            # Добавляем информацию о tail image в source_media
            source_media["tail_file_name"] = tail_file_name
            source_media["tail_mime_type"] = tail_mime
            source_media["tail_storage_url"] = tail_image_url
            source_media["tail_size_bytes"] = tail_size

    # Определяем модель для расчёта стоимости
    pricing_model = model
    if model_slug == "kling-v2-6" and enable_audio:
        try:
            pricing_model = AIModel.objects.get(slug="kling-v2-6-pro-with-sound")
        except AIModel.DoesNotExist:
            pass
    elif model_slug == "kling-v2-5-turbo" and quality_mode == "pro":
        try:
            pricing_model = AIModel.objects.get(slug="kling-v2-5-turbo-pro")
        except AIModel.DoesNotExist:
            pass
    elif model_slug == "kling-v2-1" and quality_mode == "pro":
        try:
            pricing_model = AIModel.objects.get(slug="kling-v2-1-pro")
        except AIModel.DoesNotExist:
            pass

    logger.info(f"[Kling WebApp] model_slug={model_slug}, quality_mode={quality_mode}, pricing_model={pricing_model.slug}, generation_type={generation_type}")

    # Создаём запрос на генерацию
    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=pricing_model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            duration=duration_value,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        logger.warning(f"[Kling WebApp] Insufficient balance for user {user_id}: {exc}")
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        logger.warning(f"[Kling WebApp] ValueError for user {user_id}: {exc}")
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest: %s", exc)
        ErrorTracker.log(
            origin=BotErrorEvent.Origin.CELERY,
            severity=BotErrorEvent.Severity.ERROR,
            handler="webapp_generation.process_kling_webapp",
            chat_id=user_id,
            payload={"generation_type": generation_type, "duration": duration_value},
            exc=exc,
        )
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    # Отправляем сообщение о начале генерации
    start_message = get_generation_start_message(
        model=model.display_name,
        mode=generation_type,
        aspect_ratio=aspect_ratio,
        resolution=None,
        duration=duration_value,
        prompt=prompt,
    )
    _send_start_message(user_id, start_message)

    # Запускаем Celery задачу генерации
    generate_video_task.delay(gen_request.id)

    return gen_request.id


def process_kling_o1_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Kling O1 (Omni) WebApp и запустить генерацию.

    Args:
        user_id: ID пользователя Telegram
        payload: Данные из WebApp

    Returns:
        ID созданного GenRequest или None при ошибке
    """
    from botapp.tasks import generate_video_task

    # Получаем пользователя
    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    # Получаем модель
    model_slug = payload.get("modelSlug") or "kling_O1"
    try:
        model = AIModel.objects.get(slug=model_slug)
    except AIModel.DoesNotExist:
        logger.warning(f"[Kling O1 WebApp] Model not found: {model_slug}")
        _send_error_message(user_id, "❌ Модель Kling O1 недоступна. Выберите её заново из списка моделей.")
        return None

    if model.provider != "kling":
        _send_error_message(user_id, "❌ Эта WebApp работает только с моделью Kling O1.")
        return None

    # Валидация промпта
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне Kling O1 и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "kling_o1_settings", model_slug, prompt)

    # Тип генерации
    generation_type = (payload.get("generationType") or "text2video").lower()
    if generation_type not in {"text2video", "image2video"}:
        generation_type = "text2video"

    logger.info(f"[Kling O1 WebApp] Starting: model_slug={model_slug}, generation_type={generation_type}")

    # Длительность для O1: 3-10 секунд
    try:
        duration_value = int(float(payload.get("duration") or 5))
    except (TypeError, ValueError):
        duration_value = 5
    if duration_value < 3:
        duration_value = 3
    if duration_value > 10:
        duration_value = 10

    # Aspect ratio
    defaults = model.default_params or {}
    allowed_aspects = _extract_allowed_aspect_ratios(model)
    requested_aspect = payload.get("aspectRatio") or payload.get("aspect_ratio") or defaults.get("aspect_ratio") or "16:9"
    aspect_ratio = requested_aspect if requested_aspect in allowed_aspects else allowed_aspects[0]

    params = {
        "duration": duration_value,
        "aspect_ratio": aspect_ratio,
        "omni_version": payload.get("omni_version") or "o1",
    }

    source_media = None
    reference_images = []

    # Собираем референсные изображения (image_1 ... image_7)
    for i in range(1, 8):
        image_key = f"image_{i}"
        image_url = payload.get(image_key)
        if image_url and isinstance(image_url, str) and image_url.startswith("http"):
            params[image_key] = image_url
            reference_images.append({"key": image_key, "url": image_url})
            # Если есть хотя бы одно изображение — это image2video
            if generation_type == "text2video":
                generation_type = "image2video"

    # Референсное видео (video_1)
    video_url = payload.get("video_1")
    if video_url and isinstance(video_url, str) and video_url.startswith("http"):
        # Авто-обрезка видео до выбранной пользователем длительности
        trimmed_url = _trim_video_if_needed(video_url, duration_value)
        if trimmed_url:
            video_url = trimmed_url
        params["video_1"] = video_url
        params["aspect_ratio"] = "auto"  # При наличии видео аспект автоматически "auto"
        aspect_ratio = "auto"

    if reference_images:
        source_media = {
            "source": "kling_o1_webapp",
            "reference_images": reference_images,
        }

    logger.info(f"[Kling O1 WebApp] Final params: duration={duration_value}, aspect={aspect_ratio}, generation_type={generation_type}, images={[k for k in params if k.startswith('image_')]}")

    # Создаём запрос на генерацию
    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            duration=duration_value,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        logger.warning(f"[Kling O1 WebApp] Insufficient balance for user {user_id}: {exc}")
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        logger.warning(f"[Kling O1 WebApp] ValueError for user {user_id}: {exc}")
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest для Kling O1: %s", exc)
        ErrorTracker.log(
            origin=BotErrorEvent.Origin.CELERY,
            severity=BotErrorEvent.Severity.ERROR,
            handler="webapp_generation.process_kling_o1_webapp",
            chat_id=user_id,
            payload={"generation_type": generation_type, "duration": duration_value},
            exc=exc,
        )
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    # Отправляем сообщение о начале генерации
    start_message = get_generation_start_message(
        model=model.display_name,
        mode=generation_type,
        aspect_ratio=aspect_ratio,
        resolution=None,
        duration=duration_value,
        prompt=prompt,
    )
    _send_start_message(user_id, start_message)

    # Запускаем Celery задачу генерации
    generate_video_task.delay(gen_request.id)

    return gen_request.id


def process_veo_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Veo WebApp и запустить генерацию.

    Args:
        user_id: ID пользователя Telegram
        payload: Данные из WebApp

    Returns:
        ID созданного GenRequest или None при ошибке
    """
    from botapp.tasks import generate_video_task

    # Получаем пользователя
    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    # Получаем модель
    model_slug = payload.get("modelSlug") or "veo3-fast"
    try:
        model = AIModel.objects.get(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        _send_error_message(user_id, "❌ Модель Veo недоступна. Выберите её заново из списка моделей.")
        return None

    if model.provider != "veo":
        _send_error_message(user_id, "❌ Эта WebApp работает только с моделью Veo.")
        return None

    # Валидация промпта
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне Veo и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "veo_video_settings", model_slug, prompt)

    # Тип генерации
    generation_type = (payload.get("generationType") or "text2video").lower()
    if generation_type not in {"text2video", "image2video"}:
        generation_type = "text2video"

    # Длительность
    try:
        duration_value = int(float(payload.get("duration") or payload.get("seconds") or 8))
    except (TypeError, ValueError):
        duration_value = 8
    allowed_durations = [5, 8]
    if duration_value not in allowed_durations:
        duration_value = 8

    # Aspect ratio
    defaults = model.default_params or {}
    aspect_ratio = payload.get("aspectRatio") or payload.get("aspect_ratio") or defaults.get("aspect_ratio") or "16:9"
    if aspect_ratio not in {"16:9", "9:16", "1:1"}:
        aspect_ratio = "16:9"

    params = {
        "duration": duration_value,
        "aspect_ratio": aspect_ratio,
    }

    source_media = None

    # Обработка изображения для image2video
    if generation_type == "image2video":
        # Приоритет: imageUrl (presigned upload) > imageData (base64)
        image_url = payload.get("imageUrl")
        mime = payload.get("imageMime") or "image/png"
        file_name = payload.get("imageName") or "image.png"
        image_size = 0

        if image_url:
            # Новый способ: изображение уже загружено через presigned URL
            logger.info(f"[Veo WebApp] Using presigned imageUrl for user {user_id}")
            image_size = payload.get("imageSize") or 0
        else:
            # Старый способ: base64 данные, загружаем в Supabase
            image_b64 = payload.get("imageData")
            if not image_b64:
                _send_error_message(user_id, "❌ Загрузите изображение для режима Image → Video.")
                return None

            try:
                raw = base64.b64decode(image_b64)
            except Exception:
                _send_error_message(user_id, "❌ Не удалось прочитать изображение. Загрузите файл ещё раз.")
                return None

            if len(raw) > MAX_IMAGE_BYTES:
                _send_error_message(user_id, "❌ Изображение слишком большое. Максимум 10 МБ.")
                return None

            image_size = len(raw)

            png_bytes = _convert_to_png_bytes(raw, mime)
            try:
                upload_obj = supabase_upload_png(png_bytes)
            except Exception as exc:
                logger.error("Ошибка загрузки в Supabase: %s", exc)
                _send_error_message(user_id, "❌ Не удалось загрузить изображение. Попробуйте ещё раз.")
                return None

            image_url = _extract_public_url(upload_obj)
            if not image_url:
                _send_error_message(user_id, "❌ Не удалось получить ссылку на изображение. Попробуйте снова.")
                return None

        params["image_url"] = image_url
        source_media = {
            "file_name": file_name,
            "mime_type": mime,
            "storage_url": image_url,
            "size_bytes": image_size,
            "source": "veo_webapp",
        }

    # Создаём запрос на генерацию
    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            duration=duration_value,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest: %s", exc)
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    # Отправляем сообщение о начале генерации
    start_message = get_generation_start_message(
        model=model.display_name,
        mode=generation_type,
        aspect_ratio=aspect_ratio,
        resolution=None,
        duration=duration_value,
        prompt=prompt,
    )
    _send_start_message(user_id, start_message)

    # Запускаем Celery задачу генерации
    generate_video_task.delay(gen_request.id)

    return gen_request.id


def process_sora_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Sora WebApp и запустить генерацию.
    """
    from botapp.tasks import generate_video_task

    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    model_slug = payload.get("modelSlug") or "sora2"
    try:
        model = AIModel.objects.get(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        _send_error_message(user_id, "❌ Модель Sora недоступна. Выберите её заново из списка моделей.")
        return None

    if model.provider != "openai":
        _send_error_message(user_id, "❌ Эта WebApp работает только с моделью Sora.")
        return None

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне настроек и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "sora2_settings", model_slug, prompt)

    generation_type = (payload.get("generationType") or "text2video").lower()
    if generation_type not in {"text2video", "image2video"}:
        generation_type = "text2video"

    try:
        duration_value = int(float(payload.get("duration") or payload.get("seconds") or 10))
    except (TypeError, ValueError):
        duration_value = 10
    if duration_value not in [10, 15]:
        duration_value = 10

    aspect_ratio = payload.get("aspectRatio") or payload.get("aspect_ratio") or "16:9"
    if aspect_ratio not in {"16:9", "9:16", "1:1"}:
        aspect_ratio = "16:9"

    resolution = payload.get("resolution") or "720p"

    params = {
        "duration": duration_value,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
    }

    source_media = None

    if generation_type == "image2video":
        # Приоритет: imageUrl (presigned upload) > imageData (base64)
        image_url = payload.get("imageUrl")
        mime = payload.get("imageMime") or "image/png"
        file_name = payload.get("imageName") or "image.png"
        image_size = 0

        if image_url:
            # Новый способ: изображение уже загружено через presigned URL
            logger.info(f"[Sora WebApp] Using presigned imageUrl for user {user_id}")
            image_size = payload.get("imageSize") or 0
        else:
            # Старый способ: base64 данные, загружаем в Supabase
            image_b64 = payload.get("imageData")
            if not image_b64:
                _send_error_message(user_id, "❌ Загрузите изображение для режима Image → Video.")
                return None

            try:
                raw = base64.b64decode(image_b64)
            except Exception:
                _send_error_message(user_id, "❌ Не удалось прочитать изображение. Загрузите файл ещё раз.")
                return None

            if len(raw) > MAX_IMAGE_BYTES:
                _send_error_message(user_id, "❌ Изображение слишком большое. Максимум 10 МБ.")
                return None

            image_size = len(raw)

            png_bytes = _convert_to_png_bytes(raw, mime)
            try:
                upload_obj = supabase_upload_png(png_bytes)
            except Exception as exc:
                logger.error("Ошибка загрузки в Supabase: %s", exc)
                _send_error_message(user_id, "❌ Не удалось загрузить изображение. Попробуйте ещё раз.")
                return None

            image_url = _extract_public_url(upload_obj)
            if not image_url:
                _send_error_message(user_id, "❌ Не удалось получить ссылку на изображение. Попробуйте снова.")
                return None

        params["image_url"] = image_url
        source_media = {
            "file_name": file_name,
            "mime_type": mime,
            "storage_url": image_url,
            "size_bytes": image_size,
            "source": "sora_webapp",
        }

    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            duration=duration_value,
            video_resolution=resolution,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest: %s", exc)
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    start_message = get_generation_start_message(
        model=model.display_name,
        mode=generation_type,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        duration=duration_value,
        prompt=prompt,
    )
    _send_start_message(user_id, start_message)

    generate_video_task.delay(gen_request.id)

    return gen_request.id


def process_runway_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Runway WebApp и запустить генерацию.
    """
    from botapp.tasks import generate_video_task

    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    model_slug = payload.get("modelSlug") or "runway-gen4"
    try:
        model = AIModel.objects.get(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        _send_error_message(user_id, "❌ Модель Runway недоступна. Выберите её заново из списка моделей.")
        return None

    # Runway использует провайдер "useapi"
    if model.provider not in {"runway", "useapi"}:
        _send_error_message(user_id, "❌ Эта WebApp работает только с моделью Runway.")
        return None

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне Runway и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "runway_settings", model_slug, prompt)

    generation_type = (payload.get("generationType") or "text2video").lower()
    if generation_type not in {"text2video", "image2video"}:
        generation_type = "text2video"

    try:
        duration_value = int(float(payload.get("duration") or 5))
    except (TypeError, ValueError):
        duration_value = 5
    if duration_value not in {5, 10}:
        duration_value = 5

    defaults = model.default_params or {}
    aspect_ratio = payload.get("aspectRatio") or payload.get("aspect_ratio") or defaults.get("aspect_ratio") or "16:9"

    params = {
        "duration": duration_value,
        "aspect_ratio": aspect_ratio,
    }

    source_media = None

    if generation_type == "image2video":
        # Приоритет: imageUrl (presigned upload) > imageData (base64)
        image_url = payload.get("imageUrl")
        mime = payload.get("imageMime") or "image/png"
        file_name = payload.get("imageName") or "image.png"
        image_size = 0

        if image_url:
            # Новый способ: изображение уже загружено через presigned URL
            logger.info(f"[Runway WebApp] Using presigned imageUrl for user {user_id}")
            image_size = payload.get("imageSize") or 0
        else:
            # Старый способ: base64 данные, загружаем в Supabase
            image_b64 = payload.get("imageData")
            if not image_b64:
                _send_error_message(user_id, "❌ Загрузите изображение для режима Image → Video.")
                return None

            try:
                raw = base64.b64decode(image_b64)
            except Exception:
                _send_error_message(user_id, "❌ Не удалось прочитать изображение. Загрузите файл ещё раз.")
                return None

            if len(raw) > MAX_IMAGE_BYTES:
                _send_error_message(user_id, "❌ Изображение слишком большое. Максимум 10 МБ.")
                return None

            image_size = len(raw)

            png_bytes = _convert_to_png_bytes(raw, mime)
            try:
                upload_obj = supabase_upload_png(png_bytes)
            except Exception as exc:
                logger.error("Ошибка загрузки в Supabase: %s", exc)
                _send_error_message(user_id, "❌ Не удалось загрузить изображение. Попробуйте ещё раз.")
                return None

            image_url = _extract_public_url(upload_obj)
            if not image_url:
                _send_error_message(user_id, "❌ Не удалось получить ссылку на изображение. Попробуйте снова.")
                return None

        params["image_url"] = image_url
        source_media = {
            "file_name": file_name,
            "mime_type": mime,
            "storage_url": image_url,
            "size_bytes": image_size,
            "source": "runway_webapp",
        }

    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            duration=duration_value,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest: %s", exc)
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    start_message = get_generation_start_message(
        model=model.display_name,
        mode=generation_type,
        aspect_ratio=aspect_ratio,
        resolution=None,
        duration=duration_value,
        prompt=prompt,
    )
    _send_start_message(user_id, start_message)

    generate_video_task.delay(gen_request.id)

    return gen_request.id


def process_midjourney_video_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Midjourney Video WebApp и запустить генерацию.
    """
    from botapp.tasks import generate_video_task

    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    model_slug = payload.get("modelSlug") or "midjourney-video"
    try:
        model = AIModel.objects.get(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        _send_error_message(user_id, "❌ Модель Midjourney Video недоступна.")
        return None

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "midjourney_video_settings", model_slug, prompt)

    generation_type = "text2video"

    defaults = model.default_params or {}
    aspect_ratio = payload.get("aspectRatio") or defaults.get("aspect_ratio") or "16:9"

    params = {
        "aspect_ratio": aspect_ratio,
    }

    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            aspect_ratio=aspect_ratio,
        )
    except InsufficientBalanceError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest: %s", exc)
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    start_message = get_generation_start_message(
        model=model.display_name,
        mode=generation_type,
        aspect_ratio=aspect_ratio,
        resolution=None,
        duration=None,
        prompt=prompt,
    )
    _send_start_message(user_id, start_message)

    generate_video_task.delay(gen_request.id)

    return gen_request.id


def process_midjourney_image_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Midjourney Image WebApp и запустить генерацию изображения.

    Args:
        user_id: ID пользователя Telegram
        payload: Данные из WebApp

    Returns:
        ID созданного GenRequest или None при ошибке
    """
    from botapp.tasks import generate_image_task

    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    # Получаем модель
    model_slug = payload.get("modelSlug") or "midjourney-v7-fast"
    try:
        model = AIModel.objects.get(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        _send_error_message(user_id, f"⚠️ Модель {model_slug} недоступна. Выберите её заново из списка моделей.")
        return None

    if model.provider != "midjourney":
        _send_error_message(user_id, "⚠️ WebApp настройки доступны только для моделей Midjourney.")
        return None

    # Валидация промпта
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне настроек и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "midjourney_settings", model_slug, prompt)

    # Проверка баланса
    cost = get_base_price_tokens(model)
    balance_service = BalanceService()
    can_generate, error_msg = balance_service.check_can_generate(user, model, total_cost_tokens=cost)
    if not can_generate:
        try:
            current_balance = balance_service.get_balance(user)
        except Exception:
            current_balance = Decimal("0.00")
        _send_error_message(
            user_id,
            f"❌ {error_msg}\n\n"
            f"Необходимо: ⚡{cost:.2f}\n"
            f"Ваш баланс: ⚡{current_balance:.2f}\n\n"
            f"Пополните баланс и попробуйте снова."
        )
        return None

    # Тип задачи
    task_type = payload.get("taskType") or "mj_txt2img"
    generation_type = "text2image" if task_type == "mj_txt2img" else "image2image"
    image_mode = "text" if task_type == "mj_txt2img" else "edit"

    def normalize_int(value, default, min_v, max_v, step=None):
        try:
            num = int(float(value))
        except (TypeError, ValueError):
            num = default
        num = max(min_v, min(max_v, num))
        if step and step > 0:
            num = int(round(num / step) * step)
        return num

    aspect_ratio_value = payload.get("aspectRatio") or "1:1"

    midjourney_params = {
        "speed": payload.get("speed") or "fast",
        "aspectRatio": aspect_ratio_value,
        "aspect_ratio": aspect_ratio_value,
        "version": str(payload.get("version") or "7"),
        "stylization": normalize_int(payload.get("stylization"), 200, 0, 1000, 10),
        "weirdness": normalize_int(payload.get("weirdness"), 0, 0, 3000, 50),
        "variety": normalize_int(payload.get("variety"), 10, 0, 100, 5),
        "image_mode": image_mode,
    }

    # Обработка изображений для img2img
    input_images: List[Dict[str, Any]] = []
    if generation_type == "image2image":
        image_data = payload.get("imageData")
        image_mime = payload.get("imageMime") or "image/png"
        image_name = payload.get("imageName") or "image.png"

        if not image_data:
            _send_error_message(user_id, "❌ Для режима «Изображение → Изображение» нужно загрузить картинку в WebApp.")
            return None

        try:
            raw = base64.b64decode(image_data)
        except Exception:
            _send_error_message(user_id, "❌ Не удалось прочитать изображение из WebApp. Загрузите файл ещё раз.")
            return None

        if len(raw) > MAX_IMAGE_BYTES:
            _send_error_message(user_id, "❌ Изображение слишком большое. Максимум 10 МБ.")
            return None

        input_images.append({
            "content_base64": image_data,
            "mime_type": image_mime,
            "file_name": image_name,
        })

    # Создаём запрос на генерацию
    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            input_images=input_images,
            generation_params=midjourney_params,
            aspect_ratio=aspect_ratio_value,
        )
    except InsufficientBalanceError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest для Midjourney image: %s", exc)
        ErrorTracker.log(
            origin=BotErrorEvent.Origin.CELERY,
            severity=BotErrorEvent.Severity.ERROR,
            handler="webapp_generation.process_midjourney_image_webapp",
            chat_id=user_id,
            payload={"generation_type": generation_type, "model_slug": model_slug},
            exc=exc,
        )
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    # Формируем стартовое сообщение
    format_value, quality_value = resolve_format_and_quality(
        model.provider,
        midjourney_params,
        aspect_ratio=aspect_ratio_value,
    )
    mode_label = resolve_image_mode_label(generation_type, image_mode)
    model_title = model.display_name or model.name

    start_message = format_image_start_message(
        model_title,
        mode_label,
        format_value,
        quality_value,
        prompt,
    )
    _send_start_message(user_id, start_message)

    # Запускаем Celery задачу генерации
    generate_image_task.delay(gen_request.id)

    return gen_request.id


def process_gpt_image_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные GPT Image WebApp и запустить генерацию изображения.

    Args:
        user_id: ID пользователя Telegram
        payload: Данные из WebApp

    Returns:
        ID созданного GenRequest или None при ошибке
    """
    from botapp.tasks import generate_image_task

    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    model_slug = payload.get("modelSlug") or "gpt-image-1"
    try:
        model = AIModel.objects.get(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        _send_error_message(user_id, f"⚠️ Модель {model_slug} недоступна. Выберите её заново из списка моделей.")
        return None

    if model.provider != "openai_image":
        _send_error_message(user_id, "⚠️ Этот WebApp работает только с моделью GPT Image.")
        return None

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне настроек и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "gpt_image_settings", model_slug, prompt)

    # Проверка баланса
    cost = get_base_price_tokens(model)
    balance_service = BalanceService()
    can_generate, error_msg = balance_service.check_can_generate(user, model, total_cost_tokens=cost)
    if not can_generate:
        try:
            current_balance = balance_service.get_balance(user)
        except Exception:
            current_balance = Decimal("0.00")
        _send_error_message(
            user_id,
            f"❌ {error_msg}\n"
            f"Необходимо: ⚡{cost:.2f}\n"
            f"Ваш баланс: ⚡{current_balance:.2f}\n\n"
            f"Пополните баланс и попробуйте снова."
        )
        return None

    task_type = payload.get("taskType") or "gpt_txt2img"
    generation_type = "text2image" if task_type == "gpt_txt2img" else "image2image"
    image_mode = "text" if task_type == "gpt_txt2img" else "edit"

    def normalize_size(value: Any) -> str:
        allowed = {"1024x1024", "1024x1536", "1536x1024", "auto"}
        text_value = str(value or "1024x1024").lower()
        return text_value if text_value in allowed else "1024x1024"

    def normalize_quality(value: Any) -> str:
        allowed = {"low", "medium", "high", "auto"}
        text_value = str(value or "auto").lower()
        return text_value if text_value in allowed else "auto"

    raw_params = payload.get("params") or {}
    gpt_params = {
        "size": normalize_size(raw_params.get("size")),
        "quality": normalize_quality(raw_params.get("quality")),
        "image_mode": image_mode,
    }

    # Обработка изображений
    input_images: List[Dict[str, Any]] = []
    max_images_supported = getattr(model, "max_input_images", 0) or 4

    for item in payload.get("images") or []:
        base = item.get("data")
        if not base:
            continue
        try:
            raw_bytes = base64.b64decode(base)
        except Exception:
            _send_error_message(user_id, "❌ Не удалось прочитать одно из изображений. Загрузите файл снова.")
            return None

        if len(raw_bytes) > MAX_IMAGE_BYTES:
            _send_error_message(user_id, "❌ Одно из изображений слишком большое. Максимум 10 МБ.")
            return None

        mime = item.get("mime") or "image/png"
        name = item.get("name") or "image.png"
        input_images.append({
            "content_base64": base,
            "mime_type": mime,
            "file_name": name,
        })

    if generation_type == "image2image" and not input_images:
        _send_error_message(user_id, "❌ Для режима «Изображение → Изображение» нужно загрузить хотя бы одну картинку в WebApp.")
        return None

    if input_images and len(input_images) > max_images_supported:
        input_images = input_images[:max_images_supported]

    # Создаём запрос на генерацию
    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            input_images=input_images,
            generation_params=gpt_params,
        )
    except InsufficientBalanceError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest для GPT Image: %s", exc)
        ErrorTracker.log(
            origin=BotErrorEvent.Origin.CELERY,
            severity=BotErrorEvent.Severity.ERROR,
            handler="webapp_generation.process_gpt_image_webapp",
            chat_id=user_id,
            payload={"generation_type": generation_type, "model_slug": model_slug},
            exc=exc,
        )
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    # Формируем стартовое сообщение
    aspect_ratio = gpt_params.get("size", "1024x1024")
    format_value, quality_value = resolve_format_and_quality(
        model.provider,
        gpt_params,
        aspect_ratio=aspect_ratio,
    )
    mode_label = resolve_image_mode_label(generation_type, image_mode)
    model_title = model.display_name or model.name

    start_message = format_image_start_message(
        model_title,
        mode_label,
        format_value,
        quality_value,
        prompt,
    )
    _send_start_message(user_id, start_message)

    # Запускаем Celery задачу генерации
    generate_image_task.delay(gen_request.id)

    return gen_request.id


def process_nano_banana_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Nano Banana WebApp (Gemini 3 Pro) и запустить генерацию изображения.

    Args:
        user_id: ID пользователя Telegram
        payload: Данные из WebApp

    Returns:
        ID созданного GenRequest или None при ошибке
    """
    from botapp.tasks import generate_image_task

    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    model_slug = payload.get("modelSlug") or "nano-banana-pro"
    try:
        model = AIModel.objects.get(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        _send_error_message(user_id, "❌ Модель Nano Banana недоступна. Выберите её заново из списка моделей.")
        return None

    if model.provider not in {"gemini_vertex", "gemini"}:
        _send_error_message(user_id, "❌ Эта WebApp работает только с Nano Banana (Gemini).")
        return None

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне настроек и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "nano_banana_settings", model_slug, prompt)

    # Проверка баланса
    cost = get_base_price_tokens(model)
    balance_service = BalanceService()
    can_generate, error_msg = balance_service.check_can_generate(user, model, total_cost_tokens=cost)
    if not can_generate:
        try:
            current_balance = balance_service.get_balance(user)
        except Exception:
            current_balance = Decimal("0.00")
        _send_error_message(
            user_id,
            f"❌ {error_msg}\n"
            f"Необходимо: ⚡{cost:.2f}\n"
            f"Ваш баланс: ⚡{current_balance:.2f}\n"
        )
        return None

    # Aspect ratio
    allowed_aspects = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9"}
    aspect_ratio = (
        payload.get("aspectRatio")
        or payload.get("aspect_ratio")
        or (model.default_params or {}).get("aspect_ratio")
        or "1:1"
    )
    if aspect_ratio not in allowed_aspects:
        aspect_ratio = "1:1"

    # Quality / image size
    raw_quality = (payload.get("imageSize") or payload.get("quality") or "1K").upper()
    quality_allowed = {"1K", "2K", "4K"} if "pro" in model.slug else {"1K"}
    image_size = raw_quality if raw_quality in quality_allowed else next(iter(quality_allowed))

    # Generation type
    generation_type_raw = (payload.get("generationType") or payload.get("taskType") or "text2image").lower()
    generation_type = "image2image" if generation_type_raw in {"image2image", "img2img", "nano_img2img"} else "text2image"
    image_mode = "edit" if generation_type == "image2image" else "text"

    # Обработка изображений
    input_images: List[Dict[str, Any]] = []
    if generation_type == "image2image":
        incoming = payload.get("images") or []
        max_allowed = min(model.max_input_images or len(incoming) or 1, 8)
        for idx, img in enumerate(incoming[:max_allowed]):
            data_b64 = img.get("data") or img.get("base64") or img.get("content") or ""
            if not data_b64:
                continue
            if "," in data_b64:
                data_b64 = data_b64.split(",")[-1]
            try:
                raw_bytes = base64.b64decode(data_b64)
            except Exception:
                continue
            if len(raw_bytes) > MAX_IMAGE_BYTES:
                continue
            mime = img.get("mime") or img.get("mime_type") or "image/png"
            name = img.get("name") or img.get("file_name") or f"image_{idx + 1}.png"
            input_images.append({
                "content_base64": base64.b64encode(raw_bytes).decode(),
                "mime_type": mime,
                "file_name": name,
                "size": len(raw_bytes),
                "source": "nano_webapp",
            })

        if not input_images:
            _send_error_message(user_id, "❌ Загрузите хотя бы одно изображение (до 8 файлов, до 10 МБ каждый).")
            return None

    params = {
        "image_mode": image_mode,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
    }

    # Создаём запрос на генерацию
    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            input_images=input_images,
            generation_params=params,
            aspect_ratio=aspect_ratio,
        )
    except InsufficientBalanceError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest для Nano Banana: %s", exc)
        ErrorTracker.log(
            origin=BotErrorEvent.Origin.CELERY,
            severity=BotErrorEvent.Severity.ERROR,
            handler="webapp_generation.process_nano_banana_webapp",
            chat_id=user_id,
            payload={
                "generation_type": generation_type,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
                "images": len(input_images),
            },
            exc=exc,
        )
        _send_error_message(user_id, "❌ Не удалось подготовить генерацию. Попробуйте ещё раз.")
        return None

    # Формируем стартовое сообщение
    start_message = format_image_start_message(
        model.display_name,
        resolve_image_mode_label(generation_type),
        aspect_ratio,
        image_size,
        prompt,
    )
    _send_start_message(user_id, start_message)

    # Запускаем Celery задачу генерации
    generate_image_task.delay(gen_request.id)

    return gen_request.id



def process_runway_aleph_webapp(user_id: int, payload: Dict[str, Any]) -> Optional[int]:
    """
    Обработать данные Runway Aleph WebApp и запустить генерацию video2video.

    Args:
        user_id: ID пользователя Telegram
        payload: Данные из WebApp

    Returns:
        ID созданного GenRequest или None при ошибке
    """
    from botapp.tasks import generate_video_task

    try:
        user = TgUser.objects.get(chat_id=user_id)
    except TgUser.DoesNotExist:
        _send_error_message(user_id, "❌ Не удалось найти пользователя. Начните заново.")
        return None

    model_slug = payload.get("modelSlug") or "runway_aleph"
    try:
        model = AIModel.objects.get(slug=model_slug, is_active=True)
    except AIModel.DoesNotExist:
        _send_error_message(user_id, "❌ Модель Runway Aleph недоступна. Выберите её заново из списка моделей.")
        return None

    if model.provider not in {"runway", "useapi"}:
        _send_error_message(user_id, "❌ Эта WebApp работает только с моделью Runway Aleph.")
        return None

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        _send_error_message(user_id, "❌ Введите промт в окне Runway Aleph и отправьте ещё раз.")
        return None

    if len(prompt) > model.max_prompt_length:
        _send_error_message(user_id, f"❌ Промт слишком длинный! Максимум {model.max_prompt_length} символов.")
        return None

    # Логируем входящий webapp-запрос
    ChatLogger.log_webapp_request(user_id, "runway_aleph_settings", model_slug, prompt)

    # Runway Aleph работает только в режиме video2video
    generation_type = "video2video"

    defaults = model.default_params or {}
    aspect_ratio = payload.get("aspectRatio") or payload.get("aspect_ratio") or defaults.get("aspect_ratio") or "16:9"

    params = {
        "aspect_ratio": aspect_ratio,
    }

    source_media = None

    # Обработка видео для video2video (обязательно)
    video_b64 = payload.get("videoData")
    if not video_b64:
        _send_error_message(user_id, "❌ Загрузите видео для режима Video → Video.")
        return None

    try:
        raw = base64.b64decode(video_b64)
    except Exception:
        _send_error_message(user_id, "❌ Не удалось прочитать видео. Загрузите файл ещё раз.")
        return None

    max_video_bytes = 10 * 1024 * 1024  # 10 МБ
    if len(raw) > max_video_bytes:
        _send_error_message(user_id, "❌ Видео слишком большое. Максимум 10 МБ.")
        return None

    mime = payload.get("videoMime") or "video/mp4"
    file_name = payload.get("videoName") or "video.mp4"

    # Загружаем видео в Supabase
    try:
        from botapp.services import supabase_upload_video
        upload_obj = supabase_upload_video(raw, mime)
    except Exception as exc:
        logger.error("Ошибка загрузки видео в Supabase: %s", exc)
        _send_error_message(user_id, "❌ Не удалось загрузить видео. Попробуйте ещё раз.")
        return None

    video_url = _extract_public_url(upload_obj)
    if not video_url:
        _send_error_message(user_id, "❌ Не удалось получить ссылку на видео. Попробуйте снова.")
        return None

    params["video_url"] = video_url
    source_media = {
        "file_name": file_name,
        "mime_type": mime,
        "storage_url": video_url,
        "size_bytes": len(raw),
        "source": "runway_aleph_webapp",
    }

    try:
        gen_request = GenerationService.create_generation_request(
            user=user,
            ai_model=model,
            prompt=prompt,
            quantity=1,
            generation_type=generation_type,
            generation_params=params,
            aspect_ratio=aspect_ratio,
            source_media=source_media,
        )
    except InsufficientBalanceError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except ValueError as exc:
        _send_error_message(user_id, str(exc))
        return None
    except Exception as exc:
        logger.error("Ошибка создания GenRequest для Runway Aleph: %s", exc)
        _send_error_message(user_id, "❌ Произошла ошибка при подготовке генерации. Попробуйте ещё раз.")
        return None

    start_message = get_generation_start_message(
        model=model.display_name,
        mode=generation_type,
        aspect_ratio=aspect_ratio,
        resolution=None,
        duration=None,
        prompt=prompt,
    )
    _send_start_message(user_id, start_message)

    generate_video_task.delay(gen_request.id)

    return gen_request.id


# Маппинг kind → функция обработки
WEBAPP_PROCESSORS = {
    # Video processors
    "kling_settings": process_kling_webapp,
    "kling_o1_settings": process_kling_o1_webapp,
    "veo_video_settings": process_veo_webapp,
    "sora2_settings": process_sora_webapp,
    "runway_settings": process_runway_webapp,
    "runway_aleph_settings": process_runway_aleph_webapp,
    "midjourney_video_settings": process_midjourney_video_webapp,
    # Image processors
    "midjourney_settings": process_midjourney_image_webapp,
    "gpt_image_settings": process_gpt_image_webapp,
    "nano_banana_settings": process_nano_banana_webapp,
}


def process_webapp_submission(user_id: int, data: Dict[str, Any]) -> Optional[int]:
    """
    Универсальная точка входа для обработки WebApp данных.

    Args:
        user_id: ID пользователя Telegram
        data: Данные из WebApp (должны содержать поле 'kind')

    Returns:
        ID созданного GenRequest или None при ошибке
    """
    kind = data.get("kind")
    if not kind:
        logger.warning("WebApp submission без поля 'kind': user_id=%s", user_id)
        _send_error_message(user_id, "❌ Некорректные данные из WebApp. Попробуйте ещё раз.")
        return None

    processor = WEBAPP_PROCESSORS.get(kind)
    if not processor:
        logger.warning("Неизвестный kind WebApp: %s, user_id=%s", kind, user_id)
        # Для неизвестных kind просто игнорируем — возможно их обрабатывает другой handler
        return None

    return processor(user_id, data)
