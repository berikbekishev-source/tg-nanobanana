from aiogram import Router, F
from aiogram.types import Message
from asgiref.sync import sync_to_async
from django.conf import settings
from .models import GenRequest, TgUser
from .tasks import generate_image_task

router = Router()

def _parse_qty_and_prompt(text: str) -> tuple[int, str]:
    # Простое правило: "x3 ..." или "--qty 3 ..." (1..10)
    import re
    qty = 1
    m = re.match(r"\s*(?:x|--?qty)\s*(\d+)\s+(.*)$", text.strip(), re.I)
    if m:
        q = max(1, min(10, int(m.group(1))))
        return q, m.group(2).strip()
    return 1, text.strip()

@router.message(F.text)
async def on_text(msg: Message):
    qty, prompt = _parse_qty_and_prompt(msg.text or "")
    if not prompt:
        await msg.answer("Пришлите текстовый промт (например: `x3 кот в очках`).")
        return
    # upsert user
    await sync_to_async(TgUser.objects.get_or_create)(chat_id=msg.chat.id, defaults={"username": msg.from_user.username or ""})
    # создаём запись запроса
    req = await sync_to_async(GenRequest.objects.create)(
        run_code=str(msg.message_id), chat_id=msg.chat.id,
        prompt=prompt, quantity=qty, model=settings.GEMINI_IMAGE_MODEL
    )
    generate_image_task.delay(req.id)  # Celery
    await msg.answer(f"Принял промт. Генерирую {qty} изображение(я) в Gemini…")

