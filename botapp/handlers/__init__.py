"""
Обработчики команд бота
"""
from .global_commands import router as global_commands_router
from .menu import router as menu_router
from .image_generation import router as image_router
from .video_generation import router as video_router
from .reference_prompt import router as reference_prompt_router
from .payment import router as payment_router

# Главный роутер, который объединяет все
from aiogram import Router
from botapp.middlewares.chat_logging import ChatLoggingMiddleware

main_router = Router()
# ВАЖНО: global_commands_router должен быть первым!
# Он обрабатывает кнопки меню из любого состояния
main_router.include_router(global_commands_router)
main_router.include_router(menu_router)
main_router.include_router(image_router)
main_router.include_router(video_router)
main_router.include_router(payment_router)
main_router.include_router(reference_prompt_router)
main_router.message.middleware(ChatLoggingMiddleware())
main_router.callback_query.middleware(ChatLoggingMiddleware())

__all__ = ['main_router']
