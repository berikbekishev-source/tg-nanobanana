from ninja import Schema
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from botapp.models import TgUser, UserBalance, Transaction, TokenPackage
from botapp.business.pricing import usd_to_tokens
from decimal import Decimal
import hashlib
import hmac
from urllib.parse import parse_qsl
import logging
import uuid
from asgiref.sync import async_to_sync
import base64

from config.ninja_api import build_ninja_api

logger = logging.getLogger(__name__)

miniapp_api = build_ninja_api(urls_namespace='miniapp')


class CreatePaymentRequest(Schema):
    email: str
    credits: int
    amount: float
    currency: str = 'USD'
    payment_method: str | None = None  # Lava provider enum (UNLIMINT, STRIPE, PAYPAL, ...)
    user_id: int = None
    init_data: str = None


class PaymentResponse(Schema):
    success: bool
    payment_url: str = None
    payment_id: str = None
    invoice_id: str = None
    error: str = None


@miniapp_api.get("/pricing")
def get_pricing(request):
    """Возвращает список активных пакетов токенов для мини-приложения."""
    packages = TokenPackage.objects.filter(is_active=True).order_by('sort_order', 'price_usd')
    return {
        "packages": [
            {
                "code": package.code,
                "title": package.title,
                "credits": int(package.credits),
                "price_usd": float(package.price_usd),
                "stars_amount": package.stars_amount,
            }
            for package in packages
        ]
    }


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
        amount_decimal = Decimal(str(data.amount)).quantize(Decimal('0.01'))
        package = TokenPackage.objects.filter(
            is_active=True,
            price_usd=amount_decimal,
        ).order_by('sort_order').first()

        if not package:
            logger.warning(f"No token package matches amount {amount_decimal}")
            return PaymentResponse(
                success=False,
                error="Пакет с такой суммой не найден. Обновите приложение и попробуйте снова."
            )

        expected_credits = int(package.credits)
        if data.credits != expected_credits:
            logger.warning(
                "Package mismatch: expected %s credits for $%s, got %s",
                expected_credits,
                amount_decimal,
                data.credits,
            )
            return PaymentResponse(
                success=False,
                error="Количество токенов устарело. Обновите приложение и попробуйте снова."
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
                    description=f"Пополнение {expected_credits} кредитов через {data.payment_method}",
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
        logger.info(f"Getting payment URL for credits={expected_credits}, transaction_id={transaction_id}")
        preferred_method = None
        if isinstance(data.payment_method, str):
            candidate = data.payment_method.upper()
            supported = {"BANK131", "SMART_GLOCAL", "PAY2ME", "UNLIMINT", "PAYPAL", "STRIPE"}
            if candidate == "CARD":
                candidate = None
            elif candidate not in supported:
                candidate = None
            preferred_method = candidate

        payment_result = get_payment_url(
            credits=expected_credits,
            transaction_id=transaction_id,
            user_email=data.email,
            payment_method=preferred_method,
            custom_fields={
                "credits": expected_credits,
                "transaction_id": str(transaction_id),
            }
        )

        if not payment_result:
            if user and transaction_id:
                Transaction.objects.filter(id=transaction_id).delete()
            return {
                "success": False,
                "payment_url": None,
                "payment_id": None,
                "error": f"Платежная ссылка для {expected_credits} токенов еще не создана в Lava.top"
            }

        if isinstance(payment_result, dict):
            payment_url = payment_result.get("url")
            contract_id = payment_result.get("payment_id")
        else:
            payment_url = payment_result
            contract_id = None

        if user and transaction_id and (contract_id or isinstance(payment_result, dict)):
            update_fields = {}
            if contract_id:
                update_fields["payment_id"] = contract_id
            raw = payment_result.get("raw") if isinstance(payment_result, dict) else None
            if raw:
                update_fields["payment_data"] = raw
            if update_fields:
                Transaction.objects.filter(id=transaction_id).update(**update_fields)

        logger.info(f"Payment URL generated: {payment_url}")
        response = {
            "success": True,
            "payment_url": payment_url,
            "payment_id": str(contract_id or transaction_id),
            "invoice_id": contract_id,
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

        # Проверка авторизации согласно требованиям Lava.top (Basic + ApiKey)
        auth_header = request.headers.get('Authorization', '')
        api_key_header = request.headers.get('X-API-Key')

        expected_secret = getattr(settings, 'LAVA_WEBHOOK_SECRET', None)
        expected_api_key = getattr(settings, 'LAVA_API_KEY', None)

        def _matches(value, *expected_values):
            return any(value == candidate for candidate in expected_values if candidate)

        auth_present = bool(auth_header)
        api_key_present = api_key_header is not None and api_key_header != ""

        auth_valid = True  # default to true when header not present
        if auth_header:
            header_value = auth_header.strip()
            if header_value.lower().startswith('bearer '):
                token = header_value.split(' ', 1)[1].strip()
                auth_valid = _matches(token, expected_secret, expected_api_key)
            elif header_value.lower().startswith('basic '):
                try:
                    decoded = base64.b64decode(header_value.split(' ', 1)[1]).decode('utf-8')
                    username, _, password = decoded.partition(':')
                    auth_valid = (
                        _matches(password, expected_secret, expected_api_key)
                        or _matches(decoded, expected_secret, expected_api_key)
                        or (not password and _matches(username, expected_secret, expected_api_key))
                    )
                except Exception as exc:
                    logger.warning("Failed to decode Lava webhook basic auth header: %s", exc)
                    auth_valid = False
            else:
                auth_valid = _matches(header_value, expected_secret, expected_api_key)

        api_key_valid = True
        if api_key_present:
            api_key_valid = _matches(api_key_header, expected_api_key, expected_secret)

        if not auth_present and not api_key_present:
            logger.warning("No authorization headers provided for Lava webhook")
            return JsonResponse({"ok": False, "error": "Unauthorized"}, status=401)

        if auth_present and not auth_valid:
            logger.warning("Invalid Lava webhook Authorization header")
            return JsonResponse({"ok": False, "error": "Unauthorized"}, status=401)

        if api_key_present and not api_key_valid:
            logger.warning("Invalid Lava webhook API key header")
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

        # Фиксируем тип события заранее, чтобы использовать ниже даже если транзакция не найдена
        event_type = webhook_data.get('event_type', '') or ''

        # Если транзакция не найдена и это новый платеж, создаем новую
        success_events = {
            'payment.success',
            'subscription.recurring.payment.success'
        }

        if not trans and event_type in success_events:
            # Для новых платежей от Lava.top создаем транзакцию
            logger.info(f"Creating new transaction for Lava.top payment: {order_id}")

            # Пытаемся сопоставить платёж с существующим пользователем
            fallback_chat_id = getattr(settings, "LAVA_FALLBACK_CHAT_ID", None)
            target_user = None
            if fallback_chat_id:
                try:
                    target_user = TgUser.objects.get(chat_id=int(fallback_chat_id))
                except (TgUser.DoesNotExist, ValueError):
                    target_user = None

            if not target_user:
                logger.error("Unable to map Lava webhook to a Telegram user (fallback chat id not configured)")
                return JsonResponse({"ok": False, "error": "User not found for webhook"}, status=500)

            try:
                user_balance, _ = UserBalance.objects.get_or_create(user=target_user)

                trans = Transaction.objects.create(
                    user=target_user,
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
            logger.warning(f"Transaction {order_id} not found for event {event_type}, acknowledging to prevent retries")
            return JsonResponse({"ok": True, "status": "ignored"}, status=200)

        # Проверяем тип события и статус платежа
        payment_status_raw = webhook_data.get('status')
        payment_status = (payment_status_raw or '').lower()

        # Обработка успешных платежей
        if (event_type == 'payment.success' or
            payment_status in ['success', 'paid', 'completed', 'subscription-active']):
            # Платеж успешен - начисляем токены
            with db_transaction.atomic():
                # Блокируем баланс для обновления
                user_balance = UserBalance.objects.select_for_update().get(
                    user=trans.user
                )

                # Начисляем токены по текущему курсу
                credits_amount = usd_to_tokens(trans.amount)
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
                from botapp.telegram import bot

                message_text = (
                    f"✅ **Платеж успешно выполнен!**\n\n"
                    f"💰 Зачислено: {int(credits_amount)} токенов\n"
                    f"💵 Сумма: ${trans.amount}\n\n"
                    f"Ваш новый баланс: {int(user_balance.balance)} токенов\n\n"
                    f"Спасибо за покупку! 🎉\n"
                    f"Теперь вы можете создавать изображения и видео."
                )

                # Отправляем сообщение, не ломая текущий event loop
                async_to_sync(bot.send_message)(
                    chat_id=trans.user.chat_id,
                    text=message_text,
                    parse_mode="Markdown"
                )
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
