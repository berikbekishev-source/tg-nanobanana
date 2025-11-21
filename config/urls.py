"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from botapp.api import api  # Ninja API
from lavatop.api import miniapp_api  # Payment API
from lavatop.views import miniapp_payment, midjourney_webapp

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),  # /api/telegram/webhook и /api/health
    path("api/miniapp/", miniapp_api.urls),  # Payment API endpoints
    path("miniapp/", miniapp_payment, name='miniapp_payment'),  # Payment page
    path("midjourney/", midjourney_webapp, name='midjourney_webapp'),  # Midjourney WebApp
    path("dashboard/", include("dashboard.urls")),
]

# Статические файлы для Payment App
if settings.DEBUG:
    urlpatterns += static('/lavatop/webapp/', document_root='lavatop/webapp')
