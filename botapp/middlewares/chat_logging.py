from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from botapp.chat_logger import ChatLogger


class ChatLoggingMiddleware(BaseMiddleware):
    """
    Сохраняем каждое входящее сообщение пользователя.
    """

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            await ChatLogger.log_incoming(event)
        return await handler(event, data)
