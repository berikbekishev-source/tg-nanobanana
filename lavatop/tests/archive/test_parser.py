#!/usr/bin/env python3
"""
Тестирование парсера вебхуков
"""

import os
import sys
import json

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from lavatop.webhook import parse_webhook_data
from datetime import datetime, timezone

# Тестовый payload в официальном формате Lava.top
official_payload = {
    "eventType": "payment.success",
    "product": {
        "id": "d31384b8-e412-4be5-a2ec-297ae6666c8f",
        "title": "100 Токенов"
    },
    "buyer": {
        "email": "test@example.com"
    },
    "contractId": "7ea82675-4ded-4133-95a7-a6efbaf165cc",
    "amount": 5.00,
    "currency": "USD",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "completed",
    "errorMessage": ""
}

# Парсим данные
parsed_data = parse_webhook_data(official_payload)

print("="*60)
print("TESTING WEBHOOK PARSER")
print("="*60)

print("\n📥 INPUT (Official Lava.top format):")
print(json.dumps(official_payload, indent=2))

print("\n📤 PARSED OUTPUT:")
print(json.dumps({k: str(v) for k, v in parsed_data.items() if k != 'raw_data'}, indent=2))

print("\n🔍 KEY FIELDS:")
print(f"  order_id: {parsed_data.get('order_id')}")
print(f"  event_type: {parsed_data.get('event_type')}")
print(f"  status: {parsed_data.get('status')}")
print(f"  amount: {parsed_data.get('amount')}")
print(f"  email: {parsed_data.get('email')}")

if parsed_data.get('order_id'):
    print("\n✅ order_id is present!")
else:
    print("\n❌ order_id is missing!")
    print("This is why the webhook handler returns 'Missing order_id'")