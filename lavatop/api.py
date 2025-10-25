from ninja import NinjaAPI, Schema
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from botapp.models import TgUser, UserBalance, Transaction
from decimal import Decimal
import hashlib
import hmac
from urllib.parse import parse_qsl
import logging
import uuid

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


@miniapp_api.get("/health")
def health_check(request):
    """
    Проверка работоспособности API
    """
    return {"status": "ok", "api": "miniapp", "timestamp": str(timezone.now())}


@miniapp_api.post("/create-payment")
def create_payment(request, data: CreatePaymentRequest):
    """
    Создание платежа для пополнения баланса
    """
    try:
        logger.info(f"Payment request received: credits={data.credits}, amount={data.amount}, user_id={data.user_id}")

        # Импортируем из текущего модуля
        from . import get_payment_url

        # Валидация Telegram данных (временно отключена для тестирования)
        if data.init_data:
            logger.info(f"Init data received: {data.init_data[:50]}...")  # Показываем первые 50 символов
            # validated_data = validate_telegram_init_data(data.init_data)
            # if not validated_data:
            #     logger.warning("Invalid Telegram init data")
            #     return PaymentResponse(
            #         success=False,
            #         error="Невалидные данные от Telegram"
            #     )

        # Получаем или создаем пользователя
        user = None
        if data.user_id:
            try:
                tg_user = TgUser.objects.get(chat_id=data.user_id)
                user_balance, _ = UserBalance.objects.get_or_create(user=tg_user)
                user = tg_user
                logger.info(f"User {data.user_id} found in database")
            except TgUser.DoesNotExist:
                logger.warning(f"User {data.user_id} not found in database")
                # Временно для тестирования - создаем фейкового пользователя
                # user = None

        # Валидация суммы и кредитов
        if data.credits not in [100, 200, 500, 1000]:
            logger.warning(f"Invalid credits amount: {data.credits}")
            return PaymentResponse(
                success=False,
                error="Некорректное количество кредитов"
            )

        # Проверка соответствия цены
        expected_price = data.credits * 0.05  # $5 за 100 кредитов
        if abs(data.amount - expected_price) > 0.01:
            logger.warning(f"Price mismatch: expected {expected_price}, got {data.amount}")
            return PaymentResponse(
                success=False,
                error="Некорректная сумма платежа"
            )

        # ВРЕМЕННО: Пропускаем проверку пользователя для тестирования
        # if not user:
        #     return PaymentResponse(
        #         success=False,
        #         error="Пользователь не найден. Сначала запустите бота /start"
        #     )

        # Создаем транзакцию (только если есть пользователь)
        transaction_id = None
        if user:
            try:
                user_balance = UserBalance.objects.get(user=user)
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
                transaction_id = transaction.id
                logger.info(f"Transaction {transaction_id} created for user {user.chat_id}")
            except Exception as e:
                logger.error(f"Error creating transaction: {e}")
        else:
            logger.warning("Creating payment without user/transaction for testing")
            # Для тестирования используем фейковый ID
            transaction_id = str(uuid.uuid4())[:8]

        # Получаем URL для оплаты
        logger.info(f"Getting payment URL for credits={data.credits}, transaction_id={transaction_id}")
        payment_url = get_payment_url(
            credits=data.credits,
            transaction_id=transaction_id,
            user_email=data.email
        )

        if not payment_url:
            if user and transaction_id:
                Transaction.objects.filter(id=transaction_id).delete()
            return {
                "success": False,
                "payment_url": None,
                "payment_id": None,
                "error": f"Платежная ссылка для {data.credits} токенов еще не создана в Lava.top"
            }

        logger.info(f"Payment URL generated: {payment_url}")
        response = {
            "success": True,
            "payment_url": payment_url,
            "payment_id": str(transaction_id),
            "error": None
        }
        logger.info(f"Returning success response: {response}")
        return response

    except ImportError as e:
        logger.error(f"Import error in create_payment: {e}", exc_info=True)
        return {
            "success": False,
            "payment_url": None,
            "payment_id": None,
            "error": "Ошибка импорта модуля"
        }
    except Exception as e:
        logger.error(f"Error creating payment: {e}", exc_info=True)
        return {
            "success": False,
            "payment_url": None,
            "payment_id": None,
            "error": f"Ошибка создания платежа: {str(e)}"
        }


@miniapp_api.post("/lava-webhook")
def lava_webhook(request):
    """
    Webhook для обработки платежей от Lava.top
    """
    from .webhook import parse_webhook_data
    from django.db import transaction as db_transaction
    import json

    try:
        # Получаем данные от Lava.top
        if request.content_type == 'application/json':
            payload = json.loads(request.body)
        else:
            payload = dict(request.POST.items())

        logger.info(f"Lava webhook received: {payload}")

        # Логируем важные поля для отладки
        if isinstance(payload, dict):
            logger.info(f"Event Type: {payload.get('eventType', 'N/A')}")
            logger.info(f"Contract ID: {payload.get('contractId', 'N/A')}")
            logger.info(f"Status: {payload.get('status', 'N/A')}")
            if payload.get('product'):
                logger.info(f"Product: {payload.get('product', {}).get('title', 'N/A')}")

        # Проверка API ключа из заголовка
        api_key = request.headers.get('Authorization') or request.headers.get('X-API-Key')
        expected_key = getattr(settings, 'LAVA_WEBHOOK_SECRET', None)

        if expected_key and api_key != f"Bearer {expected_key}" and api_key != expected_key:
            logger.warning(f"Invalid Lava webhook API key")
            return JsonResponse({"ok": False, "error": "Unauthorized"}, status=401)

        # Парсим данные
        webhook_data = parse_webhook_data(payload)

        # Ищем транзакцию
        order_id = webhook_data.get('order_id')
        if not order_id:
            logger.error("No order_id in Lava webhook")
            return JsonResponse({"ok": False, "error": "Missing order_id"}, status=400)

        # Пытаемся найти транзакцию
        trans = None

        # Если order_id - это число, ищем по ID
        try:
            transaction_id = int(order_id)
            trans = Transaction.objects.get(id=transaction_id)
            logger.info(f"Found transaction by ID: {transaction_id}")
        except (ValueError, Transaction.DoesNotExist):
            # Если не число или не найдено по ID, пробуем найти по payment_id
            try:
                trans = Transaction.objects.filter(payment_id=order_id).first()
                if trans:
                    logger.info(f"Found transaction by payment_id: {order_id}")
            except:
                pass

        # Если транзакция не найдена и это новый платеж, создаем новую
        if not trans and webhook_data.get('event_type') == 'payment.success':
            # Для новых платежей от Lava.top создаем транзакцию
            logger.info(f"Creating new transaction for Lava.top payment: {order_id}")

            # Пытаемся найти пользователя по email
            email = webhook_data.get('email')
            if email:
                # В реальной системе нужно связать email с пользователем
                # Пока используем тестового пользователя
                try:
                    test_user = TgUser.objects.get(chat_id=123456789)
                    user_balance, _ = UserBalance.objects.get_or_create(user=test_user)

                    trans = Transaction.objects.create(
                        user=test_user,
                        type='deposit',
                        amount=webhook_data.get('amount', Decimal('0')),
                        balance_after=user_balance.balance,
                        description=f"Payment from Lava.top: {webhook_data.get('product_title', 'Unknown')}",
                        payment_method='lava.top',
                        payment_id=order_id,
                        is_pending=False,
                        is_completed=False
                    )
                    logger.info(f"Created new transaction {trans.id} for Lava.top payment")
                except Exception as e:
                    logger.error(f"Failed to create transaction: {e}")
                    return JsonResponse({"ok": False, "error": "Failed to create transaction"}, status=500)

        if not trans:
            logger.error(f"Transaction {order_id} not found")
            return JsonResponse({"ok": False, "error": "Transaction not found"}, status=404)

        # Проверяем тип события и статус платежа
        event_type = webhook_data.get('event_type', '')
        payment_status = webhook_data.get('status', '').lower()

        # Обработка успешных платежей
        if (event_type == 'payment.success' or
            payment_status in ['success', 'paid', 'completed', 'subscription-active']):
            # Платеж успешен - начисляем токены
            with db_transaction.atomic():
                # Блокируем баланс для обновления
                user_balance = UserBalance.objects.select_for_update().get(
                    user=trans.user
                )

                # Начисляем токены (курс: $0.05 за токен = 20 токенов за $1)
                credits_amount = trans.amount * 20  # Конвертируем USD в токены
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

            logger.info(f"Payment {trans.id} completed. Credited {credits_amount} tokens to user {trans.user.chat_id}")

            # Отправляем уведомление пользователю в Telegram
            try:
                import asyncio
                from botapp.telegram import bot

                message_text = (
                    f"✅ **Платеж успешно выполнен!**\n\n"
                    f"💰 Зачислено: {int(credits_amount)} токенов\n"
                    f"💵 Сумма: ${trans.amount}\n\n"
                    f"Ваш новый баланс: {int(user_balance.balance)} токенов\n\n"
                    f"Спасибо за покупку! 🎉\n"
                    f"Теперь вы можете создавать изображения и видео."
                )

                # Отправляем сообщение асинхронно
                asyncio.run(bot.send_message(
                    chat_id=trans.user.chat_id,
                    text=message_text,
                    parse_mode="Markdown"
                ))
                logger.info(f"Payment notification sent to user {trans.user.chat_id}")
            except Exception as e:
                logger.error(f"Failed to send payment notification: {e}")
                # Не падаем, если не удалось отправить уведомление

            return JsonResponse({"ok": True, "status": "completed"})

        elif (event_type == 'payment.failed' or
              payment_status in ['failed', 'cancelled', 'canceled', 'subscription-failed']):
            # Платеж не прошел
            trans.is_pending = False
            trans.is_completed = False
            trans.payment_data = webhook_data.get('raw_data', {})
            trans.save()

            logger.info(f"Payment {trans.id} failed/cancelled")
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
