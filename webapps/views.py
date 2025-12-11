from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.http import HttpResponse, Http404
import os


@csrf_exempt
@xframe_options_exempt
def midjourney_webapp(request):
    """Отдаёт статический WebApp для настроек Midjourney."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "midjourney", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Midjourney WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def midjourney_video_webapp(request):
    """Отдаёт статический WebApp для настроек Midjourney Video."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "midjourney_video", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Midjourney Video WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def kling_webapp(request):
    """Отдаёт статический WebApp настроек Kling v2-5-turbo."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "kling", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Kling WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def kling_v26_webapp(request):
    """Отдаёт статический WebApp настроек Kling v2-6."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "kling-v2-6", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Kling v2-6 WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def veo_webapp(request):
    """Отдаёт статический WebApp для настроек Veo."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "veo", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Veo WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def sora2_webapp(request):
    """Отдаёт статический WebApp настроек Sora 2."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "sora2", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Sora 2 WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def runway_webapp(request):
    """Отдаёт статический WebApp настроек Runway."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "runway", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Runway WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def runway_aleph_webapp(request):
    """Отдаёт статический WebApp настроек Runway Aleph (video-to-video)."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "runway_aleph", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Runway Aleph WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def gpt_image_webapp(request):
    """Отдаёт статический WebApp для настроек GPT Image."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "gpt-image", "index.html")
    if not os.path.exists(page_path):
        raise Http404("GPT Image WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def nanobanana_webapp(request):
    """Отдаёт статический WebApp настроек Nano Banana."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "nanobanana", "index.html")
    if not os.path.exists(page_path):
        raise Http404("NanoBanana WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")


@csrf_exempt
@xframe_options_exempt
def kling_v21_webapp(request):
    """Отдаёт статический WebApp настроек Kling v2-1."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "kling-v2-1", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Kling v2-1 WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")
