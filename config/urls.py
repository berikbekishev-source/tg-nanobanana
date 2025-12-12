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
from lavatop.views import miniapp_payment
from webapps.views import midjourney_webapp, midjourney_video_webapp, kling_webapp, kling_v26_webapp, kling_v21_webapp, kling_o1_webapp, veo_webapp, sora2_webapp, runway_webapp, runway_aleph_webapp, gpt_image_webapp, nanobanana_webapp, nano_banana_webapp

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),  # /api/telegram/webhook и /api/health
    path("api/miniapp/", miniapp_api.urls),  # Payment API endpoints
    path("miniapp/", miniapp_payment, name='miniapp_payment'),  # Payment page
    path("midjourney/", midjourney_webapp, name='midjourney_webapp'),  # Midjourney WebApp
    path("midjourney_video/", midjourney_video_webapp, name='midjourney_video_webapp'),  # Midjourney Video WebApp
    path("kling/", kling_webapp, name='kling_webapp'),  # Kling v2-5-turbo WebApp
    path("kling-v2-6/", kling_v26_webapp, name='kling_v26_webapp'),  # Kling v2-6 WebApp
    path("kling-v2-1/", kling_v21_webapp, name='kling_v21_webapp'),  # Kling v2-1 WebApp
    path("kling-o1/", kling_o1_webapp, name='kling_o1_webapp'),  # Kling O1 (Omni) WebApp
    path("veo/", veo_webapp, name='veo_webapp'),  # Veo WebApp
    path("sora2/", sora2_webapp, name='sora2_webapp'),  # Sora 2 WebApp
    path("runway/", runway_webapp, name='runway_webapp'),  # Runway WebApp
    path("runway-aleph/", runway_aleph_webapp, name='runway_aleph_webapp'),  # Runway Aleph WebApp
    path("gpt-image/", gpt_image_webapp, name='gpt_image_webapp'),  # GPT Image WebApp
    path("nanobanana/", nanobanana_webapp, name='nanobanana_webapp'),  # Nano Banana Pro WebApp
    path("nano-banana/", nano_banana_webapp, name='nano_banana_webapp'),  # Nano Banana WebApp
    path("dashboard/", include("dashboard.urls")),
]

# Статические файлы для Payment App
if settings.DEBUG:
    urlpatterns += static('/lavatop/webapp/', document_root='lavatop/webapp')
