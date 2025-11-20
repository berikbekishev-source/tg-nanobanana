"""
Webhook Processing for Lava.top Payments
"""

import hashlib
import hmac
import json
import logging
from typing import Dict
from django.conf import settings
from decimal import Decimal

from botapp.business.pricing import usd_to_tokens

logger = logging.getLogger(__name__)


def verify_signature(payload: str, signature: str) -> bool:
    """
    Verify webhook signature from Lava.top

    Args:
        payload: Request body as string
        signature: Signature from header

    Returns:
        True if signature is valid
    """

    # Try SDK verification first
    from .provider import get_provider
    provider = get_provider()

    if provider.client:
        try:
            result = provider.verify_webhook_signature(payload, signature)
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"SDK signature verification failed: {e}")

    # Fallback to manual verification
    webhook_secret = getattr(settings, 'LAVA_WEBHOOK_SECRET', None)

    if not webhook_secret:
        logger.warning("LAVA_WEBHOOK_SECRET not configured, skipping verification")
        return True  # Allow in development

    try:
        # Parse payload if it's a string
        if isinstance(payload, str):
            data = json.loads(payload)
        else:
            data = payload

        # Create signature string (adjust based on Lava.top docs)
        data_string = f"{data.get('order_id')}{data.get('amount')}{data.get('status')}"

        # Calculate HMAC
        expected_signature = hmac.new(
            webhook_secret.encode(),
            data_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)

    except Exception as e:
        logger.error(f"Manual signature verification failed: {e}")
        return False


def parse_webhook_data(payload: Dict) -> Dict:
    """
    Parse webhook data from Lava.top according to official specification

    Args:
        payload: Raw webhook data

    Returns:
        Parsed payment data
    """

    # Handle both old format (for backward compatibility) and new official format

    # Official Lava.top format
    if 'eventType' in payload:
        return {
            'event_type': payload.get('eventType'),
            'order_id': payload.get('contractId'),  # contractId is the transaction ID
            'amount': Decimal(str(payload.get('amount', 0))),
            'status': payload.get('status'),
            'payment_id': payload.get('contractId'),
            'currency': payload.get('currency', 'RUB'),
            'email': payload.get('buyer', {}).get('email') if payload.get('buyer') else None,
            'product_id': payload.get('product', {}).get('id') if payload.get('product') else None,
            'product_title': payload.get('product', {}).get('title') if payload.get('product') else None,
            'error_message': payload.get('errorMessage', ''),
            'timestamp': payload.get('timestamp'),
            'parent_contract_id': payload.get('parentContractId'),  # For recurring subscriptions
            'raw_data': payload
        }

    # Legacy format (our test format)
    else:
        return {
            'event_type': 'payment.success' if payload.get('status') == 'success' else 'payment.failed',
            'order_id': payload.get('order_id') or payload.get('custom_id'),
            'amount': Decimal(str(payload.get('amount', 0))),
            'status': payload.get('status'),
            'payment_id': payload.get('id') or payload.get('payment_id'),
            'currency': payload.get('currency', 'USD'),
            'email': payload.get('email'),
            'product_id': None,
            'product_title': None,
            'error_message': '',
            'timestamp': payload.get('created_at'),
            'parent_contract_id': None,
            'custom_fields': payload.get('custom_fields', {}),
            'raw_data': payload
        }


def process_webhook(payload: Dict, signature: str = None) -> Dict:
    """
    Process payment webhook from Lava.top

    Args:
        payload: Webhook payload
        signature: Webhook signature for verification

    Returns:
        Processing result
    """

    logger.info(f"Processing Lava webhook: {payload.get('order_id')}")

    # Verify signature if provided
    if signature:
        payload_str = json.dumps(payload) if isinstance(payload, dict) else str(payload)
        if not verify_signature(payload_str, signature):
            logger.error("Webhook signature verification failed")
            return {
                'success': False,
                'error': 'Invalid signature',
                'status_code': 401
            }

    # Parse webhook data
    payment_data = parse_webhook_data(payload)
    status = payment_data['status'].lower() if payment_data['status'] else ''

    # Process based on status
    if status in ['success', 'paid', 'completed']:
        logger.info(f"Payment {payment_data['order_id']} completed")

        # Calculate tokens based on current rate
        tokens = int(usd_to_tokens(Decimal(str(payment_data['amount']))))

        return {
            'success': True,
            'action': 'credit_tokens',
            'order_id': payment_data['order_id'],
            'tokens': tokens,
            'amount': float(payment_data['amount']),
            'payment_id': payment_data['payment_id'],
            'custom_fields': payment_data['custom_fields']
        }

    elif status in ['failed', 'cancelled', 'canceled']:
        logger.info(f"Payment {payment_data['order_id']} failed/cancelled")

        return {
            'success': True,
            'action': 'mark_failed',
            'order_id': payment_data['order_id'],
            'reason': status
        }

    else:
        logger.warning(f"Unknown payment status: {status}")

        return {
            'success': True,
            'action': 'none',
            'order_id': payment_data['order_id'],
            'status': status
        }


def create_webhook_response(result: Dict) -> Dict:
    """
    Create webhook response for Lava.top

    Args:
        result: Processing result

    Returns:
        Response dict for webhook
    """

    if result.get('success'):
        return {
            'ok': True,
            'status': result.get('action', 'processed')
        }
    else:
        return {
            'ok': False,
            'error': result.get('error', 'Processing failed')
        }
