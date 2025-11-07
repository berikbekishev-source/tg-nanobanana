import base64
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from PIL import Image

from botapp.business.balance import BalanceService, InsufficientBalanceError
from botapp.business.generation import GenerationService
from botapp.models import AIModel, TgUser, Transaction, UserBalance
from botapp.providers.video.base import VideoGenerationError
from botapp.providers.video.openai_sora import OpenAISoraProvider
from botapp.media_utils import detect_reference_mime
from botapp.services import (
    openai_generate_images,
    gemini_vertex_generate,
    gemini_vertex_edit,
    generate_images_for_model,
    OPENAI_IMAGE_EDIT_URL,
)


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
        self.assertTrue(called_urls[0].endswith("/videos"))
        self.assertTrue(called_urls[-1].endswith("/videos/job-123/download"))

    @override_settings(OPENAI_API_KEY=None)
    def test_missing_api_key_raises(self):
        with self.assertRaises(VideoGenerationError):
            OpenAISoraProvider()

    @override_settings(OPENAI_API_KEY="test-key")
    def test_1080p_resolution_maps_to_supported_size(self):
        provider = OpenAISoraProvider()
        json_payload, _, _ = provider._build_create_payload(
            prompt="Test",
            model_name="sora-2",
            generation_type="text2video",
            params={"resolution": "1080p", "aspect_ratio": "16:9"},
            input_media=None,
            input_mime_type=None,
        )
        self.assertIsNotNone(json_payload)
        self.assertEqual(json_payload.get("size"), "1280x720")

    @override_settings(OPENAI_API_KEY="test-key")
    def test_image2video_reference_resized_to_required_dimensions(self):
        provider = OpenAISoraProvider()
        img = Image.new("RGB", (800, 600), color=(255, 0, 0))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        json_payload, form_payload, files = provider._build_create_payload(
            prompt="Test",
            model_name="sora-2",
            generation_type="image2video",
            params={"resolution": "1080p", "aspect_ratio": "9:16"},
            input_media=buffer.getvalue(),
            input_mime_type="image/png",
        )

        self.assertIsNone(json_payload)
        self.assertIsNotNone(form_payload)
        self.assertIsNotNone(files)
        media_bytes = files["input_reference"][1]
        with Image.open(BytesIO(media_bytes)) as processed:
            self.assertEqual(processed.size, (720, 1280))


class OpenAIImageGenerationTests(TestCase):
    @override_settings(OPENAI_API_KEY="test-key")
    @patch("botapp.services.httpx.Client")
    def test_openai_generate_images_decodes_base64(self, client_cls: MagicMock):
        client_instance = MagicMock()
        client_ctx = MagicMock()
        client_ctx.__enter__.return_value = client_instance
        client_ctx.__exit__.return_value = False
        client_cls.return_value = client_ctx

        payload_bytes = base64.b64encode(b"openai-image-bytes").decode("utf-8")
        response = MagicMock()
        response.json.return_value = {"data": [{"b64_json": payload_bytes}]}
        response.raise_for_status.return_value = None
        client_instance.post.return_value = response

        imgs = openai_generate_images(
            "robot illustration",
            1,
            params={"size": "512x512", "quality": "high"},
            model_name="gpt-image-1",
        )

        self.assertEqual(len(imgs), 1)
        self.assertEqual(imgs[0], b"openai-image-bytes")
        post_kwargs = client_instance.post.call_args.kwargs
        self.assertEqual(post_kwargs["json"]["size"], "512x512")
        self.assertEqual(post_kwargs["json"]["model"], "gpt-image-1")
        self.assertEqual(post_kwargs["json"]["quality"], "high")

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("botapp.services.openai_generate_images")
    def test_generate_images_for_model_routes_to_openai(self, openai_mock: MagicMock):
        model = AIModel.objects.create(
            slug="test-openai-image",
            name="GPT Image 1",
            display_name="GPT Image 1",
            type="image",
            provider="openai_image",
            description="",
            short_description="",
            price=Decimal("2.50"),
            api_endpoint="https://api.openai.com/v1/images",
            api_model_name="gpt-image-1",
            max_prompt_length=1000,
            supports_image_input=False,
            max_input_images=0,
            default_params={"size": "1024x1024", "quality": "standard"},
            allowed_params={},
            max_quantity=4,
            cooldown_seconds=0,
        )
        openai_mock.return_value = [b"img"]

        imgs = generate_images_for_model(
            model,
            "city skyline",
            2,
            {"size": "512x512"},
            generation_type="text2image",
        )

        self.assertEqual(imgs, [b"img"])
        self.assertTrue(openai_mock.called)
        call_kwargs = openai_mock.call_args.kwargs
        self.assertEqual(call_kwargs["model_name"], "gpt-image-1")
        self.assertEqual(call_kwargs["params"]["size"], "512x512")

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("botapp.services.httpx.Client")
    def test_openai_generate_images_falls_back_to_auto_quality(self, client_cls: MagicMock):
        client_instance = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = client_instance
        ctx.__exit__.return_value = False
        client_cls.return_value = ctx

        response = MagicMock()
        response.json.return_value = {"data": [{"b64_json": base64.b64encode(b"img").decode()}]}
        response.raise_for_status.return_value = None
        client_instance.post.return_value = response

        openai_generate_images(
            "prompt",
            1,
            params={"quality": "standard", "size": "auto"},
            model_name="gpt-image-1",
        )

        payload = client_instance.post.call_args.kwargs["json"]
        self.assertEqual(payload["quality"], "auto")
        self.assertEqual(payload["size"], "auto")

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("botapp.services.httpx.Client")
    def test_openai_generate_images_accepts_format_and_compression(self, client_cls: MagicMock):
        client_instance = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = client_instance
        ctx.__exit__.return_value = False
        client_cls.return_value = ctx

        response = MagicMock()
        response.json.return_value = {"data": [{"b64_json": base64.b64encode(b"img").decode()}]}
        response.raise_for_status.return_value = None
        client_instance.post.return_value = response

        openai_generate_images(
            "prompt",
            1,
            params={"format": "jpeg", "output_compression": 50},
            model_name="gpt-image-1",
        )
        payload = client_instance.post.call_args.kwargs["json"]
        self.assertEqual(payload["format"], "jpeg")
        self.assertEqual(payload["output_compression"], 50)

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("botapp.services.httpx.Client")
    def test_openai_generate_images_image2image_calls_edit_endpoint(self, client_cls: MagicMock):
        client_instance = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = client_instance
        ctx.__exit__.return_value = False
        client_cls.return_value = ctx

        response = MagicMock()
        response.json.return_value = {"data": [{"b64_json": base64.b64encode(b"img").decode()}]}
        response.raise_for_status.return_value = None
        client_instance.post.return_value = response

        imgs = openai_generate_images(
            "prompt",
            1,
            params={"size": "1024x1024"},
            model_name="gpt-image-1",
            generation_type="image2image",
            input_images=[{"content": b"raw", "mime_type": "image/png", "filename": "input.png"}],
        )

        self.assertEqual(imgs, [b"img"])
        call_args = client_instance.post.call_args
        self.assertEqual(call_args.args[0], OPENAI_IMAGE_EDIT_URL)
        self.assertIn("files", call_args.kwargs)

    def test_generate_images_for_model_image2image_not_supported_provider(self):
        model = AIModel.objects.create(
            slug="gemini-image",
            name="Gemini Image",
            display_name="Gemini Image",
            type="image",
            provider="gemini",
            description="",
            short_description="",
            price=Decimal("1.00"),
            api_endpoint="https://example.com",
            api_model_name="gemini-image",
            max_prompt_length=1000,
            supports_image_input=False,
            max_input_images=0,
            default_params={},
            allowed_params={},
            max_quantity=4,
            cooldown_seconds=0,
        )

        with self.assertRaises(ValueError):
            generate_images_for_model(
                model,
                "prompt",
                1,
                {},
                generation_type="image2image",
                input_images=[{"content": b"x"}],
            )

class ReferenceMimeDetectionTests(TestCase):
    def test_detect_png_signature_when_header_generic(self):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
        mime = detect_reference_mime(png_bytes, "test.png", "application/octet-stream")
        self.assertEqual(mime, "image/png")

    def test_detect_mp4_signature(self):
        mp4_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20
        mime = detect_reference_mime(mp4_bytes, "clip.bin", "application/octet-stream")
        self.assertEqual(mime, "video/mp4")


class GeminiVertexFallbackTests(TestCase):
    @patch("botapp.services._authorized_vertex_session")
    @patch("botapp.services._load_service_account_info")
    def test_generate_falls_back_to_generative_language_api(self, load_info: MagicMock, auth_session: MagicMock):
        load_info.return_value = {"project_id": "demo-project"}
        session = MagicMock()
        auth_session.return_value = session

        vertex_response = MagicMock()
        vertex_response.status_code = 404
        vertex_response.text = "Publisher Model not found"
        vertex_response.json.return_value = {"error": {"message": "not found"}}

        gl_response = MagicMock()
        gl_response.status_code = 200
        gl_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "data": base64.b64encode(b"ok").decode(),
                                }
                            }
                        ]
                    }
                }
            ]
        }

        session.post.side_effect = [vertex_response, gl_response]

        images = gemini_vertex_generate("test prompt", 1)
        self.assertEqual(images, [b"ok"])
        self.assertEqual(session.post.call_count, 2)
        second_call_url = session.post.call_args_list[1].args[0]
        self.assertIn("generativelanguage.googleapis.com", second_call_url)


class GeminiVertexApiKeyTests(TestCase):
    @override_settings(NANO_BANANA_API_KEY="test-key")
    @patch("botapp.services.httpx.post")
    @patch("botapp.services._load_service_account_info")
    def test_generate_uses_api_key_directly(self, load_info: MagicMock, http_post: MagicMock):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {"data": base64.b64encode(b"img").decode()}
                            }
                        ]
                    }
                }
            ]
        }
        http_post.return_value = response

        imgs = gemini_vertex_generate("prompt", 1)

        self.assertEqual(imgs, [b"img"])
        http_post.assert_called_once()
        headers = http_post.call_args.kwargs["headers"]
        self.assertEqual(headers["x-goog-api-key"], "test-key")
        load_info.assert_not_called()

    @override_settings(NANO_BANANA_API_KEY="test-key")
    @patch("botapp.services.httpx.post")
    @patch("botapp.services._load_service_account_info")
    def test_edit_uses_api_key_directly(self, load_info: MagicMock, http_post: MagicMock):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {"data": base64.b64encode(b"edit").decode()}
                            }
                        ]
                    }
                }
            ]
        }
        http_post.return_value = response

        imgs = gemini_vertex_edit(
            "prompt",
            1,
            input_images=[{"content": b"raw", "mime_type": "image/png"}],
        )

        self.assertEqual(imgs, [b"edit"])
        http_post.assert_called_once()
        headers = http_post.call_args.kwargs["headers"]
        self.assertEqual(headers["x-goog-api-key"], "test-key")
        load_info.assert_not_called()
