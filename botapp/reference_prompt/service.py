"""Сервисы для построения JSON-промта по пользовательскому референсу."""

from __future__ import annotations

import base64
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from aiogram import Bot
import httpx
from django.conf import settings

from botapp.services import GEMINI_URL_TMPL
from .downloader import download_video, is_supported_url
from .models import ReferencePromptModel, get_reference_prompt_model


@dataclass
class ReferenceInputPayload:
    """Метаданные по референсу, собранные из сообщения пользователя."""

    input_type: str
    text: Optional[str] = None
    urls: Optional[List[str]] = None
    caption: Optional[str] = None
    file_id: Optional[str] = None
    file_unique_id: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    source_description: Optional[str] = None

    @classmethod
    def from_state(cls, data: Dict[str, Any]) -> "ReferenceInputPayload":
        return cls(**data)

    def as_state(self) -> Dict[str, Any]:
        return {
            "input_type": self.input_type,
            "text": self.text,
            "urls": self.urls,
            "caption": self.caption,
            "file_id": self.file_id,
            "file_unique_id": self.file_unique_id,
            "file_name": self.file_name,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "source_description": self.source_description,
        }


@dataclass
class ReferencePromptResult:
    """Результат сборки JSON-промта."""

    prompt_text: str
    parameters: Dict[str, Any]
    vertex_request: Dict[str, Any]
    blueprint: Dict[str, Any]
    pretty_json: str
    dialogue_code: str
    chunks: List[str]


logger = logging.getLogger(__name__)


class ReferencePromptService:
    """Сервис генерации промта по референсу (укороченный текстовый вывод)."""

    ARCHIVED_SYSTEM_PROMPT_JSON = (
        "You are a senior VEO3 prompt engineer & creative director.\n\n"
        "GOAL\nFrom idea/context (text, transcript, or image caption), produce ONE VEO3-JSON-1.0 blueprint. "
        "Do NOT output API request here; return only the blueprint.\n\n"
        "Return EXACTLY ONE JSON object with TWO keys:\n"
        "{\n"
        "  \"veo3_blueprint\": { ...see BLUEPRINT SCHEMA... },\n"
        "  \"vertex_request\": {\n"
        "    \"instances\": [{ \"prompt\": \"<single compact paragraph ≤1200 chars>\" }],\n"
        "    \"parameters\": {\n"
        "      \"aspectRatio\": \"16:9\" | \"9:16\",\n"
        "      \"compressionQuality\": \"optimized\" | \"lossless\",\n"
        "      \"durationSeconds\": 4 | 6 | 8,\n"
        "      \"generateAudio\": true | false,\n"
        "      \"negativePrompt\": \"<comma-separated negatives>\",\n"
        "      \"personGeneration\": \"allow_adult\" | \"disallow\",\n"
        "      \"resolution\": \"720p\" | \"1080p\",\n"
        "      \"sampleCount\": 1,\n"
        "      \"seed\": <uint32>,\n"
        "      \"storageUri\": \"<gs://bucket/prefix/>\"  // omit if unknown\n"
        "    }\n"
        "  }\n"
        "}\n\n"
        "PROMPT RULE (instances[0].prompt)\n"
        "- ONE paragraph ≤1200 chars.\n"
        "- Start with subject+environment; then camera movement; lighting/color; pacing/editing; key actions.\n"
        "- If speech exists, include short quoted lines in the detected speech language; otherwise omit.\n"
        "- No JSON, no meta, no brand names.\n\n"
        "LANGUAGE POLICY\n"
        "- Control directives in concise English.\n"
        "- Keep spoken lines (dialogue/VO) in the source speech language unless user explicitly asked otherwise.\n\n"
        "NEGATIVES\n"
        "- Always include: \"text overlay, watermark, logo, blurry\".\n"
        "- If user requires on-screen captions, remove \"text overlay\" from negatives.\n\n"
        "MAPPING TO VERTEX (must be valid per Vertex AI Veo docs)\n"
        "- aspectRatio ∈ {\"16:9\",\"9:16\"}.\n"
        "- durationSeconds ∈ {4,6,8} (pick closest to source).\n"
        "- resolution ∈ {\"720p\",\"1080p\"}.\n"
        "- personGeneration ∈ {\"allow_adult\",\"disallow\"} (use \"allow_adult\" unless user forbids faces).\n"
        "- generateAudio: true if source has sound or user expects audio; else false.\n"
        "- sampleCount = 1; compressionQuality = \"optimized\" unless user asks otherwise.\n\n"
        "BLUEPRINT SCHEMA (VEO3-JSON-1.0)\n"
        "{\n"
        "  \"version\":\"VEO3-JSON-1.0\",\n"
        "  \"video_spec\":{\"aspect_ratio\":\"9:16\"|\"16:9\"|\"1:1\",\"resolution\":\"1080x1920\"|\"1920x1080\"|\"1080x1080\",\"fps\":24|25|30,\"duration_sec\":4|6|8},\n"
        "  \"render\":{\"model\":\"veo3_fast\",\"seed\":<int>,\"cfg_scale\":4..12},\n"
        "  \"audio\":{\"music\":{\"mood_en\":\"<=60\",\"tempo_bpm\":60..180|null},\"voiceover_en\":\"<=240|optional\",\"sfx_en\":[\"<0..5>\"]},\n"
        "  \"shots\":[{\"id\":\"s1\",\"duration_sec\":1..6,\"prompt_en\":\"<=180\",\"negative_en\":\"<=120\",\"camera\":{\"framing_en\":\"close-up|medium|wide\",\"lens_en\":\"35mm|50mm|85mm|...\",\"movement_en\":\"static|pan|tilt|dolly|handheld\"},\"subjects_en\":[\"<1..4>\"],\"environment_en\":\"<=120\",\"lighting_en\":\"<=80\",\"style\":{\"look_en\":\"<=80\",\"color_en\":\"<=80\",\"grade_en\":\"<=80\"},\"transition_out\":\"cut|fade|whip\"}],\n"
        "  \"safety\":{\"nsfw\":false,\"copyrighted\":false,\"brand_sensitive\":false},\n"
        "  \"constraints\":{\"no_text_overlay\":true,\"avoid_watermarks\":true,\"avoid_text_logos\":true},\n"
        "  \"meta\":{\"blueprint_ref\":\"VIDEO_BLUEPRINT-1.0\",\"mods_applied_en\":\"<=200\",\"transcript_excerpt_en\":\"<=200|optional\"}\n"
        "}\n\n"
        "OUTPUT\nReturn exactly one valid JSON object with both keys and nothing else."
    )

    SYSTEM_PROMPT = (
        "You are an expert prompt writer for general video generation models (Sora, Veo, Kling, Runway, OpenAI, etc.).\n"
        "Given a reference (link/photo/video) and optional user edits, produce ONE concise English prompt that will recreate the reference as closely as possible.\n"
        "- Output plain text only, no JSON, no code fences, no meta-comments.\n"
        "- Keep it under ~800 characters.\n"
        "- Include subject, environment, camera feel/movement, lighting, mood/color, pacing/editing, notable actions, and framing.\n"
        "- Do not include platform-specific parameters or negative prompts.\n"
        "- If audio/speech is implied, briefly suggest it in English; otherwise omit.\n"
        "- Respect user edits if provided; otherwise infer from the reference.\n"
    )

    MAX_INLINE_BYTES = 14 * 1024 * 1024  # 14 MB ограничение для Gemini inline_data

    def __init__(self, *, model: Optional[ReferencePromptModel] = None) -> None:
        self._default_model = model

    async def generate_prompt(
        self,
        *,
        bot: Bot,
        model_slug: str,
        reference: ReferenceInputPayload,
        modifications: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> ReferencePromptResult:
        """Формирует текстовый промт на основе входных данных пользователя."""

        model = self._default_model or get_reference_prompt_model(model_slug)

        media_bytes: Optional[bytes] = None

        source_url: Optional[str] = None
        if reference.urls:
            source_url = next((u for u in reference.urls if is_supported_url(u)), None)

        if source_url:
            reference.source_url = reference.source_url or source_url
            try:
                download_result = await download_video(source_url)
            except Exception as exc:  # noqa: BLE001 - обернули внешний загрузчик
                logger.exception("Failed to download reference media from %s: %s", source_url, exc)
                raise ValueError(
                    "Не удалось скачать видео по ссылке. Отправьте файл напрямую или попробуйте другую ссылку."
                ) from exc

            media_bytes = download_result.content
            reference.input_type = "video"
            reference.mime_type = download_result.mime_type
            reference.file_size = len(download_result.content)
            reference.duration = download_result.duration or reference.duration
            reference.width = download_result.width or reference.width
            reference.height = download_result.height or reference.height
            reference.source_title = reference.source_title or download_result.title
            reference.source_description = reference.source_description or download_result.description

            if download_result.title and (
                not reference.text or reference.text.strip() in {"", source_url.strip()}
            ):
                reference.text = download_result.title

            if download_result.description and (
                not reference.caption or reference.caption.strip() in {"", source_url.strip()}
            ):
                reference.caption = download_result.description

            if len(media_bytes) > self.MAX_INLINE_BYTES:
                size_mb = len(media_bytes) / (1024 * 1024)
                raise ValueError(
                    f"Скачанное видео весит {size_mb:.1f} MB — это больше лимита 14 MB."
                )

        if media_bytes is None and reference.file_id and reference.input_type in {"photo", "video"}:
            media_bytes = await self._download_file(bot, reference.file_id)
            reference.file_size = len(media_bytes)
            if len(media_bytes) > self.MAX_INLINE_BYTES:
                size_mb = len(media_bytes) / (1024 * 1024)
                raise ValueError(
                    f"Размер файла ({size_mb:.1f} MB) превышает допустимый предел для анализа."
                )

        if media_bytes is None and source_url:
            raise ValueError(
                "Не удалось обработать ссылку. Загрузите видео или изображение напрямую."
            )

        prompt_text = self._build_user_prompt(reference, modifications)
        parts = [{"text": prompt_text}]

        if media_bytes and reference.mime_type:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": reference.mime_type,
                        "data": base64.b64encode(media_bytes).decode("utf-8"),
                    }
                }
            )

        payload = {
            "systemInstruction": {
                "role": "user",
                "parts": [{"text": self.SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": parts,
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "topP": 0.9,
                "responseMimeType": "text/plain",
            },
        }

        response_json = await self._call_gemini(model.gemini_model, payload)
        prompt_out = self._extract_text_response(response_json)
        dialogue_code = uuid.uuid4().hex[:12]

        chunks = [f"✅Ваш промт готов:\n{prompt_out}"]

        return ReferencePromptResult(
            prompt_text=prompt_out,
            parameters={},
            vertex_request={},
            blueprint={},
            pretty_json=prompt_out,
            dialogue_code=dialogue_code,
            chunks=chunks,
        )
    async def _download_file(self, bot: Bot, file_id: str) -> bytes:
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise ValueError("Не удалось получить путь к файлу Telegram")

        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN не задан в настройках")

        url = f"https://api.telegram.org/file/bot{token}/{file.file_path}"

        timeout = httpx.Timeout(120.0, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    def _build_user_prompt(self, reference: ReferenceInputPayload, modifications: Optional[str]) -> str:
        ctx_lines: List[str] = []

        idea_text = (reference.text or reference.caption or "").strip()
        if not idea_text and reference.source_title:
            idea_text = reference.source_title
        if not idea_text and reference.source_description:
            idea_text = reference.source_description[:400]

        if idea_text:
            ctx_lines.append(f"Reference summary: {idea_text}")

        if reference.input_type:
            ctx_lines.append(f"Reference type: {reference.input_type}")
        if reference.urls:
            ctx_lines.append(f"Source link: {reference.urls[0]}")
        if reference.duration:
            ctx_lines.append(f"Duration (if video): {reference.duration} seconds")
        if reference.width and reference.height:
            ctx_lines.append(f"Resolution (if known): {reference.width}x{reference.height}")
        if modifications:
            ctx_lines.append(f"User edits: {modifications}")

        if not ctx_lines:
            ctx_lines.append("No additional context provided; infer from attached media.")

        return "\n".join(ctx_lines)

    async def _call_gemini(self, model_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY не задан")

        # API ожидает путь вида models/<model-name>. Чтобы избежать двойного префикса,
        # нормализуем входное значение.
        normalized_model = model_name.split("/", 1)[1] if model_name.startswith("models/") else model_name
        url = GEMINI_URL_TMPL.format(model=normalized_model)
        logger.info("Gemini request url: %s (raw model: %s)", url, model_name)
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(120.0, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    def _extract_json_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        candidates = response.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini не вернул кандидатов для JSON ответа")

        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            text = part.get("text")
            if not text:
                continue
            cleaned = self._strip_code_fence(text)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:  # pragma: no cover - логирование
                logger.warning("Не удалось распарсить JSON от Gemini: %s", exc)
        raise ValueError("Gemini вернул неожиданный формат ответа")

    @staticmethod
    def _extract_text_response(response: Dict[str, Any]) -> str:
        candidates = response.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini не вернул кандидатов для ответа")
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            text = part.get("text")
            if text:
                return text.strip()
        raise ValueError("Gemini вернул неожиданный формат ответа")

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        if text.startswith("```"):
            text = text.strip("`\n")
            if text.startswith("json"):
                text = text[4:]
        return text.strip()

    def _prepare_vertex_payload(
        self, raw: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str, Dict[str, Any]]:
        parsed = self._extract_payload(raw)
        blueprint = parsed.get("veo3_blueprint") or {}
        shots = blueprint.get("shots") or []
        shot = shots[0] if shots else {}

        vertex_base = parsed.get("vertex_request") or {}
        base_instances = vertex_base.get("instances") or [{}]
        base_instance = base_instances[0] if base_instances else {}
        base_params = dict(vertex_base.get("parameters") or {})
        base_params.pop("enhancePrompt", None)

        prompt_full = self._compose_prompt_text(base_instance, shot)
        negatives = self._compose_negative_prompt(shot, base_params, blueprint)
        parameters = self._compose_parameters(base_params, blueprint, prompt_full, negatives)

        vertex_request = {
            "instances": [{"prompt": prompt_full}],
            "parameters": parameters,
        }

        return vertex_request, blueprint, prompt_full, parameters

    @staticmethod
    def _extract_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
        if not raw:
            return {}
        if raw.get("vertex_request") or raw.get("veo3_blueprint"):
            return raw
        if raw.get("output"):
            return ReferencePromptService._extract_payload(raw["output"])
        return raw

    def _compose_prompt_text(self, base_instance: Dict[str, Any], shot: Dict[str, Any]) -> str:
        pieces: List[str] = []

        prompt = (base_instance.get("prompt") or "").strip()
        if prompt:
            pieces.append(prompt)

        camera = shot.get("camera") or {}
        cam_parts: List[str] = []
        if camera.get("framing_en"):
            cam_parts.append(f"framing: {camera['framing_en']}")
        if camera.get("lens_en"):
            cam_parts.append(f"lens: {camera['lens_en']}")
        if camera.get("movement_en"):
            cam_parts.append(f"movement: {camera['movement_en']}")
        if cam_parts:
            pieces.append("camera: " + "; ".join(cam_parts))

        subjects = shot.get("subjects_en") or []
        if subjects:
            pieces.append("subjects: " + ", ".join(subjects))
        if shot.get("environment_en"):
            pieces.append(f"environment: {shot['environment_en']}")
        if shot.get("lighting_en"):
            pieces.append(f"lighting: {shot['lighting_en']}")

        style = shot.get("style") or {}
        style_parts: List[str] = []
        if style.get("look_en"):
            style_parts.append(f"look: {style['look_en']}")
        if style.get("color_en"):
            style_parts.append(f"color: {style['color_en']}")
        if style.get("grade_en"):
            style_parts.append(f"grade: {style['grade_en']}")
        if style_parts:
            pieces.append("style: " + "; ".join(style_parts))

        prompt_full = ". ".join(pieces).strip()
        prompt_full = re_collapse_whitespace(prompt_full)

        if not prompt_full and shot.get("prompt_en"):
            prompt_full = re_collapse_whitespace(str(shot["prompt_en"]))

        return prompt_full[:2000]

    def _compose_negative_prompt(
        self,
        shot: Dict[str, Any],
        base_params: Dict[str, Any],
        blueprint: Dict[str, Any],
    ) -> str:
        items: List[str] = []

        def push_many(raw_value: Any) -> None:
            if not raw_value:
                return
            if isinstance(raw_value, str):
                candidates = [part.strip() for part in raw_value.split(",")]
            elif isinstance(raw_value, Iterable):
                candidates = [str(part).strip() for part in raw_value]
            else:
                candidates = [str(raw_value).strip()]
            for cand in candidates:
                if cand and cand not in items:
                    items.append(cand)

        push_many(shot.get("negative_en"))
        push_many(base_params.get("negativePrompt"))

        constraints = blueprint.get("constraints") or {}
        if constraints.get("no_text_overlay", True):
            push_many("text overlay")

        for extra in ("watermark", "logo", "blurry"):
            push_many(extra)

        return ", ".join(items)

    def _compose_parameters(
        self,
        base_params: Dict[str, Any],
        blueprint: Dict[str, Any],
        prompt_full: str,
        negatives: str,
    ) -> Dict[str, Any]:
        video_spec = blueprint.get("video_spec") or {}

        aspect = base_params.get("aspectRatio") or video_spec.get("aspect_ratio") or "9:16"
        if aspect not in {"9:16", "16:9"}:
            aspect = "9:16"

        duration = base_params.get("durationSeconds") or video_spec.get("duration_sec") or 6
        duration = self._pick_duration(duration)

        resolution = base_params.get("resolution")
        if not resolution:
            res_raw = str(video_spec.get("resolution") or "").lower()
            resolution = "1080p" if "1080" in res_raw else "720p"

        generate_audio = base_params.get("generateAudio")
        if generate_audio is None:
            audio = blueprint.get("audio") or {}
            has_audio = bool(
                audio.get("voiceover_en")
                or (audio.get("music") and any(audio.get("music", {}).values()))
                or audio.get("sfx_en")
            )
            generate_audio = has_audio

        person_generation = self._norm_person(base_params.get("personGeneration") or "allow_adult")
        sample_count = clamp(int(base_params.get("sampleCount", 1)), 1, 4)

        seed = base_params.get("seed")
        if seed is None:
            seed = fnv1a32(json.dumps({"aspect": aspect, "duration": duration, "prompt": prompt_full, "negative": negatives}, ensure_ascii=False))

        params: Dict[str, Any] = {
            "aspectRatio": aspect,
            "durationSeconds": duration,
            "generateAudio": bool(generate_audio),
            "negativePrompt": negatives,
            "personGeneration": person_generation,
            "resolution": resolution,
            "sampleCount": sample_count,
            "seed": int(seed),
            "compressionQuality": "optimized",
        }

        storage_uri = base_params.get("storageUri")
        if storage_uri:
            params["storageUri"] = str(storage_uri)

        return params

    def _format_chunks(self, pretty: str) -> List[str]:
        chunks_raw = chunk_text(pretty, 3500) or [pretty]
        total = len(chunks_raw)
        formatted: List[str] = []
        for idx, chunk in enumerate(chunks_raw, start=1):
            header = "*Veo 3 request*" if total == 1 else f"*Veo 3 request — часть {idx} из {total}*"
            formatted.append(f"{header}\n```json\n{chunk}\n```")
        return formatted

    @staticmethod
    def _norm_person(value: Any) -> str:
        text = str(value).strip().lower()
        return "disallow" if text in {"disallow", "dont_allow", "don't_allow"} else "allow_adult"

    @staticmethod
    def _pick_duration(value: Any) -> int:
        try:
            num = float(value)
        except (TypeError, ValueError):
            num = 6
        candidates = [4, 6, 8]
        return min(candidates, key=lambda x: abs(x - num))


def fnv1a32(text: str) -> int:
    h = 0x811C9DC5
    for ch in text:
        h ^= ord(ch)
        h = (h * 0x01000193) % (1 << 32)
    return h


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def re_collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def chunk_text(text: str, limit: int) -> List[str]:
    """Разбивает текст на части не длиннее limit."""

    if not text:
        return []
    return [text[i : i + limit] for i in range(0, len(text), limit)]
