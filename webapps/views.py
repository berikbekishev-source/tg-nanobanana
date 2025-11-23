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
def kling_webapp(request):
    """Отдаёт статический WebApp настроек Kling."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "kling", "index.html")
    if not os.path.exists(page_path):
        raise Http404("Kling WebApp not found")
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
def gpt_image_webapp(request):
    """Отдаёт статический WebApp для настроек GPT Image."""
    base_dir = os.path.dirname(__file__)
    page_path = os.path.join(base_dir, "gpt-image", "index.html")
    if not os.path.exists(page_path):
        raise Http404("GPT Image WebApp not found")
    with open(page_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HttpResponse(html_content, content_type="text/html")
