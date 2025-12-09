"""
Celery задачи для асинхронной генерации изображений и видео
"""
import base64
import json
import logging
import os
import subprocess
import tempfile
from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import httpx
from celery import shared_task, signals
from django.conf import settings
from django.db import close_old_connections
from imageio_ffmpeg import get_ffmpeg_exe

from .business.balance import BalanceService
from .business.generation import GenerationService
from .chat_logger import ChatLogger
from .error_tracker import ErrorTracker
from .keyboards import get_generation_complete_message
from .media_utils import detect_reference_mime, ensure_png_format
from .models import BotErrorEvent, GenRequest, TgUser
from .providers import VideoGenerationError, get_video_provider
from .services import generate_images_for_model, supabase_upload_png, supabase_upload_video, GeminiBlockedError

logger = logging.getLogger(__name__)

MAX_TELEGRAM_CAPTION = 1024  # ограничение Telegram на caption для медиа


def _shorten_caption(text: str, limit: int = MAX_TELEGRAM_CAPTION) -> str:
    """Обрезает caption до лимита Telegram."""
    if not text:
        return text
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _log_bot_api_result(result) -> None:
    """Логирует результат Telegram Bot API, корректно обрабатывая списки (media group)."""
    if isinstance(result, list):
        for item in result:
            ChatLogger.log_outgoing_from_payload(item)
    else:
        ChatLogger.log_outgoing_from_payload(result)


def send_telegram_photo(
    chat_id: int,
    photo_bytes: bytes,
    caption: str,
    reply_markup: Optional[Dict] = None,
    parse_mode: Optional[str] = None,
):
    """Отправка изображения файлом (document) в Telegram напрямую."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {"document": ("image.png", photo_bytes, "image/png")}
    data = {
        "chat_id": chat_id,
        "caption": _shorten_caption(caption),
    }
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    with httpx.Client(timeout=30) as client:
        resp = client.post(url, files=files, data=data)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            # Логируем тело ответа, чтобы понимать причину 4xx от Telegram
            logger.warning(
                "Telegram sendDocument failed: status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
            raise
        payload = resp.json()
        _log_bot_api_result(payload.get("result"))
        return payload


def send_telegram_video(chat_id: int, video_bytes: bytes, caption: str, reply_markup: Optional[Dict] = None):
    """Отправка видео строго файлом (document) без авто-детекции контента."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {"document": ("video.mp4", video_bytes, "application/octet-stream")}
    data = {
        "chat_id": chat_id,
        "caption": _shorten_caption(caption),
        "disable_content_type_detection": True,
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    with httpx.Client(timeout=120) as client:
        resp = client.post(url, files=files, data=data)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            logger.warning(
                "Telegram sendDocument failed: status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
            raise
        payload = resp.json()
        _log_bot_api_result(payload.get("result"))
        return payload


def send_telegram_album(
    chat_id: int,
    images: List[Tuple[bytes, Optional[str]]],
) -> dict:
    """
    Отправка нескольких изображений одним альбомом (media group).
    Caption ставится только на первое изображение.
    """
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    files = {}
    media = []

    for idx, (image_bytes, caption) in enumerate(images, start=1):
        file_key = f"photo{idx}"
        files[file_key] = ("image.png", image_bytes, "image/png")
        media_item = {
            "type": "photo",
            "media": f"attach://{file_key}",
        }
        if caption:
            media_item["caption"] = _shorten_caption(caption)
        media.append(media_item)

    with httpx.Client(timeout=60) as client:
        resp = client.post(
            url,
            data={
                "chat_id": chat_id,
                "media": json.dumps(media, ensure_ascii=False),
            },
            files=files,
        )
        resp.raise_for_status()
        payload = resp.json()
        _log_bot_api_result(payload.get("result"))
        return payload


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
        payload = resp.json()
        _log_bot_api_result(payload.get("result"))
        return payload


def get_inline_menu_markup():
    """Разметка reply-клавиатуры главного меню"""
    payment_url = getattr(settings, "PAYMENT_MINI_APP_URL", "https://example.com/payment")
    return {
        "keyboard": [
            [
                {"text": "🎨 Создать изображение"},
                {"text": "🎬 Создать видео"},
            ],
            [
                {"text": "💰 Мой баланс (цены)"},
                {"text": "💳 Пополнить баланс", "web_app": {"url": payment_url}},
            ],
            [{"text": "📲 Промт по референсу"}],
            [{"text": "🏠Главное меню"}],
            [{"text": "🧡 Поддержка"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def get_video_result_markup(request_id: int, include_extension: bool = True) -> Dict[str, Any]:
    """Inline клавиатура для результатов видео."""
    keyboard: List[List[Dict[str, str]]] = []
    if include_extension:
        keyboard.append([{
            "text": "🔁 Продлить FAST",
            "callback_data": f"extend_video:{request_id}",
        }])
    return {"inline_keyboard": keyboard}


def fetch_remote_file(url: str) -> bytes:
    """Скачать файл по URL и вернуть байтовое содержимое."""
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def _download_media_with_mime(url: str) -> Tuple[bytes, str]:
    """Скачать бинарный файл и вернуть пару (контент, mime)."""
    with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
        mime = resp.headers.get("content-type", "video/mp4")
        return resp.content, mime.split(";")[0].strip()




@lru_cache()
def _ffmpeg_bin() -> str:
    return get_ffmpeg_exe()


def _close_db_connections(**kwargs):
    """Закрываем незавершённые соединения с БД перед/после тасков."""
    close_old_connections()


signals.task_prerun.connect(_close_db_connections)
signals.task_postrun.connect(_close_db_connections)


@signals.task_failure.connect
def _log_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, einfo=None, **extra):
    task_name = getattr(sender, "name", str(sender) if sender else "unknown")
    ErrorTracker.log(
        origin=BotErrorEvent.Origin.CELERY,
        severity=BotErrorEvent.Severity.CRITICAL,
        handler=task_name,
        payload={
            "task_id": task_id,
            "args": args,
            "kwargs": kwargs,
        },
        extra={"traceback": str(einfo) if einfo else ""},
        exc=exception,
    )


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


def _probe_media_info(path: str) -> str:
    """Возвращает текстовую информацию о медиафайле из ffmpeg."""
    proc = subprocess.run(
        [_ffmpeg_bin(), "-hide_banner", "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.stderr


def _probe_duration(path: str) -> Optional[float]:
    """Возвращает длительность ролика (в секундах), используя ffmpeg."""
    info = _probe_media_info(path)

    for line in info.splitlines():
        if "Duration:" in line:
            try:
                duration_str = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
                h, m, s = duration_str.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except Exception:
                continue
    return None


def _probe_fps(path: str) -> Optional[float]:
    """Пытается определить FPS ролика из вывода ffmpeg."""
    info = _probe_media_info(path)

    def _parse_rate(token: str) -> Optional[float]:
        token = token.strip()
        if "/" in token:
            num, denom = token.split("/", 1)
            try:
                return float(num) / float(denom)
            except (ValueError, ZeroDivisionError):
                return None
        try:
            return float(token)
        except ValueError:
            return None

    for line in info.splitlines():
        if "Stream #0:0" in line and "Video:" in line:
            parts = [part.strip() for part in line.split(",")]
            for part in parts:
                if part.endswith(" fps"):
                    rate = _parse_rate(part[:-4])
                    if rate:
                        return rate
                if part.endswith(" tbr"):
                    rate = _parse_rate(part[:-4])
                    if rate:
                        return rate
    return None


def _detect_audio(path: str) -> bool:
    proc = subprocess.run(
        [_ffmpeg_bin(), "-hide_banner", "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return "Audio:" in proc.stderr


def extract_last_frame(video_bytes: bytes, duration_hint: Optional[float] = None) -> bytes:
    """Извлекает последний кадр видео (PNG) с помощью ffmpeg."""
    temp_paths: List[str] = []
    try:
        fd_input, input_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd_input)
        with open(input_path, "wb") as fh:
            fh.write(video_bytes)
        temp_paths.append(input_path)

        fd_frame, frame_path = tempfile.mkstemp(suffix=".png")
        os.close(fd_frame)
        temp_paths.append(frame_path)

        attempts: List[List[str]] = []
        if duration_hint and duration_hint > 0.2:
            seek_time = max(duration_hint - 0.1, 0.0)
            attempts.append([
                _ffmpeg_bin(), "-y",
                "-ss", f"{seek_time:.3f}",
                "-i", input_path,
                "-frames:v", "1",
                frame_path,
            ])
        attempts.extend([
            [
                _ffmpeg_bin(), "-y",
                "-sseof", "-0.1",
                "-i", input_path,
                "-frames:v", "1",
                frame_path,
            ],
            [
                _ffmpeg_bin(), "-y",
                "-i", input_path,
                "-vf", "select='gte(n,n_forced-1)'",
                "-frames:v", "1",
                frame_path,
            ],
            [
                _ffmpeg_bin(), "-y",
                "-i", input_path,
                "-frames:v", "1",
                frame_path,
            ],
        ])

        frame_bytes: Optional[bytes] = None
        errors: List[str] = []
        for command in attempts:
            try:
                _run_command(command)
            except RuntimeError as exc:
                errors.append(str(exc))
                continue
            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                with open(frame_path, "rb") as fh_frame:
                    data = fh_frame.read()
                if data:
                    frame_bytes = data
                    break

        if not frame_bytes:
            extra = f" Детали: {' | '.join(errors)}" if errors else ""
            raise RuntimeError("Не удалось извлечь кадр видео." + extra)

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
    duration1: Optional[float],
    duration2: Optional[float],
    fade_duration: float = 1.0,
) -> Tuple[bytes, float]:
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
        with open(path2, "wb") as fh:
            fh.write(part2_bytes)
        temp_paths.append(path2)

        fd_out, output_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd_out)
        temp_paths.append(output_path)

        actual_d1 = duration1 or _probe_duration(path1) or fade_duration
        actual_d2 = duration2 or _probe_duration(path2) or fade_duration

        candidate_fades = [fade_duration]
        if actual_d1:
            candidate_fades.append(actual_d1 / 2)
        if actual_d2:
            candidate_fades.append(actual_d2 / 2)
        raw_fade = min(value for value in candidate_fades if value)
        fade = max(0.1, min(0.5, raw_fade))

        pre_cut = max(actual_d1 - fade, 0.0)

        has_audio1 = _detect_audio(path1)
        has_audio2 = _detect_audio(path2)
        include_audio = has_audio1 and has_audio2

        fps1 = _probe_fps(path1)
        fps2 = _probe_fps(path2)
        target_fps = fps1 or fps2 or 24.0

        def build_command(include_audio_filter: bool) -> List[str]:
            filter_parts: List[str] = [
                f"[0:v]trim=0:{pre_cut:.3f},setpts=PTS-STARTPTS[v0_tmp]",
                f"[1:v]trim=0:{actual_d2:.3f},setpts=PTS-STARTPTS[v1_tmp]",
                f"[v0_tmp]fps=fps={target_fps:.6f}[v0]",
                f"[v1_tmp]fps=fps={target_fps:.6f}[v1]",
                "[v0][v1]concat=n=2:v=1:a=0[vout]",
            ]

            map_args: List[str] = ["-map", "[vout]"]
            audio_args: List[str] = ["-an"]

            if include_audio_filter:
                filter_parts.extend([
                    f"[0:a]atrim=0:{pre_cut:.3f},asetpts=PTS-STARTPTS[a0]",
                    f"[0:a]atrim={pre_cut:.3f}:{actual_d1:.3f},asetpts=PTS-STARTPTS[a1]",
                    f"[1:a]atrim=0:{fade:.3f},asetpts=PTS-STARTPTS[a2]",
                    f"[1:a]atrim={fade:.3f}:{actual_d2:.3f},asetpts=PTS-STARTPTS[a3]",
                    f"[a1][a2]acrossfade=d={fade:.3f}[af]",
                    "[a0][af][a3]concat=n=3:v=0:a=1[aout]",
                ])
                map_args.extend(["-map", "[aout]"])
                audio_args = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100"]

            return [
                _ffmpeg_bin(),
                "-y",
                "-i", path1,
                "-i", path2,
                "-filter_complex", ";".join(filter_parts),
                *map_args,
                "-c:v", "libx264",
                "-threads", "2",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                *audio_args,
                "-movflags", "+faststart",
                output_path,
            ]

        command_errors: List[str] = []
        if include_audio:
            try:
                _run_command(build_command(include_audio_filter=True))
            except RuntimeError as exc:
                command_errors.append(str(exc))
                include_audio = False

        if not include_audio:
            try:
                _run_command(build_command(include_audio_filter=False))
            except RuntimeError as exc:
                if command_errors:
                    command_errors.append(str(exc))
                    raise RuntimeError(" ".join(command_errors)) from exc
                raise

        with open(output_path, "rb") as fh_out:
            combined_bytes = fh_out.read()

        final_duration = actual_d1 + actual_d2 - fade

        return combined_bytes, final_duration
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
        file_bytes = file_resp.content
        header_mime = file_resp.headers.get("Content-Type", "application/octet-stream")
        mime_type = detect_reference_mime(file_bytes, file_path, header_mime)
        return file_bytes, mime_type


def _prepare_input_images(sources: List[Any], limit: Optional[int]) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    if not sources:
        return payloads
    max_items = limit or len(sources)
    for idx, entry in enumerate(sources):
        if len(payloads) >= max_items:
            break
        file_id: Optional[str] = None
        role: Optional[str] = None
        mime_type: Optional[str] = None
        filename = f"input_{idx}.png"
        base64_data: Optional[str] = None
        storage_url: Optional[str] = None
        content: Optional[bytes] = None

        if isinstance(entry, dict):
            file_id = entry.get("telegram_file_id") or entry.get("file_id")
            role = entry.get("type") or entry.get("role")
            mime_type = entry.get("mime_type") or entry.get("mime")
            filename = entry.get("filename") or entry.get("file_name") or entry.get("name") or filename
            base64_data = entry.get("content_base64") or entry.get("base64") or entry.get("data")
            storage_url = entry.get("storage_url") or entry.get("url")
        elif isinstance(entry, str):
            file_id = entry

        if file_id:
            image_bytes, mime_type_raw = download_telegram_file(file_id)
            mime_type = mime_type or mime_type_raw
            content = image_bytes
        elif base64_data:
            try:
                data_str = base64_data.split(",")[-1] if "," in base64_data else base64_data
                content = base64.b64decode(data_str)
            except Exception:
                content = None
        elif storage_url:
            try:
                content = fetch_remote_file(storage_url)
            except Exception:
                content = None

        if content is None:
            continue

        png_bytes, png_mime = ensure_png_format(content, mime_type or "image/png")
        payloads.append(
            {
                "content": png_bytes,
                "mime_type": png_mime,
                "filename": filename,
                "role": role,
            }
        )
    return payloads


def _extract_charge_details(req: GenRequest) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Возвращает списанную сумму и баланс после операции для указанного запроса.
    """
    charged_amount: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None

    transaction = getattr(req, "transaction", None)
    if transaction:
        transaction.refresh_from_db()
        charged_amount = abs(transaction.amount)
        balance_after = transaction.balance_after

    if charged_amount is None:
        cost = getattr(req, "cost", None)
        if cost is not None:
            charged_amount = abs(Decimal(cost))

    if balance_after is None:
        try:
            balance = BalanceService.ensure_balance(req.user)
            balance_after = balance.balance
        except Exception:
            balance_after = None

    if charged_amount is None:
        charged_amount = Decimal("0.00")
    if balance_after is None:
        balance_after = Decimal("0.00")

    return charged_amount, balance_after


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_image_task(self, request_id: int):
    """
    Задача генерации изображений
    """
    logger.info(f"[CELERY_IMAGE_TASK] Начало выполнения задачи генерации изображения: request_id={request_id}")

    req: Optional[GenRequest] = None
    try:
        req = GenRequest.objects.select_related('user', 'ai_model', 'transaction').get(id=request_id)
        logger.info(f"[CELERY_IMAGE_TASK] Запрос загружен: user={req.user.chat_id}, model={req.ai_model.name}, provider={req.ai_model.provider}")

        # Получаем модель и параметры
        model = req.ai_model
        prompt = req.prompt
        quantity = req.quantity or 1
        generation_type = req.generation_type or 'text2image'

        params = dict(model.default_params or {})
        params.update(req.generation_params or {})
        image_mode = params.get("image_mode")

        input_images_payload: List[Dict[str, Any]] = []
        if generation_type == 'image2image':
            input_sources = req.input_images or []
            max_inputs = model.max_input_images or None
            # Для ремикса отдаем все разрешенные моделью референсы (документация Gemini допускает до 14 для Pro).
            if image_mode == "remix":
                if max_inputs:
                    max_inputs = min(len(input_sources), max_inputs)
                else:
                    max_inputs = len(input_sources) or None
            logger.info(
                f"[TASK] Подготовка изображений для запроса {req.id}: input_sources={len(input_sources)}, "
                f"max_inputs={max_inputs}, model.max_input_images={model.max_input_images}, mode={image_mode}"
            )
            input_images_payload = _prepare_input_images(input_sources, max_inputs)
            logger.info(f"[TASK] Подготовлено {len(input_images_payload)} изображений для передачи в модель")

            if not input_images_payload:
                generation_type = 'text2image'
        if generation_type != 'image2image':
            input_images_payload = []

        # Вызываем сервис генерации изображений
        try:
            imgs = generate_images_for_model(
                model,
                prompt,
                quantity,
                params,
                generation_type=generation_type,
                input_images=input_images_payload,
                image_mode=image_mode,
            )
        except GeminiBlockedError as blocked_err:
            # Gemini заблокировал запрос - retry бесполезен, сразу сообщаем пользователю
            logger.error(f"[TASK] Gemini заблокировал запрос {req.id}: {blocked_err}")
            req.status = "error"
            req.error_message = str(blocked_err)
            req.save(update_fields=["status", "error_message"])

            send_telegram_message(
                req.chat_id,
                f"❌ {blocked_err}",
                reply_markup=get_inline_menu_markup(),
                parse_mode=None,
            )
            return  # Выходим без retry

        # Проверка что генерация вернула результаты
        if not imgs:
            error_msg = f"Генерация не вернула изображений. Model: {model.display_name}, Type: {generation_type}, Mode: {image_mode}"
            logger.error(f"[TASK] {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"[TASK] Успешно сгенерировано {len(imgs)} изображений для запроса {req.id}")

        # Проверка что генерация вернула результаты
        if not imgs:
            error_msg = f"Генерация не вернула изображений. Model: {model.display_name}, Type: {generation_type}, Mode: {image_mode}"
            logger.error(f"[TASK] {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"[TASK] Успешно сгенерировано {len(imgs)} изображений для запроса {req.id}")

        urls = []
        inline_markup = get_inline_menu_markup()
        charged_amount, balance_after = _extract_charge_details(req)
        system_message = get_generation_complete_message(
            prompt=prompt,
            generation_type=generation_type,
            model_name=model.display_name,
            model_display_name=model.display_name,
            quantity=quantity,
            aspect_ratio=req.aspect_ratio or "1:1",
            generation_params=req.generation_params or {},
            model_provider=model.provider,
            image_mode=(req.generation_params or {}).get("image_mode"),
            charged_amount=charged_amount,
            balance_after=balance_after,
        )

        # Загружаем изображения в Storage и формируем список для отправки одним альбомом
        prepared_images: List[Tuple[bytes, Optional[str]]] = []
        for idx, img in enumerate(imgs, start=1):
            try:
                logger.info(f"[TASK] Загрузка изображения {idx}/{quantity} в Supabase для запроса {req.id}")
                url_obj = supabase_upload_png(img)
                url = url_obj.get("public_url") if isinstance(url_obj, dict) else url_obj
                urls.append(url)
                logger.info(f"[TASK] Изображение {idx}/{quantity} загружено: {url}")
                caption = None
                # caption добавляем только к первому изображению
                prepared_images.append((img, caption))
                logger.info(f"[TASK] Изображение {idx}/{quantity} подготовлено к отправке")
            except Exception as img_error:
                logger.exception(f"[TASK] Ошибка при обработке изображения {idx}/{quantity} для запроса {req.id}: {img_error}")
                # Продолжаем обработку остальных изображений
                continue

        # Проверка что хотя бы одно изображение было успешно обработано
        if not urls or not prepared_images:
            error_msg = f"Ни одно изображение не было успешно загружено или отправлено для запроса {req.id}"
            logger.error(f"[TASK] {error_msg}")
            raise ValueError(error_msg)

        delivered_count = len(prepared_images)
        if delivered_count > 0:
            caption_text = f"{system_message}\n\n📷 Изображения 1-{delivered_count}"
            prepared_images[0] = (prepared_images[0][0], caption_text)

        # Отправляем результаты одним сообщением (media group) если изображений несколько
        try:
            if len(prepared_images) == 1:
                img, caption = prepared_images[0]
                send_telegram_photo(
                    chat_id=req.chat_id,
                    photo_bytes=img,
                    caption=caption or system_message,
                    reply_markup=inline_markup,
                )
            else:
                send_telegram_album(
                    chat_id=req.chat_id,
                    images=prepared_images,
                )
                # Отдельно отправляем меню, так как sendMediaGroup не поддерживает inline клавиатуру
                send_telegram_message(
                    req.chat_id,
                    "Готово! Выберите действие:",
                    reply_markup=inline_markup,
                    parse_mode=None,
                )
            logger.info(f"[TASK] Запрос {req.id} завершен успешно. Загружено и отправлено {len(prepared_images)}/{quantity} изображений")
        except Exception as send_error:
            logger.exception(f"[TASK] Ошибка при отправке результатов запроса {req.id}: {send_error}")
            raise

        # Обновляем статус запроса
        req.status = "done"
        req.result_urls = urls
        req.save(update_fields=["status", "result_urls"])

    except Exception as e:
        max_retries = getattr(self, "max_retries", 0) or 0
        current_retry = getattr(getattr(self, "request", None), "retries", 0)
        is_final_attempt = current_retry >= max_retries

        if req is None:
            raise

        if is_final_attempt:
            req.status = "error"
            req.error_message = str(e)
            req.save(update_fields=["status", "error_message"])

            send_telegram_message(
                req.chat_id,
                f"❌ Ошибка генерации изображения: {str(e)}",
                reply_markup=get_inline_menu_markup(),
                parse_mode=None,
            )
        else:
            req.status = "processing"
            req.save(update_fields=["status"])

        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_video_task(self, request_id: int):
    """
    Задача генерации видео через провайдеров (Vertex Veo и др.)
    """
    req: Optional[GenRequest] = None
    try:
        req = GenRequest.objects.select_related('user', 'ai_model', 'transaction').get(id=request_id)
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
        last_frame_media: Optional[bytes] = None
        last_frame_mime: Optional[str] = None

        source_media = req.source_media if isinstance(req.source_media, dict) else {}
        telegram_file_id = params.get("input_image_file_id") or source_media.get("telegram_file_id")

        media_to_video = generation_type in {"image2video", "video2video"}
        default_media_mime = "video/mp4" if generation_type == "video2video" else "image/png"

        inline_entry: Optional[Dict[str, Any]] = None
        if media_to_video:
            for entry in req.input_images or []:
                if not isinstance(entry, dict):
                    continue
                raw_b64 = entry.get("content_base64") or entry.get("base64") or entry.get("data")
                if raw_b64:
                    inline_entry = entry
                    break

        if media_to_video and inline_entry:
            raw_b64 = inline_entry.get("content_base64") or inline_entry.get("base64") or inline_entry.get("data")
            try:
                input_media = base64.b64decode(raw_b64)
            except Exception as exc:
                raise VideoGenerationError("Не удалось прочитать входные данные из WebApp.") from exc
            input_mime_type = (
                inline_entry.get("mime_type")
                or inline_entry.get("mime")
                or inline_entry.get("content_type")
                or default_media_mime
            )
        elif media_to_video and telegram_file_id:
            input_media, input_mime_type = download_telegram_file(telegram_file_id)
            preferred_mime = (
                params.get("input_image_mime_type")
                or params.get("input_video_mime_type")
                or source_media.get("mime_type")
            )
            if preferred_mime:
                input_mime_type = preferred_mime
        elif media_to_video:
            storage_url = (
                source_media.get("storage_url")
                or params.get("image_url")
                or params.get("video_url")
            )
            base64_data = (
                source_media.get("base64")
                or params.get("image_base64")
                or params.get("video_base64")
            )
            if storage_url:
                try:
                    input_media = fetch_remote_file(storage_url)
                    input_mime_type = (
                        source_media.get("mime_type")
                        or params.get("input_image_mime_type")
                        or params.get("input_video_mime_type")
                        or default_media_mime
                    )
                except Exception as exc:
                    logger.warning("Failed to fetch image from storage_url=%s: %s", storage_url, exc, exc_info=exc)
            elif base64_data:
                try:
                    input_media = base64.b64decode(base64_data)
                    input_mime_type = (
                        source_media.get("mime_type")
                        or params.get("input_image_mime_type")
                        or params.get("input_video_mime_type")
                        or default_media_mime
                    )
                except Exception as exc:
                    logger.warning("Failed to decode base64 image for video generation: %s", exc, exc_info=exc)

        final_frame_data = params.pop("final_frame", None)
        if final_frame_data and isinstance(final_frame_data, dict):
            raw_b64 = (
                final_frame_data.get("content_base64")
                or final_frame_data.get("base64")
                or final_frame_data.get("data")
            )
            if raw_b64:
                try:
                    last_frame_media = base64.b64decode(raw_b64)
                except Exception as exc:
                    raise VideoGenerationError("Не удалось прочитать конечный кадр из WebApp.") from exc
                if len(last_frame_media) > 5 * 1024 * 1024:
                    raise VideoGenerationError("Конечный кадр превышает 5 МБ.")
                last_frame_mime = (
                    final_frame_data.get("mime_type")
                    or final_frame_data.get("mime")
                    or final_frame_data.get("content_type")
                    or "image/png"
                )

        generate_kwargs: Dict[str, Any] = {
            "prompt": prompt,
            "model_name": model.api_model_name,
            "generation_type": generation_type,
            "params": params,
            "input_media": input_media,
            "input_mime_type": input_mime_type,
        }
        # Не все провайдеры поддерживают last_frame_* (например, Kling).
        if last_frame_media is not None and getattr(provider, "slug", "") != "kling":
            generate_kwargs["last_frame_media"] = last_frame_media
            generate_kwargs["last_frame_mime_type"] = last_frame_mime

        result = provider.generate(**generate_kwargs)

        if result.content is None:
            updates = []
            if result.provider_job_id:
                req.provider_job_id = result.provider_job_id
                updates.append("provider_job_id")
            if result.metadata:
                req.provider_metadata = result.metadata
                updates.append("provider_metadata")
            if updates:
                req.save(update_fields=updates)
            logger.info(
                "[VIDEO_TASK] Geminigen поставил задачу в очередь: request_id=%s job_id=%s",
                req.id,
                result.provider_job_id,
            )
            return

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

        charged_amount, balance_after = _extract_charge_details(req)

        message = get_generation_complete_message(
            prompt=prompt,
            generation_type=generation_type,
            model_name=model.display_name,
            model_display_name=model.display_name,
            generation_params=req.generation_params or {},
            model_provider=model.provider,
            duration=req.duration or result.duration,
            resolution=req.video_resolution or result.resolution,
            aspect_ratio=req.aspect_ratio or result.aspect_ratio,
            charged_amount=charged_amount,
            balance_after=balance_after,
        )

        allow_extension = bool(getattr(provider, "supports_extension", model.provider == "veo"))

        try:
            send_telegram_video(
                chat_id=req.chat_id,
                video_bytes=result.content,
                caption=message,
                reply_markup=get_video_result_markup(req.id, include_extension=allow_extension),
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response else "unknown"
            body = e.response.text if e.response else str(e)
            logger.warning("Telegram sendDocument failed: status=%s body=%s", status, body[:500], exc_info=e)
            fallback_text = (
                "Видео готово, но Telegram вернул ошибку при отправке файла. "
                f"Ссылка для скачивания: {public_url}"
            )
            send_telegram_message(
                req.chat_id,
                fallback_text,
                reply_markup=get_video_result_markup(req.id, include_extension=allow_extension),
                parse_mode=None,
            )
        except Exception as e:
            logger.exception("Unexpected error while sending video to Telegram")
            fallback_text = (
                "Видео готово, но не удалось отправить его файлом. "
                f"Ссылка для скачивания: {public_url}"
            )
            send_telegram_message(
                req.chat_id,
                fallback_text,
                reply_markup=get_video_result_markup(req.id, include_extension=allow_extension),
                parse_mode=None,
            )
            raise e

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
            logger.exception("Failed to notify user about video error: %s", send_error)
            ErrorTracker.log(
                origin=BotErrorEvent.Origin.CELERY,
                severity=BotErrorEvent.Severity.WARNING,
                handler="send_video_failure_notification",
                chat_id=req.chat_id,
                gen_request=req,
                payload={"request_id": req.id},
                exc=send_error,
            )
        return
    except Exception as e:
        if req:
            GenerationService.fail_generation(req, str(e), refund=True)
            send_telegram_message(
                req.chat_id,
                f"❌ Ошибка генерации видео: {str(e)}",
                reply_markup=get_inline_menu_markup(),
                parse_mode=None,
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
        if model.provider != "veo":
            raise VideoGenerationError("Продление доступно только для видео, созданных моделью Veo.")

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
        frame_bytes = extract_last_frame(part1_bytes, parent.duration)

        result = provider.generate(
            prompt=prompt,
            model_name=model.api_model_name,
            generation_type=generation_type,
            params=params,
            input_media=frame_bytes,
            input_mime_type="image/png",
        )
        if result.content is None:
            raise VideoGenerationError(
                "Продление для Geminigen пока недоступно: провайдер вернул задачу без готового видео."
            )
        part2_bytes = result.content

        combined_bytes, combined_duration = combine_videos_with_crossfade(
            part1_bytes,
            part2_bytes,
            parent.duration,
            result.duration or params.get("duration"),
        )

        upload_result = supabase_upload_video(combined_bytes, mime_type="video/mp4")
        public_url = upload_result.get("public_url") if isinstance(upload_result, dict) else upload_result

        provider_metadata = dict(result.metadata or {})
        provider_metadata["extension"] = {
            "parent_request_id": parent.id,
            "segment_job_id": result.provider_job_id,
        }

        final_resolution = parent.video_resolution or req.video_resolution or params.get("resolution")
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
        charged_amount, balance_after = _extract_charge_details(req)

        message = get_generation_complete_message(
            prompt=prompt,
            generation_type=generation_type,
            model_name=model.display_name,
            model_display_name=model.display_name,
            generation_params=req.generation_params or {},
            model_provider=model.provider,
            duration=req.duration or int(round(combined_duration)),
            resolution=req.video_resolution or final_resolution,
            aspect_ratio=req.aspect_ratio or final_aspect_ratio,
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



@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_geminigen_webhook(self, payload: Dict[str, Any]):
    """
    Обработка вебхуков Geminigen для видео (VIDEO_GENERATION_COMPLETED / FAILED).
    """
    event = (payload.get("event") or payload.get("type") or "").strip()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    job_uuid = data.get("uuid") or payload.get("uuid") or payload.get("job_id")
    status = data.get("status") or payload.get("status")
    media_url = data.get("media_url") or data.get("mediaUrl")
    thumbnail_url = data.get("thumbnail_url") or data.get("thumbnailUrl")
    error_message = (
        data.get("error_message")
        or data.get("errorMessage")
        or (payload.get("detail") or {}).get("message")
        or payload.get("error_message")
    )

    if not job_uuid:
        logger.warning("[GEMINIGEN_WEBHOOK] Пропущено событие без uuid: %s", payload)
        return

    try:
        req = GenRequest.objects.select_related('user', 'ai_model', 'transaction').get(provider_job_id=str(job_uuid))
    except GenRequest.DoesNotExist:
        logger.warning("[GEMINIGEN_WEBHOOK] Запрос с uuid=%s не найден.", job_uuid)
        return

    if req.status == "done":
        logger.info("[GEMINIGEN_WEBHOOK] Запрос уже завершён, uuid=%s", job_uuid)
        return
    if req.status == "error":
        logger.warning("[GEMINIGEN_WEBHOOK] Запрос уже в статусе error, uuid=%s", job_uuid)
        return

    model = req.ai_model
    normalized_event = event.upper()
    normalized_status = str(status).lower() if status is not None else ""
    success_events = {"VIDEO_GENERATION_COMPLETED", "VIDEO.GENERATED", "VIDEO_GENERATED", "VIDEO.GENERATION.COMPLETED"}
    fail_events = {"VIDEO_GENERATION_FAILED", "VIDEO.GENERATION.FAILED", "VIDEO_FAILED"}

    def _merge_metadata() -> Dict[str, Any]:
        meta = req.provider_metadata or {}
        meta = dict(meta)
        meta["webhook"] = payload
        if thumbnail_url:
            meta["thumbnail_url"] = thumbnail_url
        return meta

    if normalized_event in success_events or normalized_status in {"2", "completed", "success"} or media_url:
        if not media_url:
            GenerationService.fail_generation(
                req,
                "Geminigen сообщил об успехе, но не прислал media_url.",
                refund=True,
            )
            send_telegram_message(
                req.chat_id,
                "❌ Видео не получено: нет ссылки media_url в ответе Geminigen.",
                reply_markup=get_inline_menu_markup(),
                parse_mode=None,
            )
            return

        try:
            video_bytes, mime_type = _download_media_with_mime(str(media_url))
        except Exception as exc:
            GenerationService.fail_generation(
                req,
                f"Не удалось скачать видео по ссылке Geminigen: {exc}",
                refund=True,
            )
            send_telegram_message(
                req.chat_id,
                "❌ Не удалось скачать видео по ссылке Geminigen. Попробуйте ещё раз позже.",
                reply_markup=get_inline_menu_markup(),
                parse_mode=None,
            )
            return

        upload_result = supabase_upload_video(video_bytes, mime_type=mime_type or "video/mp4")
        public_url = upload_result.get("public_url") if isinstance(upload_result, dict) else upload_result

        GenerationService.complete_generation(
            req,
            result_urls=[public_url],
            file_sizes=[len(video_bytes)],
            duration=req.duration,
            video_resolution=req.video_resolution,
            aspect_ratio=req.aspect_ratio,
            provider_job_id=str(job_uuid),
            provider_metadata=_merge_metadata(),
        )

        charged_amount, balance_after = _extract_charge_details(req)
        message = get_generation_complete_message(
            prompt=req.prompt,
            generation_type=req.generation_type,
            model_name=model.display_name if model else req.model,
            model_display_name=model.display_name if model else req.model,
            generation_params=req.generation_params or {},
            model_provider=model.provider if model else "veo",
            duration=req.duration,
            resolution=req.video_resolution,
            aspect_ratio=req.aspect_ratio,
            charged_amount=charged_amount,
            balance_after=balance_after,
        )

        allow_extension = False  # Geminigen пока без синхронного продления

        try:
            send_telegram_video(
                chat_id=req.chat_id,
                video_bytes=video_bytes,
                caption=message,
                reply_markup=get_video_result_markup(req.id, include_extension=allow_extension),
            )
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else "unknown"
            body = e.response.text if e.response else str(e)
            logger.warning("Telegram sendDocument failed: status=%s body=%s", status_code, body[:500], exc_info=e)
            fallback_text = (
                "Видео готово, но Telegram вернул ошибку при отправке файла. "
                f"Ссылка для скачивания: {public_url}"
            )
            send_telegram_message(
                req.chat_id,
                fallback_text,
                reply_markup=get_video_result_markup(req.id, include_extension=allow_extension),
                parse_mode=None,
            )
        except Exception as exc:
            logger.exception("Unexpected error while sending Geminigen video to Telegram: %s", exc)
            fallback_text = (
                "Видео готово, но не удалось отправить его файлом. "
                f"Ссылка для скачивания: {public_url}"
            )
            send_telegram_message(
                req.chat_id,
                fallback_text,
                reply_markup=get_video_result_markup(req.id, include_extension=allow_extension),
                parse_mode=None,
            )
            raise

        return

    if normalized_event in fail_events or normalized_status in {"3", "failed", "error"}:
        GenerationService.fail_generation(req, error_message or "Geminigen сообщил об ошибке", refund=True)
        send_telegram_message(
            req.chat_id,
            f"❌ Ошибка генерации видео: {error_message or 'Geminigen сообщил об ошибке'}",
            reply_markup=get_inline_menu_markup(),
            parse_mode=None,
        )
        return

    logger.info("[GEMINIGEN_WEBHOOK] Событие проигнорировано: event=%s status=%s uuid=%s", event, status, job_uuid)

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
    except Exception:
        # Логируем ошибку
        raise
