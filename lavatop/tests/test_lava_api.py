#!/usr/bin/env python3
"""
Тестирование Lava.top API
Основано на документации API endpoints
"""

import requests
import json
from typing import Dict, Any, Optional

# API Configuration
API_KEY = "HUavlwH154yV1KjiTbEKnZJyHxem7W0SgE7iIKsbq6MlSjNMulkOS3GgYEadREEb"
BASE_URL = "https://api.lava.top"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}


class LavaAPITester:
    """Класс для тестирования Lava.top API endpoints"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.base_url = BASE_URL

    def test_products_list(self):
        """
        GET /api/v2/products
        Получение списка продуктов. Обновленная версия /api/v1/feed
        """
        print("\n" + "="*60)
        print("TEST: GET /api/v2/products")
        print("="*60)

        try:
            response = self.session.get(f"{self.base_url}/api/v2/products")
            print(f"Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Success! Products retrieved:")
                print(json.dumps(data, indent=2, ensure_ascii=False)[:500])
            else:
                print(f"❌ Error: {response.text}")

            return response

        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

    def test_product_update(self, product_id: str):
        """
        PATCH /api/v2/products/{productId}
        Обновление продукта
        """
        print("\n" + "="*60)
        print(f"TEST: PATCH /api/v2/products/{product_id}")
        print("="*60)

        update_data = {
            "name": "Updated Product Name",
            "description": "Updated description",
            "price": 10.00
        }

        try:
            response = self.session.patch(
                f"{self.base_url}/api/v2/products/{product_id}",
                json=update_data
            )
            print(f"Status Code: {response.status_code}")

            if response.status_code in [200, 204]:
                print("✅ Product updated successfully")
                if response.text:
                    print(f"Response: {response.json()}")
            else:
                print(f"❌ Error: {response.text}")

            return response

        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

    def test_create_invoice(self, amount: float = 5.00):
        """
        POST /api/v2/invoice
        Создание контракта на покупку контента (аналогичен /api/v1/invoice)
        """
        print("\n" + "="*60)
        print("TEST: POST /api/v2/invoice")
        print("="*60)

        invoice_data = {
            "amount": amount,
            "currency": "USD",
            "order_id": f"test_order_{int(time.time())}",
            "description": "Test payment for 100 tokens",
            "success_url": "https://example.com/success",
            "fail_url": "https://example.com/fail",
            "webhook_url": "https://your-app.railway.app/api/miniapp/lava-webhook",
            "expire": 1800  # 30 минут
        }

        print(f"Request Data: {json.dumps(invoice_data, indent=2)}")

        try:
            response = self.session.post(
                f"{self.base_url}/api/v2/invoice",
                json=invoice_data
            )
            print(f"Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Invoice created successfully!")
                print(f"Invoice ID: {data.get('id')}")
                print(f"Payment URL: {data.get('url')}")
                print(f"Full Response: {json.dumps(data, indent=2)}")
                return data
            else:
                print(f"❌ Error: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

    def test_get_invoices(self):
        """
        GET /api/v1/invoices
        Получение страницы контрактов API-ключа, использованного в запросе
        """
        print("\n" + "="*60)
        print("TEST: GET /api/v1/invoices")
        print("="*60)

        params = {
            "limit": 10,
            "offset": 0
        }

        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/invoices",
                params=params
            )
            print(f"Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Invoices retrieved successfully!")
                print(f"Total: {data.get('total', 0)}")
                print(f"Invoices: {json.dumps(data.get('data', [])[:2], indent=2)}")
            else:
                print(f"❌ Error: {response.text}")

            return response

        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

    def test_get_invoice_by_id(self, invoice_id: str):
        """
        GET /api/v1/invoices/{id}
        Получение контракта по идентификатору
        """
        print("\n" + "="*60)
        print(f"TEST: GET /api/v1/invoices/{invoice_id}")
        print("="*60)

        try:
            response = self.session.get(f"{self.base_url}/api/v1/invoices/{invoice_id}")
            print(f"Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Invoice details retrieved!")
                print(f"Status: {data.get('status')}")
                print(f"Amount: {data.get('amount')} {data.get('currency')}")
                print(f"Full Response: {json.dumps(data, indent=2)}")
            else:
                print(f"❌ Error: {response.text}")

            return response

        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

    def test_sales_report(self):
        """
        GET /api/v1/sales
        Получение списка продаж партнёра
        """
        print("\n" + "="*60)
        print("TEST: GET /api/v1/sales")
        print("="*60)

        params = {
            "limit": 10,
            "offset": 0,
            "date_from": "2025-10-01",
            "date_to": "2025-10-25"
        }

        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/sales",
                params=params
            )
            print(f"Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Sales report retrieved!")
                print(f"Total sales: {data.get('total', 0)}")
                print(f"Period: {params['date_from']} to {params['date_to']}")
                if data.get('data'):
                    print(f"Recent sales: {json.dumps(data['data'][:2], indent=2)}")
            else:
                print(f"❌ Error: {response.text}")

            return response

        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

    def test_subscriptions(self):
        """
        GET /api/v1/subscriptions
        Получение страницы подписок API-ключа, использованного в запросе
        """
        print("\n" + "="*60)
        print("TEST: GET /api/v1/subscriptions")
        print("="*60)

        try:
            response = self.session.get(f"{self.base_url}/api/v1/subscriptions")
            print(f"Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Subscriptions retrieved!")
                print(f"Active subscriptions: {len(data.get('data', []))}")
                if data.get('data'):
                    print(f"Subscriptions: {json.dumps(data['data'][:2], indent=2)}")
            else:
                print(f"❌ Error: {response.text}")

            return response

        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None

    def test_webhook_contract(self):
        """
        POST /example-of-webhook-route-contract
        Пример API-метода, который должен создать сервис автора для приёма вебхуков от lava.top
        """
        print("\n" + "="*60)
        print("TEST: Webhook Contract Example")
        print("="*60)

        # Пример данных webhook от Lava.top
        webhook_data = {
            "id": "payment_12345",
            "order_id": "test_order_123",
            "status": "success",
            "amount": 5.00,
            "currency": "USD",
            "buyer_email": "buyer@example.com",
            "product_id": "prod_100_tokens",
            "timestamp": "2025-10-25T15:30:00Z",
            "signature": "webhook_signature_here"
        }

        print("Example webhook payload from Lava.top:")
        print(json.dumps(webhook_data, indent=2))

        print("\nWebhook handler should:")
        print("1. Verify signature")
        print("2. Check order_id exists in database")
        print("3. Update payment status")
        print("4. Credit tokens to user balance")
        print("5. Send notification to user")
        print("6. Return 200 OK response")

        return webhook_data


def run_full_test_suite():
    """Запуск полного набора тестов API"""
    import time

    print("\n" + "🚀"*30)
    print("LAVA.TOP API TEST SUITE")
    print("🚀"*30)
    print(f"\nAPI Key: {API_KEY[:20]}...")
    print(f"Base URL: {BASE_URL}")

    tester = LavaAPITester()

    # 1. Test Products
    print("\n📦 TESTING PRODUCTS ENDPOINTS")
    products = tester.test_products_list()

    # 2. Test Invoice Creation
    print("\n💳 TESTING INVOICE CREATION")
    invoice = tester.test_create_invoice(amount=5.00)

    if invoice and invoice.get('id'):
        # 3. Test Get Invoice by ID
        print("\n🔍 TESTING GET INVOICE BY ID")
        time.sleep(1)
        tester.test_get_invoice_by_id(invoice['id'])

    # 4. Test Get All Invoices
    print("\n📋 TESTING GET ALL INVOICES")
    tester.test_get_invoices()

    # 5. Test Sales Report
    print("\n📊 TESTING SALES REPORT")
    tester.test_sales_report()

    # 6. Test Subscriptions
    print("\n🔄 TESTING SUBSCRIPTIONS")
    tester.test_subscriptions()

    # 7. Test Webhook Example
    print("\n🔔 WEBHOOK CONTRACT EXAMPLE")
    tester.test_webhook_contract()

    print("\n" + "="*60)
    print("✅ TEST SUITE COMPLETED!")
    print("="*60)
    print("\n📌 Important Notes:")
    print("1. Replace API_KEY with your actual Lava.top API key")
    print("2. Some endpoints may require specific permissions")
    print("3. Webhook URL must be publicly accessible")
    print("4. Check rate limits to avoid being blocked")
    print("5. Always handle errors and edge cases in production")


if __name__ == "__main__":
    import time
    run_full_test_suite()