"""
Celery задачи для асинхронной генерации изображений и видео
"""
from celery import shared_task
import httpx
from django.conf import settings
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache
import json
import os
import tempfile
import subprocess

from imageio_ffmpeg import get_ffmpeg_exe, get_ffprobe_exe

from .models import GenRequest, TgUser, AIModel
from .services import generate_images, supabase_upload_png, supabase_upload_video
from .keyboards import get_generation_complete_message, get_main_menu_inline_keyboard
from .providers import get_video_provider, VideoGenerationError
from .business.generation import GenerationService


def send_telegram_photo(chat_id: int, photo_bytes: bytes, caption: str, reply_markup: Optional[Dict] = None):
    """Отправка фото в Telegram через Bot API напрямую (без aiogram)"""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("image.png", photo_bytes, "image/png")}
    data = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    with httpx.Client(timeout=30) as client:
        resp = client.post(url, files=files, data=data)
        resp.raise_for_status()
        return resp.json()


def send_telegram_video(chat_id: int, video_bytes: bytes, caption: str, reply_markup: Optional[Dict] = None):
    """Отправка видео в Telegram через Bot API напрямую"""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendVideo"
    files = {"video": ("video.mp4", video_bytes, "video/mp4")}
    data = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    with httpx.Client(timeout=60) as client:
        resp = client.post(url, files=files, data=data)
        resp.raise_for_status()
        return resp.json()


def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[Dict] = None, parse_mode: Optional[str] = "Markdown"):
    """Отправка текстового сообщения в Telegram через Bot API"""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    with httpx.Client(timeout=10) as client:
        resp = client.post(url, json=data)
        resp.raise_for_status()
        return resp.json()


def get_inline_menu_markup():
    """Получение разметки inline кнопки главного меню для JSON"""
    return {
        "inline_keyboard": [[
            {
                "text": "🏠 Главное меню",
                "callback_data": "main_menu"
            }
        ]]
    }


def get_video_result_markup(request_id: int, include_extension: bool = True) -> Dict[str, Any]:
    """Inline клавиатура для результатов видео."""
    keyboard: List[List[Dict[str, str]]] = []
    if include_extension:
        keyboard.append([{
            "text": "🔁 Продлить FAST",
            "callback_data": f"extend_video:{request_id}",
        }])
    keyboard.append([{
        "text": "🏠 Главное меню",
        "callback_data": "main_menu",
    }])
    return {"inline_keyboard": keyboard}


def fetch_remote_file(url: str) -> bytes:
    """Скачать файл по URL и вернуть байтовое содержимое."""
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


@lru_cache()
def _ffmpeg_bin() -> str:
    return get_ffmpeg_exe()


@lru_cache()
def _ffprobe_bin() -> str:
    try:
        return get_ffprobe_exe()
    except Exception:
        return get_ffmpeg_exe()


def _run_command(command: List[str]) -> str:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({' '.join(command)}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _probe_frames(path: str) -> int:
    try:
        output = _run_command([
            _ffprobe_bin(),
            "-v", "error",
            "-select_streams", "v:0",
            "-count_frames",
            "-show_entries", "stream=nb_read_frames",
            "-of", "default=nokey=1:noprint_wrappers=1",
            path,
        ])
        return int(float(output))
    except Exception:
        return 0


def _probe_duration(path: str) -> Optional[float]:
    try:
        out = _run_command([
            _ffprobe_bin(),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nokey=1:noprint_wrappers=1",
            path,
        ])
        return float(out)
    except Exception:
        return None


def _probe_resolution(path: str) -> Tuple[Optional[int], Optional[int]]:
    try:
        out = _run_command([
            _ffprobe_bin(),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            path,
        ])
        width, height = out.split(",")
        return int(width), int(height)
    except Exception:
        return None, None


def _probe_has_audio(path: str) -> bool:
    try:
        out = _run_command([
            _ffprobe_bin(),
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            path,
        ])
        return out.strip() == "audio"
    except Exception:
        return False


def extract_last_frame(video_bytes: bytes) -> bytes:
    """
    Извлекает последний кадр видео (PNG) с помощью ffmpeg.
    """
    temp_paths: List[str] = []
    frame_bytes: Optional[bytes] = None
    try:
        fd_input, input_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd_input)
        with open(input_path, "wb") as fh:
            fh.write(video_bytes)
        temp_paths.append(input_path)

        fd_frame, frame_path = tempfile.mkstemp(suffix=".png")
        os.close(fd_frame)
        temp_paths.append(frame_path)

        total_frames = _probe_frames(input_path)
        if total_frames > 0:
            last_idx = max(total_frames - 1, 0)
            select_expr = f"select='eq(n,{last_idx})'"
            command = [
                _ffmpeg_bin(),
                "-y",
                "-i", input_path,
                "-vf", select_expr,
                "-vframes", "1",
                frame_path,
            ]
        else:
            command = [
                _ffmpeg_bin(),
                "-y",
                "-sseof", "-0.04",
                "-i", input_path,
                "-vframes", "1",
                frame_path,
            ]

        try:
            _run_command(command)
        except RuntimeError:
            fallback_command = [
                _ffmpeg_bin(),
                "-y",
                "-i", input_path,
                "-vframes", "1",
                frame_path,
            ]
            _run_command(fallback_command)

        with open(frame_path, "rb") as fh_frame:
            frame_bytes = fh_frame.read()

        if not frame_bytes:
            raise RuntimeError("Не удалось извлечь кадр видео.")

        return frame_bytes
    finally:
        for path in temp_paths:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass


def combine_videos_with_crossfade(
    part1_bytes: bytes,
    part2_bytes: bytes,
    fade_duration: float = 1.0,
) -> Tuple[bytes, float, Tuple[int, int]]:
    """
    Склеивает два видео с плавным переходом (видео и, при наличии, аудио) через ffmpeg.
    """
    temp_paths: List[str] = []
    output_path = ""
    try:
        fd1, path1 = tempfile.mkstemp(suffix=".mp4")
        os.close(fd1)
        with open(path1, "wb") as fh:
            fh.write(part1_bytes)
        temp_paths.append(path1)

        fd2, path2 = tempfile.mkstemp(suffix=".mp4")
        os.close(fd2)
        with open(path2, "wb") as fh2:
            fh2.write(part2_bytes)
        temp_paths.append(path2)

        fd_out, output_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd_out)
        temp_paths.append(output_path)

        duration1 = _probe_duration(path1) or 0.0
        duration2 = _probe_duration(path2) or 0.0

        fade = max(min(fade_duration, duration1 / 2 if duration1 else fade_duration, duration2 / 2 if duration2 else fade_duration), 0.5)
        offset = max(duration1 - fade, 0.0)

        has_audio1 = _probe_has_audio(path1)
        has_audio2 = _probe_has_audio(path2)

        filter_parts = [
            f"[0:v][1:v]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}[v]"
        ]
        map_args: List[str] = ["-map", "[v]"]
        audio_codec_args: List[str] = ["-an"]

        if has_audio1 and has_audio2:
            filter_parts.append(f"[0:a][1:a]acrossfade=d={fade:.3f}[a]")
            map_args.extend(["-map", "[a]"])
            audio_codec_args = ["-c:a", "aac", "-b:a", "192k"]
        elif has_audio2:
            map_args.extend(["-map", "1:a"])
            audio_codec_args = ["-c:a", "aac", "-b:a", "192k"]
        elif has_audio1:
            map_args.extend(["-map", "0:a"])
            audio_codec_args = ["-c:a", "aac", "-b:a", "192k"]

        command = [
            _ffmpeg_bin(),
            "-y",
            "-i", path1,
            "-i", path2,
            "-filter_complex", ";".join(filter_parts),
            *map_args,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            *audio_codec_args,
            "-movflags", "+faststart",
            output_path,
        ]

        _run_command(command)

        with open(output_path, "rb") as fh_out:
            combined_bytes = fh_out.read()

        final_duration = duration1 + duration2 - fade if duration1 and duration2 else duration1 + duration2
        width, height = _probe_resolution(output_path)

        return combined_bytes, final_duration, (width or 0, height or 0)
    finally:
        for path in temp_paths:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass

def download_telegram_file(file_id: str) -> Tuple[bytes, str]:
    """Скачать файл из Telegram и вернуть (bytes, mime_type)."""
    api_base = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        resp = client.get(f"{api_base}/getFile", params={"file_id": file_id})
        resp.raise_for_status()
        result = resp.json().get("result")
        if not result:
            raise ValueError("Не удалось получить файл из Telegram")
        file_path = result["file_path"]
        file_resp = client.get(f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}")
        file_resp.raise_for_status()
        mime_type = file_resp.headers.get("Content-Type", "application/octet-stream")
        return file_resp.content, mime_type


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_image_task(self, request_id: int):
    """
    Задача генерации изображений
    """
    try:
        req = GenRequest.objects.select_related('user', 'ai_model').get(id=request_id)

        # Получаем модель и параметры
        model = req.ai_model
        prompt = req.prompt
        quantity = req.quantity or 1
        generation_type = req.generation_type or 'text2image'

        # Вызываем сервис генерации изображений
        if generation_type == 'text2image':
            imgs = generate_images(prompt, quantity)
        else:
            # Для image2image нужно получить входное изображение
            # TODO: Реализовать загрузку и обработку входного изображения
            imgs = generate_images(prompt, quantity)

        urls = []
        inline_markup = get_inline_menu_markup()

        # Загружаем и отправляем каждое изображение
        for idx, img in enumerate(imgs, start=1):
            # Загружаем в Storage
            url_obj = supabase_upload_png(img)
            url = url_obj.get("public_url") if isinstance(url_obj, dict) else url_obj
            urls.append(url)

            # Формируем системное сообщение после генерации
            system_message = get_generation_complete_message(
                prompt=prompt,
                generation_type=generation_type,
                model_name=model.display_name,
                quantity=quantity,
                aspect_ratio=req.aspect_ratio or "1:1"
            )

            # Отправляем изображение с системным сообщением
            send_telegram_photo(
                chat_id=req.chat_id,
                photo_bytes=img,
                caption=system_message + f"\n\n📷 Изображение {idx}/{quantity}",
                reply_markup=inline_markup
            )

        # Обновляем статус запроса
        req.status = "done"
        req.result_urls = urls
        req.save(update_fields=["status", "result_urls"])

    except Exception as e:
        req.status = "error"
        req.save(update_fields=["status"])

        # Отправляем сообщение об ошибке
        send_telegram_message(
            req.chat_id,
            f"❌ Ошибка генерации изображения: {str(e)}",
            reply_markup=get_inline_menu_markup()
        )
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_video_task(self, request_id: int):
    """
    Задача генерации видео через провайдеров (Vertex Veo и др.)
    """
    req = GenRequest.objects.select_related('user', 'ai_model', 'transaction').get(id=request_id)
    try:
        GenerationService.start_generation(req)

        model = req.ai_model
        if not model:
            raise VideoGenerationError("У запроса отсутствует связанная модель.")

        prompt = req.prompt
        generation_type = req.generation_type or 'text2video'

        provider = get_video_provider(model.provider)

        params: Dict[str, Any] = {}
        params.update(model.default_params or {})
        params.update(req.generation_params or {})

        input_media: Optional[bytes] = None
        input_mime_type: Optional[str] = None

        source_media = req.source_media if isinstance(req.source_media, dict) else {}
        telegram_file_id = params.get("input_image_file_id") or source_media.get("telegram_file_id")
        if generation_type == 'image2video' and telegram_file_id:
            input_media, input_mime_type = download_telegram_file(telegram_file_id)

        result = provider.generate(
            prompt=prompt,
            model_name=model.api_model_name,
            generation_type=generation_type,
            params=params,
            input_media=input_media,
            input_mime_type=input_mime_type,
        )

        upload_result = supabase_upload_video(result.content, mime_type=result.mime_type)
        public_url = upload_result.get("public_url") if isinstance(upload_result, dict) else upload_result

        GenerationService.complete_generation(
            req,
            result_urls=[public_url],
            file_sizes=[len(result.content)],
            duration=result.duration,
            video_resolution=result.resolution,
            aspect_ratio=result.aspect_ratio,
            provider_job_id=result.provider_job_id,
            provider_metadata=result.metadata,
        )

        transaction = req.transaction
        if transaction:
            transaction.refresh_from_db()
            charged_amount = transaction.amount
            balance_after = transaction.balance_after
        else:
            charged_amount = Decimal("0.00")
            balance_after = Decimal("0.00")

        message = get_generation_complete_message(
            prompt=prompt,
            generation_type=generation_type,
            model_name=model.display_name,
            duration=req.duration or result.duration,
            resolution=req.video_resolution or result.resolution,
            aspect_ratio=req.aspect_ratio or result.aspect_ratio,
            model_hashtag=model.hashtag,
            charged_amount=charged_amount,
            balance_after=balance_after,
        )

        send_telegram_video(
            chat_id=req.chat_id,
            video_bytes=result.content,
            caption=message,
            reply_markup=get_video_result_markup(req.id),
        )

    except VideoGenerationError as e:
        GenerationService.fail_generation(req, str(e), refund=True)
        error_text = str(e)
        if len(error_text) > 3500:
            error_text = error_text[:3500] + "…"
        try:
            send_telegram_message(
                req.chat_id,
                f"❌ Ошибка генерации видео: {error_text}",
                reply_markup=get_inline_menu_markup(),
                parse_mode=None,
            )
        except Exception as send_error:
            print(f"Failed to notify user about video error: {send_error}")
        return
    except Exception as e:
        GenerationService.fail_generation(req, str(e), refund=True)
        send_telegram_message(
            req.chat_id,
            f"❌ Ошибка генерации видео: {str(e)}",
            reply_markup=get_inline_menu_markup(),
        )
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def extend_video_task(self, request_id: int):
    """
    Продлить ранее сгенерированное видео на дополнительный сегмент.
    """
    req = GenRequest.objects.select_related('user', 'ai_model', 'transaction', 'parent_request').get(id=request_id)
    parent = req.parent_request
    if not parent:
        raise VideoGenerationError("Не удалось определить исходный ролик для продления.")

    parent.refresh_from_db()
    if parent.status != "done" or not parent.result_urls:
        raise VideoGenerationError("Исходный ролик ещё не готов для продления.")

    try:
        GenerationService.start_generation(req)

        model = req.ai_model or parent.ai_model
        if not model:
            raise VideoGenerationError("Модель для продления видео недоступна.")

        prompt = req.prompt
        generation_type = 'image2video'

        provider = get_video_provider(model.provider)

        params: Dict[str, Any] = {}
        params.update(model.default_params or {})
        params.update(parent.generation_params or {})
        params.update(req.generation_params or {})
        params.pop("extend_parent_request_id", None)
        params.pop("parent_request_id", None)
        params.pop("input_image_file_id", None)
        params.pop("input_image_mime_type", None)
        params["mode"] = generation_type

        params["duration"] = 8
        if parent.aspect_ratio:
            params["aspect_ratio"] = parent.aspect_ratio
        if parent.video_resolution:
            params["resolution"] = parent.video_resolution

        source_media = req.source_media if isinstance(req.source_media, dict) else {}
        part1_url = source_media.get("parent_result_url") or (parent.result_urls[0] if parent.result_urls else None)
        if not part1_url:
            raise VideoGenerationError("Не найдена ссылка на исходное видео.")

        part1_bytes = fetch_remote_file(part1_url)
        frame_bytes = extract_last_frame(part1_bytes)

        result = provider.generate(
            prompt=prompt,
            model_name=model.api_model_name,
            generation_type=generation_type,
            params=params,
            input_media=frame_bytes,
            input_mime_type="image/png",
        )
        part2_bytes = result.content

        combined_bytes, combined_duration, (width, height) = combine_videos_with_crossfade(part1_bytes, part2_bytes)

        upload_result = supabase_upload_video(combined_bytes, mime_type="video/mp4")
        public_url = upload_result.get("public_url") if isinstance(upload_result, dict) else upload_result

        provider_metadata = dict(result.metadata or {})
        provider_metadata["extension"] = {
            "parent_request_id": parent.id,
            "segment_job_id": result.provider_job_id,
        }

        final_resolution = parent.video_resolution or req.video_resolution or params.get("resolution") or (f"{height}p" if height else None)
        final_aspect_ratio = parent.aspect_ratio or req.aspect_ratio or params.get("aspect_ratio")

        GenerationService.complete_generation(
            req,
            result_urls=[public_url],
            file_sizes=[len(combined_bytes)],
            duration=int(round(combined_duration)),
            video_resolution=final_resolution,
            aspect_ratio=final_aspect_ratio,
            provider_job_id=result.provider_job_id,
            provider_metadata=provider_metadata,
        )

        req.refresh_from_db()
        transaction = req.transaction
        if transaction:
            transaction.refresh_from_db()
            charged_amount = transaction.amount
            balance_after = transaction.balance_after
        else:
            charged_amount = Decimal("0.00")
            balance_after = Decimal("0.00")

        message = get_generation_complete_message(
            prompt=prompt,
            generation_type=generation_type,
            model_name=model.display_name,
            duration=req.duration or int(round(combined_duration)),
            resolution=req.video_resolution or final_resolution,
            aspect_ratio=req.aspect_ratio or final_aspect_ratio,
            model_hashtag=model.hashtag,
            charged_amount=charged_amount,
            balance_after=balance_after,
        )

        send_telegram_video(
            chat_id=req.chat_id,
            video_bytes=combined_bytes,
            caption=message,
            reply_markup=get_video_result_markup(req.id),
        )

    except VideoGenerationError as e:
        GenerationService.fail_generation(req, str(e), refund=True)
        error_text = str(e)
        if len(error_text) > 3500:
            error_text = error_text[:3500] + "…"
        try:
            send_telegram_message(
                req.chat_id,
                f"❌ Ошибка продления видео: {error_text}",
                reply_markup=get_inline_menu_markup(),
                parse_mode=None,
            )
        except Exception:
            pass
        raise
    except Exception as e:
        GenerationService.fail_generation(req, str(e), refund=True)
        send_telegram_message(
            req.chat_id,
            f"❌ Ошибка продления видео: {str(e)}",
            reply_markup=get_inline_menu_markup(),
        )
        raise

@shared_task(bind=True, max_retries=1)
def process_payment_webhook(self, payment_data: Dict):
    """
    Обработка webhook от платежной системы
    """
    from .business.balance import BalanceService

    try:
        # Получаем данные из webhook
        user_id = payment_data.get('user_id')
        amount = Decimal(str(payment_data.get('amount', 0)))
        payment_method = payment_data.get('payment_method')
        transaction_id = payment_data.get('transaction_id')

        # Получаем пользователя
        user = TgUser.objects.get(chat_id=user_id)

        # Создаем транзакцию
        transaction = BalanceService.create_transaction(
            user=user,
            amount=amount,
            transaction_type='deposit',
            payment_method=payment_method,
            payment_id=transaction_id,
            description=f"Пополнение баланса через {payment_method}",
            payment_data=payment_data
        )

        # Подтверждаем транзакцию
        BalanceService.complete_transaction(
            transaction=transaction,
            status='completed'
        )

        # Отправляем уведомление пользователю
        from .keyboards import format_balance
        new_balance = BalanceService.get_balance(user)

        send_telegram_message(
            user.chat_id,
            f"✅ **Платеж успешно обработан!**\n\n"
            f"Зачислено: ⚡ {amount} токенов\n"
            f"Ваш текущий баланс: {format_balance(new_balance)}",
            reply_markup=get_inline_menu_markup()
        )

    except TgUser.DoesNotExist:
        # Пользователь не найден
        pass
    except Exception as e:
        # Логируем ошибку
        raise
