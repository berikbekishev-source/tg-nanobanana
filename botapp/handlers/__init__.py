"""
Обработчики команд бота
"""
from .menu import router as menu_router
from .image_generation import router as image_router
from .video_generation import router as video_router
from .payment import router as payment_router

# Главный роутер, который объединяет все
from aiogram import Router

main_router = Router()
main_router.include_router(menu_router)
main_router.include_router(image_router)
main_router.include_router(video_router)
main_router.include_router(payment_router)

__all__ = ['main_router']