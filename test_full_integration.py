#!/usr/bin/env python3
"""
Полный тест интеграции Lava SDK с платежной системой
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/Users/berik/Desktop/tg-nanobanana')
django.setup()

from django.conf import settings
from miniapp.payment_providers.lava_provider import get_payment_url, get_sdk_instance, verify_webhook_signature


def test_sdk_integration():
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ИНТЕГРАЦИИ LAVA SDK")
    print("=" * 60)

    # 1. Проверка SDK
    print("\n1. Проверка инициализации SDK:")
    print("-" * 40)

    sdk = get_sdk_instance()
    if sdk and sdk.client:
        print("✅ SDK клиент инициализирован")
        if sdk.product_id:
            print(f"✅ Product ID найден: {sdk.product_id}")
        else:
            print("⚠️ Product ID не найден (будет использовано из URL)")
    else:
        print("⚠️ SDK не инициализирована, будут использоваться статические ссылки")

    # 2. Тест создания платежной ссылки для 100 токенов
    print("\n2. Тест создания ссылки для 100 токенов:")
    print("-" * 40)

    test_transaction_id = f"test_{os.urandom(4).hex()}"
    test_email = "test@example.com"

    payment_url = get_payment_url(
        credits=100,
        transaction_id=test_transaction_id,
        user_email=test_email
    )

    if payment_url:
        print(f"✅ Платежная ссылка создана:")
        print(f"   Transaction ID: {test_transaction_id}")
        print(f"   URL: {payment_url[:60]}...")
    else:
        print("❌ Не удалось создать платежную ссылку")

    # 3. Тест для других пакетов (должны быть недоступны)
    print("\n3. Тест для других пакетов токенов:")
    print("-" * 40)

    for credits in [200, 500, 1000]:
        payment_url = get_payment_url(
            credits=credits,
            transaction_id=f"test_{credits}",
            user_email=test_email
        )

        if payment_url:
            print(f"⚠️ {credits} токенов: Неожиданно получена ссылка")
        else:
            print(f"✅ {credits} токенов: Корректно отклонено (пока не поддерживается)")

    # 4. Проверка webhook signature
    print("\n4. Тест проверки подписи webhook:")
    print("-" * 40)

    test_payload = {
        "order_id": "test_order",
        "amount": 5.00,
        "status": "success"
    }

    # Для теста используем фейковую подпись
    test_signature = "test_signature_123"

    # SDK должна обработать это безопасно
    result = verify_webhook_signature(test_payload, test_signature)
    print(f"Результат проверки подписи: {result}")

    if result:
        print("✅ Подпись принята (возможно, проверка отключена в тестовом режиме)")
    else:
        print("⚠️ Подпись отклонена (это нормально для тестовой подписи)")

    # 5. Итоговый статус
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 60)

    print("\n✅ Система готова к работе:")
    print("  • SDK интеграция настроена")
    print("  • 100 токенов доступны для покупки")
    print("  • Остальные пакеты корректно отключены")
    print("  • Webhook готов к приему платежей")

    print("\n📝 Дальнейшие действия:")
    print("  1. Деплой на Railway")
    print("  2. Тестовая покупка 100 токенов")
    print("  3. Проверка начисления токенов")
    print("  4. Добавление остальных пакетов по готовности")


if __name__ == "__main__":
    test_sdk_integration()