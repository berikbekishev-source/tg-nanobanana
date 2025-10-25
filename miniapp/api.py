from ninja import NinjaAPI, Schema
from django.http import JsonResponse
from django.conf import settings
from botapp.models import TgUser, UserBalance, Transaction
from decimal import Decimal
import hashlib
import hmac
from urllib.parse import parse_qsl
import logging

logger = logging.getLogger(__name__)

miniapp_api = NinjaAPI(urls_namespace='miniapp', csrf=False)


class CreatePaymentRequest(Schema):
    email: str
    credits: int
    amount: float
    currency: str = 'USD'
    payment_method: str = 'card'
    user_id: int = None
    init_data: str = None


class PaymentResponse(Schema):
    success: bool
    payment_url: str = None
    payment_id: str = None
    error: str = None


def validate_telegram_init_data(init_data: str) -> dict:
    """
    Валидация данных из Telegram Web App
    """
    try:
        # Парсим init_data
        parsed_data = dict(parse_qsl(init_data))

        # Получаем hash и удаляем его из данных
        received_hash = parsed_data.pop('hash', None)
        if not received_hash:
            return None

        # Создаем строку для проверки
        data_check_string = '\n'.join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )

        # Создаем секретный ключ
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=settings.TELEGRAM_BOT_TOKEN.encode(),
            digestmod=hashlib.sha256
        ).digest()

        # Вычисляем hash
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        # Проверяем hash
        if calculated_hash == received_hash:
            return parsed_data

        return None
    except Exception as e:
        logger.error(f"Error validating init_data: {e}")
        return None


@miniapp_api.post("/create-payment", response=PaymentResponse)
def create_payment(request, data: CreatePaymentRequest):
    """
    Создание платежа для пополнения баланса
    """
    try:
        # Валидация Telegram данных
        if data.init_data:
            validated_data = validate_telegram_init_data(data.init_data)
            if not validated_data:
                return PaymentResponse(
                    success=False,
                    error="Невалидные данные от Telegram"
                )

        # Получаем или создаем пользователя
        user = None
        if data.user_id:
            try:
                tg_user = TgUser.objects.get(chat_id=data.user_id)
                user_balance, _ = UserBalance.objects.get_or_create(user=tg_user)
                user = tg_user
            except TgUser.DoesNotExist:
                logger.warning(f"User {data.user_id} not found")

        # Валидация суммы и кредитов
        if data.credits not in [100, 200, 500, 1000]:
            return PaymentResponse(
                success=False,
                error="Некорректное количество кредитов"
            )

        # Проверка соответствия цены
        expected_price = data.credits * 0.05  # $5 за 100 кредитов
        if abs(data.amount - expected_price) > 0.01:
            return PaymentResponse(
                success=False,
                error="Некорректная сумма платежа"
            )

        # Проверяем наличие пользователя
        if not user:
            return PaymentResponse(
                success=False,
                error="Пользователь не найден. Сначала запустите бота /start"
            )

        # Создаем транзакцию
        transaction = Transaction.objects.create(
            user=user,
            type='deposit',
            amount=Decimal(str(data.amount)),
            balance_after=user_balance.balance,
            description=f"Пополнение {data.credits} кредитов через {data.payment_method}",
            payment_method=data.payment_method,
            is_pending=True,
            is_completed=False
        )

        # Интеграция с Lava.top
        from miniapp.payment_providers.lava_provider import get_payment_url

        payment_url = get_payment_url(
            credits=data.credits,
            transaction_id=transaction.id,
            user_email=data.email
        )

        if not payment_url:
            transaction.delete()
            return PaymentResponse(
                success=False,
                error=f"Платежная ссылка для {data.credits} токенов еще не создана в Lava.top"
            )

        return PaymentResponse(
            success=True,
            payment_url=payment_url,
            payment_id=str(transaction.id)
        )

    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        return PaymentResponse(
            success=False,
            error=f"Ошибка создания платежа: {str(e)}"
        )


@miniapp_api.post("/lava-webhook")
def lava_webhook(request):
    """
    Webhook для обработки платежей от Lava.top
    """
    from miniapp.payment_providers.lava_provider import parse_webhook_data
    from django.db import transaction as db_transaction
    import json

    try:
        # Получаем данные от Lava.top
        if request.content_type == 'application/json':
            payload = json.loads(request.body)
        else:
            payload = dict(request.POST.items())

        logger.info(f"Lava webhook received: {payload}")

        # Проверка API ключа из заголовка
        api_key = request.headers.get('Authorization') or request.headers.get('X-API-Key')
        expected_key = getattr(settings, 'LAVA_WEBHOOK_SECRET', None)

        if expected_key and api_key != f"Bearer {expected_key}" and api_key != expected_key:
            logger.warning(f"Invalid Lava webhook API key")
            return JsonResponse({"ok": False, "error": "Unauthorized"}, status=401)

        # Парсим данные
        webhook_data = parse_webhook_data(payload)

        # Ищем транзакцию
        transaction_id = webhook_data.get('order_id')
        if not transaction_id:
            logger.error("No order_id in Lava webhook")
            return JsonResponse({"ok": False, "error": "Missing order_id"}, status=400)

        try:
            trans = Transaction.objects.get(id=transaction_id)
        except Transaction.DoesNotExist:
            logger.error(f"Transaction {transaction_id} not found")
            return JsonResponse({"ok": False, "error": "Transaction not found"}, status=404)

        # Проверяем статус платежа
        payment_status = webhook_data.get('status', '').lower()

        if payment_status in ['success', 'paid', 'completed']:
            # Платеж успешен - начисляем токены
            with db_transaction.atomic():
                # Блокируем баланс для обновления
                user_balance = UserBalance.objects.select_for_update().get(
                    user=trans.user
                )

                # Начисляем токены
                credits_amount = trans.amount  # Сумма в USD = количество токенов
                user_balance.balance += credits_amount
                user_balance.total_deposited += credits_amount
                user_balance.save()

                # Обновляем транзакцию
                trans.is_completed = True
                trans.is_pending = False
                trans.payment_id = webhook_data.get('payment_id')
                trans.payment_data = webhook_data.get('raw_data', {})
                trans.balance_after = user_balance.balance
                trans.save()

            logger.info(f"Payment {transaction_id} completed. Credited {credits_amount} tokens to user {trans.user.chat_id}")

            # TODO: Отправить уведомление пользователю в Telegram
            # Можно использовать Celery задачу

            return JsonResponse({"ok": True, "status": "completed"})

        elif payment_status in ['failed', 'cancelled', 'canceled']:
            # Платеж не прошел
            trans.is_pending = False
            trans.is_completed = False
            trans.payment_data = webhook_data.get('raw_data', {})
            trans.save()

            logger.info(f"Payment {transaction_id} failed/cancelled")
            return JsonResponse({"ok": True, "status": "failed"})

        else:
            # Неизвестный статус - просто логируем
            logger.warning(f"Unknown payment status: {payment_status}")
            return JsonResponse({"ok": True, "status": "unknown"})

    except Exception as e:
        logger.error(f"Error processing Lava webhook: {e}", exc_info=True)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@miniapp_api.get("/payment-status/{payment_id}")
def payment_status(request, payment_id: int):
    """
    Проверка статуса платежа
    """
    try:
        transaction = Transaction.objects.get(id=payment_id)

        # Определяем статус
        if transaction.is_completed:
            status = 'completed'
        elif transaction.is_pending:
            status = 'pending'
        else:
            status = 'failed'

        return JsonResponse({
            "success": True,
            "status": status,
            "amount": float(transaction.amount),
            "created_at": transaction.created_at.isoformat()
        })
    except Transaction.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Платеж не найден"
        }, status=404)
