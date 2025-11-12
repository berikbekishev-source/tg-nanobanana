"""Небольшое служебное изменение для теста пайплайна деплоя.

Не влияет на логику приложения; нужно лишь для прохождения
сквозного теста CI/CD (feature → staging → production).
"""

default_app_config = 'botapp.apps.BotappConfig'
