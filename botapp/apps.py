from django.apps import AppConfig


class BotappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "botapp"

    def ready(self):
        from .telegram import dp  # noqa
        from .handlers import router as basic_router  # noqa
        dp.include_router(basic_router)
