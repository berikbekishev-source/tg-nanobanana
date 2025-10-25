from django.apps import AppConfig


class BotappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "botapp"

    def ready(self):
        try:
            from .telegram import dp  # noqa
            from .handlers import main_router  # noqa
            dp.include_router(main_router)
        except ImportError:
            # aiogram not installed yet
            pass
