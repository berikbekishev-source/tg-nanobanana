from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.business.generation import GenerationService
from botapp.models import AIModel, TgUser, Transaction, UserBalance
from botapp.providers.video.base import VideoGenerationError
from botapp.providers.video.openai_sora import OpenAISoraProvider


class BalanceServiceTests(TestCase):
    def setUp(self):
        self.user = TgUser.objects.create(
            chat_id=123456,
            username="tester",
            first_name="Test",
            language_code="ru",
        )
        self.model = AIModel.objects.create(
            slug="test-model",
            name="Test Model",
            display_name="Test Model",
            type="image",
            provider="gemini",
            description="Test description",
            short_description="Short",
            price=Decimal("2.50"),
            api_endpoint="https://example.com",
            api_model_name="test-model",
            max_prompt_length=1000,
            supports_image_input=False,
            max_input_images=0,
            default_params={},
            allowed_params={},
            max_quantity=4,
            cooldown_seconds=0,
        )

    def test_welcome_bonus_issued_once(self):
        balance = BalanceService.ensure_balance(self.user)
        self.assertEqual(balance.balance, Decimal("5.00"))
        bonus_transactions = Transaction.objects.filter(user=self.user, type="bonus")
        self.assertEqual(bonus_transactions.count(), 1)

        # Повторный вызов не должен создавать новых бонусов
        BalanceService.ensure_balance(self.user)
        self.assertEqual(Transaction.objects.filter(user=self.user, type="bonus").count(), 1)

    def test_charge_for_generation_updates_balance(self):
        BalanceService.ensure_balance(self.user)
        BalanceService.add_deposit(
            self.user,
            amount=Decimal("10.00"),
            payment_method="test",
            description="Manual deposit",
        )

        tx = BalanceService.charge_for_generation(self.user, self.model, quantity=2)
        self.assertEqual(tx.amount, Decimal("-5.00"))

        balance = UserBalance.objects.get(user=self.user)
        # 5 welcome + 10 deposit - 5 generation
        self.assertEqual(balance.balance, Decimal("10.00"))
        self.assertEqual(balance.total_spent, Decimal("5.00"))

    def test_charge_for_generation_insufficient(self):
        BalanceService.ensure_balance(self.user)
        expensive_model = AIModel.objects.create(
            slug="expensive",
            name="Expensive",
            display_name="Expensive",
            type="image",
            provider="gemini",
            description="Expensive model",
            short_description="Expensive",
            price=Decimal("10.00"),
            api_endpoint="https://example.com",
            api_model_name="expensive",
            max_prompt_length=1000,
            supports_image_input=False,
            max_input_images=0,
            default_params={},
            allowed_params={},
            max_quantity=1,
            cooldown_seconds=0,
        )

        with self.assertRaises(InsufficientBalanceError):
            BalanceService.charge_for_generation(self.user, expensive_model)

    def test_complete_deposit_triggers_first_bonus(self):
        tx = BalanceService.create_transaction(
            self.user,
            amount=Decimal("20.00"),
            transaction_type="deposit",
            description="Webhook deposit",
            payment_method="card",
        )
        BalanceService.complete_transaction(tx, status="completed")

        balance = UserBalance.objects.get(user=self.user)
        # 5 welcome + 20 deposit + 4 (20% бонус)
        self.assertEqual(balance.balance, Decimal("29.00"))

        bonus_tx = Transaction.objects.filter(
            user=self.user, type="bonus", description__icontains="первое пополнение"
        ).first()
        self.assertIsNotNone(bonus_tx)
        self.assertEqual(bonus_tx.amount, Decimal("4.00"))

    def test_refund_generation_restores_balance(self):
        BalanceService.add_deposit(
            self.user,
            amount=Decimal("10.00"),
            payment_method="test",
            description="Manual deposit",
        )
        charge_tx = BalanceService.charge_for_generation(self.user, self.model)

        refund_tx = BalanceService.refund_generation(
            self.user,
            charge_tx,
            reason="API error",
        )
        self.assertEqual(refund_tx.amount, Decimal("2.50"))

        balance = UserBalance.objects.get(user=self.user)
        # 5 welcome + 10 deposit - 2.5 + 2.5 refund
        self.assertEqual(balance.balance, Decimal("15.00"))
        self.assertEqual(balance.total_spent, Decimal("0.00"))


class GenerationServiceTests(TestCase):
    def setUp(self):
        self.user = TgUser.objects.create(
            chat_id=987654,
            username="videotester",
            first_name="Video",
            language_code="ru",
        )
        self.video_model = AIModel.objects.create(
            slug="veo3-fast-test",
            name="Veo 3.1 Fast",
            display_name="Veo 3.1 Fast",
            type="video",
            provider="veo",
            description="",
            short_description="",
            price=Decimal("19.00"),
            api_endpoint="",
            api_model_name="veo-3.1-fast",
            max_prompt_length=1000,
            supports_image_input=True,
            max_input_images=1,
            default_params={
                "duration": 8,
                "resolution": "720p",
                "aspect_ratio": "9:16",
                "fps": 24,
            },
            allowed_params={},
            max_quantity=1,
            cooldown_seconds=0,
        )

    def test_create_video_request(self):
        BalanceService.add_deposit(
            self.user,
            amount=Decimal("50.00"),
            payment_method="test",
            description="Manual deposit",
        )

        req = GenerationService.create_generation_request(
            user=self.user,
            ai_model=self.video_model,
            prompt="Test video prompt",
            generation_type="text2video",
            generation_params={
                "duration": 8,
                "resolution": "720p",
                "aspect_ratio": "9:16",
            },
        )

        self.assertEqual(req.duration, 8)
        self.assertEqual(req.video_resolution, "720p")
        self.assertEqual(req.aspect_ratio, "9:16")
        self.assertEqual(req.cost, Decimal("19.00"))
        self.assertIsNotNone(req.transaction)


class OpenAISoraProviderTests(TestCase):
    @override_settings(
        OPENAI_API_KEY="test-key",
        OPENAI_API_BASE="https://api.openai.com/v1",
        OPENAI_VIDEO_POLL_INTERVAL=1,
        OPENAI_VIDEO_POLL_TIMEOUT=30,
    )
    @patch("botapp.providers.video.openai_sora.time.sleep", return_value=None)
    @patch("botapp.providers.video.openai_sora.httpx.Client")
    def test_generate_video_success(self, client_cls: MagicMock, _sleep: MagicMock):
        client_instance = MagicMock()
        client_ctx_manager = MagicMock()
        client_ctx_manager.__enter__.return_value = client_instance
        client_ctx_manager.__exit__.return_value = False
        client_cls.return_value = client_ctx_manager

        post_response = MagicMock()
        post_response.json.return_value = {"id": "job-123", "status": "queued"}
        post_response.headers = {}
        post_response.content = b""
        post_response.raise_for_status.return_value = None

        poll_response_running = MagicMock()
        poll_response_running.json.return_value = {"id": "job-123", "status": "processing"}
        poll_response_running.headers = {}
        poll_response_running.content = b""
        poll_response_running.raise_for_status.return_value = None

        poll_response_done = MagicMock()
        poll_response_done.json.return_value = {
            "id": "job-123",
            "status": "succeeded",
            "seconds": "12",
            "size": "1080x1920",
        }
        poll_response_done.headers = {}
        poll_response_done.content = b""
        poll_response_done.raise_for_status.return_value = None

        content_response = MagicMock()
        content_response.content = b"binary-video-data"
        content_response.headers = {"content-type": "video/mp4"}
        content_response.raise_for_status.return_value = None

        client_instance.request.side_effect = [
            post_response,
            poll_response_running,
            poll_response_done,
            content_response,
        ]

        provider = OpenAISoraProvider()
        result = provider.generate(
            prompt="Create a sunset skyline",
            model_name="sora-2",
            generation_type="text2video",
            params={"duration": 8, "resolution": "720p", "aspect_ratio": "16:9"},
        )

        first_request_kwargs = client_instance.request.call_args_list[0].kwargs
        self.assertEqual(
            first_request_kwargs.get("json"),
            {
                "prompt": "Create a sunset skyline",
                "model": "sora-2",
                "seconds": "8",
                "size": "1280x720",
            },
        )
        self.assertNotIn("duration", first_request_kwargs.get("json", {}))
        self.assertIsNone(first_request_kwargs.get("data"))
        self.assertIsNone(first_request_kwargs.get("files"))

        self.assertEqual(result.content, b"binary-video-data")
        self.assertEqual(result.mime_type, "video/mp4")
        self.assertEqual(result.duration, 12)
        self.assertEqual(result.resolution, "1080p")
        self.assertEqual(result.aspect_ratio, "9:16")
        self.assertEqual(result.provider_job_id, "job-123")
        self.assertIn("job", result.metadata)
        self.assertEqual(client_instance.request.call_count, 4)

        called_urls = [call.args[1] for call in client_instance.request.call_args_list]
        self.assertTrue(called_urls[0].endswith("/video/generations"))
        self.assertTrue(called_urls[1].endswith("/video/generations/job-123"))
        self.assertTrue(called_urls[-1].endswith("/video/generations/job-123/content"))

    @override_settings(OPENAI_API_KEY=None)
    def test_missing_api_key_raises(self):
        with self.assertRaises(VideoGenerationError):
            OpenAISoraProvider()
