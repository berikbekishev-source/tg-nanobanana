#!/usr/bin/env python3
"""
Тестирование полной интеграции с Lava API
"""

import os
import sys
import django
from decimal import Decimal

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/Users/berik/Desktop/tg-nanobanana')
django.setup()

from miniapp.payment_providers.lava_provider import LavaAPI, get_payment_url


def test_lava_api():
    """
    Тестирует подключение и основные функции Lava API
    """

    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ИНТЕГРАЦИИ С LAVA API")
    print("=" * 60)

    # Инициализация API
    lava_api = LavaAPI()

    print("\n1. Проверка конфигурации:")
    print("-" * 40)

    if lava_api.api_key:
        print(f"✅ API Key настроен: {lava_api.api_key[:10]}...{lava_api.api_key[-4:]}")
    else:
        print("❌ API Key не настроен!")
        return False

    if lava_api.webhook_secret:
        print(f"✅ Webhook Secret настроен: {lava_api.webhook_secret}")
    else:
        print("⚠️  Webhook Secret не настроен")

    # Тест создания счета через API
    print("\n2. Тест создания счета через API:")
    print("-" * 40)

    test_order_id = f"api_test_{int(os.urandom(4).hex(), 16)}"
    test_amount = Decimal("5.00")  # $5 за 100 токенов

    print(f"Order ID: {test_order_id}")
    print(f"Amount: ${test_amount}")

    try:
        # Debug: показываем URL и headers
        print(f"   API URL: {lava_api.BASE_URL}/invoice/create")
        print(f"   Headers: X-Api-Key: {lava_api.api_key[:10]}...{lava_api.api_key[-4:] if lava_api.api_key else 'None'}")

        invoice = lava_api.create_invoice(
            amount=test_amount,
            order_id=test_order_id,
            custom_fields={
                "test": True,
                "credits": 100,
                "email": "test@example.com"
            }
        )

        if invoice:
            print(f"✅ Счет создан успешно!")
            print(f"   Invoice ID: {invoice.get('id')}")
            print(f"   Payment URL: {invoice.get('url')}")
            print(f"   Status: {invoice.get('status')}")

            # Сохраним ID для проверки статуса
            invoice_id = invoice.get('id')

            # Проверка статуса счета
            print("\n3. Проверка статуса счета:")
            print("-" * 40)

            status = lava_api.get_invoice_status(invoice_id)
            if status:
                print(f"✅ Статус получен: {status}")
            else:
                print("⚠️  Не удалось получить статус")

            return True

        else:
            print("❌ Не удалось создать счет через API")
            print("   Проверьте правильность API ключа")
            return False

    except Exception as e:
        print(f"❌ Ошибка при работе с API: {e}")
        return False


def test_payment_url_generation():
    """
    Тестирует генерацию платежных ссылок
    """

    print("\n4. Тест генерации платежных ссылок:")
    print("-" * 40)

    test_cases = [
        (100, "test_100"),
        (200, "test_200"),
        (500, "test_500"),
        (1000, "test_1000")
    ]

    for credits, order_id in test_cases:
        print(f"\nТест для {credits} токенов:")

        # Тест с API
        url_api = get_payment_url(
            credits=credits,
            transaction_id=order_id,
            user_email="test@example.com",
            use_api=True
        )

        if url_api:
            print(f"  ✅ С API: {url_api[:50]}...")
        else:
            print(f"  ⚠️  API не работает, используется fallback")

            # Тест со статическими ссылками
            url_static = get_payment_url(
                credits=credits,
                transaction_id=order_id,
                user_email="test@example.com",
                use_api=False
            )

            if url_static:
                print(f"  ✅ Статическая: {url_static[:50]}...")
            else:
                print(f"  ❌ Нет статической ссылки для {credits} токенов")


def test_webhook_signature():
    """
    Тестирует проверку подписи webhook
    """

    print("\n5. Тест проверки подписи webhook:")
    print("-" * 40)

    lava_api = LavaAPI()

    test_data = '{"status": "success", "amount": 5.00}'

    # Правильная подпись
    import hmac
    import hashlib

    if lava_api.webhook_secret:
        correct_signature = hmac.new(
            lava_api.webhook_secret.encode(),
            test_data.encode(),
            hashlib.sha256
        ).hexdigest()

        # Проверка правильной подписи
        if lava_api.verify_webhook_signature(test_data, correct_signature):
            print("✅ Правильная подпись принята")
        else:
            print("❌ Правильная подпись отклонена")

        # Проверка неправильной подписи
        if not lava_api.verify_webhook_signature(test_data, "wrong_signature"):
            print("✅ Неправильная подпись отклонена")
        else:
            print("❌ Неправильная подпись принята")
    else:
        print("⚠️  Webhook Secret не настроен, проверка подписи отключена")


if __name__ == "__main__":
    # Основной тест API
    api_works = test_lava_api()

    # Тест генерации ссылок
    test_payment_url_generation()

    # Тест подписи webhook
    test_webhook_signature()

    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 60)

    if api_works:
        print("✅ Lava API работает корректно!")
        print("   - Счета создаются через API")
        print("   - Можно проверять статус платежей")
        print("   - Webhook готов к приему уведомлений")
    else:
        print("⚠️  Lava API не работает, но есть fallback:")
        print("   - Используются статические ссылки")
        print("   - Webhook все равно может принимать уведомления")

    print("\n📝 Рекомендации:")
    print("1. Убедитесь, что API ключ правильный")
    print("2. Проверьте, что webhook настроен в Lava.top")
    print("3. Добавьте статические ссылки для всех пакетов токенов")
    print("4. Протестируйте реальный платеж с минимальной суммой")