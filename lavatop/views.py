from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.http import HttpResponse
import os


@csrf_exempt
@xframe_options_exempt
def miniapp_payment(request):
    """
    Главная страница Telegram Mini App для оплаты
    """
    # Путь к файлу оплаты
    webapp_dir = os.path.join(os.path.dirname(__file__), 'webapp')
    payment_path = os.path.join(webapp_dir, 'payment.html')

    # Читаем HTML файл
    with open(payment_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    return HttpResponse(html_content, content_type='text/html')
