#!/usr/bin/env python3
"""
Тестирование с реальными вебхуками от Lava.top
Использует тестовый режим для создания платежей без реальной оплаты
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from botapp.models import TgUser, UserBalance, Transaction
from decimal import Decimal


class WebhookReceiver:
    """Получатель вебхуков для тестирования"""

    def __init__(self, port=8080):
        self.port = port
        self.received_webhooks = []
        self.server = None
        self.server_thread = None

    def start(self):
        """Запуск локального сервера для приема вебхуков"""

        class WebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path == '/webhook':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)

                    # Сохраняем полученный вебхук
                    webhook_data = {
                        'headers': dict(self.headers),
                        'body': json.loads(post_data.decode('utf-8')),
                        'timestamp': datetime.now().isoformat()
                    }

                    self.server.parent.received_webhooks.append(webhook_data)

                    print(f"\n✅ Webhook received at {webhook_data['timestamp']}")
                    print(f"Data: {json.dumps(webhook_data['body'], indent=2)}")

                    # Отвечаем 200 OK
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'ok': True}).encode('utf-8'))

            def log_message(self, format, *args):
                pass  # Отключаем логи

        self.server = HTTPServer(('localhost', self.port), WebhookHandler)
        self.server.parent = self

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        print(f"🎯 Webhook receiver started on port {self.port}")

    def stop(self):
        """Остановка сервера"""
        if self.server:
            self.server.shutdown()
            print("🛑 Webhook receiver stopped")


class LavaTestMode:
    """Класс для работы с тестовым режимом Lava.top"""

    def __init__(self):
        self.api_key = os.getenv('LAVA_API_KEY', 'HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb')
        self.base_url = "https://api.lava.top"
        self.test_mode = True

    def create_test_payment(self, webhook_url: str):
        """
        Создание тестового платежа в Lava.top

        В тестовом режиме Lava.top позволяет:
        1. Создавать платежи с тестовыми картами
        2. Автоматически подтверждать платежи
        3. Отправлять реальные вебхуки
        """

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'X-Test-Mode': 'true'  # Включаем тестовый режим
        }

        # Создаем тестовый счет
        invoice_data = {
            'amount': 5.00,
            'currency': 'USD',
            'order_id': f'test_{int(time.time())}',
            'description': 'Test payment - 100 tokens',
            'webhook_url': webhook_url,
            'success_url': 'https://example.com/success',
            'fail_url': 'https://example.com/fail',
            'test_mode': True,  # Важно: включаем тестовый режим
            'auto_complete': True  # Автоматически завершить платеж (для тестов)
        }

        print(f"\n📝 Creating test invoice...")
        print(f"Webhook URL: {webhook_url}")
        print(f"Data: {json.dumps(invoice_data, indent=2)}")

        try:
            # Пробуем создать через v2 API
            response = requests.post(
                f"{self.base_url}/api/v2/invoice",
                headers=headers,
                json=invoice_data,
                timeout=30
            )

            if response.status_code == 404:
                # Если v2 не работает, пробуем v1
                response = requests.post(
                    f"{self.base_url}/api/v1/invoice",
                    headers=headers,
                    json=invoice_data,
                    timeout=30
                )

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Test invoice created!")
                print(f"Invoice ID: {data.get('id')}")
                print(f"Payment URL: {data.get('url')}")
                return data
            else:
                print(f"❌ Failed to create invoice: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def trigger_test_webhook(self, invoice_id: str):
        """
        Триггер тестового вебхука от Lava.top
        Некоторые платежные системы позволяют вручную триггерить вебхуки для тестов
        """

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'X-Test-Mode': 'true'
        }

        # Пытаемся триггернуть вебхук
        trigger_data = {
            'invoice_id': invoice_id,
            'action': 'complete',  # Завершить платеж
            'trigger_webhook': True  # Отправить вебхук
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/test/trigger-webhook",
                headers=headers,
                json=trigger_data,
                timeout=30
            )

            if response.status_code == 200:
                print(f"✅ Webhook triggered for invoice {invoice_id}")
                return True
            else:
                print(f"⚠️ Manual webhook trigger not available: {response.status_code}")
                return False

        except Exception as e:
            print(f"⚠️ Trigger endpoint not available: {e}")
            return False


class NgrokTunnel:
    """Управление ngrok туннелем для публичного доступа к локальному вебхуку"""

    def __init__(self, port=8080):
        self.port = port
        self.public_url = None
        self.process = None

    def start(self):
        """Запуск ngrok туннеля"""
        try:
            # Проверяем, установлен ли ngrok
            result = subprocess.run(['which', 'ngrok'], capture_output=True, text=True)
            if result.returncode != 0:
                print("⚠️ ngrok не установлен. Установите его командой:")
                print("brew install ngrok/ngrok/ngrok")
                return None

            # Запускаем ngrok
            print(f"🚇 Starting ngrok tunnel on port {self.port}...")
            self.process = subprocess.Popen(
                ['ngrok', 'http', str(self.port), '--log=stdout'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Получаем публичный URL через API ngrok
            time.sleep(3)  # Даем время запуститься

            try:
                response = requests.get('http://localhost:4040/api/tunnels')
                tunnels = response.json()
                for tunnel in tunnels['tunnels']:
                    if tunnel['proto'] == 'https':
                        self.public_url = tunnel['public_url']
                        print(f"✅ Ngrok tunnel started: {self.public_url}")
                        return self.public_url
            except:
                print("⚠️ Не удалось получить URL ngrok. Используйте Railway URL")

        except Exception as e:
            print(f"❌ Error starting ngrok: {e}")
            return None

    def stop(self):
        """Остановка ngrok"""
        if self.process:
            self.process.terminate()
            print("🛑 Ngrok tunnel stopped")


def test_with_railway_webhook():
    """Тест с использованием Railway URL (для продакшна)"""

    print("\n" + "="*60)
    print("🚂 TESTING WITH RAILWAY WEBHOOK URL")
    print("="*60)

    # Получаем Railway URL
    railway_url = os.getenv('RAILWAY_PUBLIC_DOMAIN', 'web-production-96df.up.railway.app')
    if not railway_url:
        print("⚠️ RAILWAY_PUBLIC_DOMAIN не установлен")
        print("Запустите: railway variables")
        return

    webhook_url = f"https://{railway_url}/api/miniapp/lava-webhook"
    print(f"Webhook URL: {webhook_url}")

    # Создаем тестовый платеж
    lava = LavaTestMode()
    invoice = lava.create_test_payment(webhook_url)

    if invoice:
        print(f"\n📧 Проверьте логи Railway для получения вебхука:")
        print(f"railway logs --service web | grep 'Lava webhook'")

        # Ждем вебхук
        print(f"\n⏳ Ожидаем вебхук в течение 30 секунд...")
        time.sleep(30)

        # Проверяем статус через API
        check_invoice_status(invoice['id'])


def test_with_local_ngrok():
    """Тест с использованием локального сервера и ngrok"""

    print("\n" + "="*60)
    print("🏠 TESTING WITH LOCAL WEBHOOK + NGROK")
    print("="*60)

    # Запускаем локальный webhook receiver
    receiver = WebhookReceiver(port=8080)
    receiver.start()

    # Запускаем ngrok
    ngrok = NgrokTunnel(port=8080)
    public_url = ngrok.start()

    if not public_url:
        print("❌ Не удалось запустить ngrok")
        receiver.stop()
        return

    webhook_url = f"{public_url}/webhook"

    # Создаем тестовый платеж
    lava = LavaTestMode()
    invoice = lava.create_test_payment(webhook_url)

    if invoice:
        # Пробуем триггернуть вебхук вручную
        lava.trigger_test_webhook(invoice['id'])

        # Ждем вебхук
        print(f"\n⏳ Ожидаем вебхук в течение 30 секунд...")
        for i in range(30):
            if receiver.received_webhooks:
                print(f"\n✅ Получено {len(receiver.received_webhooks)} вебхуков!")
                break
            time.sleep(1)
            print(".", end="", flush=True)

        # Показываем результаты
        if receiver.received_webhooks:
            print("\n\n📊 RECEIVED WEBHOOKS:")
            for webhook in receiver.received_webhooks:
                print(f"Time: {webhook['timestamp']}")
                print(f"Body: {json.dumps(webhook['body'], indent=2)}")
        else:
            print("\n❌ Вебхуки не получены")

    # Останавливаем сервисы
    receiver.stop()
    ngrok.stop()


def check_invoice_status(invoice_id: str):
    """Проверка статуса счета через API"""

    api_key = os.getenv('LAVA_API_KEY', 'HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb')
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(
            f"https://api.lava.top/api/v1/invoices/{invoice_id}",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            print(f"\n📋 Invoice Status:")
            print(f"ID: {data.get('id')}")
            print(f"Status: {data.get('status')}")
            print(f"Amount: {data.get('amount')} {data.get('currency')}")
            return data
        else:
            print(f"❌ Failed to check status: {response.status_code}")

    except Exception as e:
        print(f"❌ Error checking status: {e}")


def create_test_database_entries():
    """Создание тестовых записей в БД для тестирования"""

    print("\n📝 Creating test database entries...")

    # Создаем тестового пользователя
    test_user, created = TgUser.objects.get_or_create(
        chat_id=123456789,
        defaults={
            'username': 'test_user',
            'first_name': 'Test',
            'last_name': 'User'
        }
    )

    # Создаем баланс
    balance, _ = UserBalance.objects.get_or_create(
        user=test_user,
        defaults={'balance': Decimal('0')}
    )

    # Создаем тестовую транзакцию
    transaction = Transaction.objects.create(
        user=test_user,
        type='deposit',
        amount=Decimal('5.00'),
        balance_after=balance.balance,
        description='Test payment for 100 tokens',
        payment_method='card',
        is_pending=True,
        is_completed=False
    )

    print(f"✅ Test user: {test_user.username}")
    print(f"✅ Transaction ID: {transaction.id}")

    return test_user, transaction


def run_complete_test():
    """Запуск полного теста платежной системы"""

    print("\n" + "🎯"*30)
    print("LAVA.TOP PAYMENT SYSTEM TEST")
    print("Real webhooks without actual payments")
    print("🎯"*30)

    # Создаем тестовые данные в БД
    test_user, transaction = create_test_database_entries()

    print("\n\nВыберите способ тестирования:")
    print("1. Railway webhook (для продакшна)")
    print("2. Local + ngrok (для локальной разработки)")
    print("3. Оба варианта")

    choice = input("\nВаш выбор (1/2/3): ").strip()

    if choice == '1':
        test_with_railway_webhook()
    elif choice == '2':
        test_with_local_ngrok()
    elif choice == '3':
        test_with_railway_webhook()
        test_with_local_ngrok()
    else:
        print("❌ Неверный выбор")


if __name__ == "__main__":
    run_complete_test()
