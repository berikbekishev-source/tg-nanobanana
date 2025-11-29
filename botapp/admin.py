import mimetypes

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from django.urls import path, reverse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.core.paginator import Paginator
from .models import (
    TgUser, GenRequest, UserBalance, AIModel,
    Transaction, UserSettings, Promocode, PricingSettings,
    ChatThread, ChatMessage, BotErrorEvent,
)


@admin.register(TgUser)
class TgUserAdmin(admin.ModelAdmin):
    list_display = ('chat_id', 'username', 'first_name', 'last_name',
                    'language_code', 'is_premium', 'is_blocked', 'created_at')
    search_fields = ('chat_id', 'username', 'first_name', 'last_name')
    list_filter = ('is_premium', 'is_blocked', 'language_code', 'created_at')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('User Info', {
            'fields': ('chat_id', 'username', 'first_name', 'last_name')
        }),
        ('Settings', {
            'fields': ('language_code', 'is_premium', 'is_blocked')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            generation_count=Count('generations'),
            transaction_count=Count('transactions')
        )


@admin.register(UserBalance)
class UserBalanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'bonus_balance', 'total_spent',
                    'total_deposited', 'referral_code', 'created_at')
    search_fields = ('user__username', 'user__chat_id', 'referral_code')
    list_filter = ('created_at',)
    raw_id_fields = ('user', 'referred_by')
    readonly_fields = ('referral_code', 'created_at', 'updated_at')

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Balance', {
            'fields': ('balance', 'bonus_balance', 'total_spent', 'total_deposited')
        }),
        ('Referral', {
            'fields': ('referral_code', 'referred_by', 'referral_earnings')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'referred_by')


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ('slug', 'display_name', 'type', 'provider', 'cost_unit', 'base_cost_usd', 'price',
                    'is_active', 'is_beta', 'order', 'total_generations')
    search_fields = ('slug', 'name', 'display_name', 'description')
    list_filter = ('type', 'provider', 'is_active', 'is_beta')
    ordering = ('order', 'name')
    readonly_fields = (
        'price',
        'total_generations',
        'total_errors',
        'average_generation_time',
        'created_at',
        'updated_at',
    )

    fieldsets = (
        ('Basic Info', {
            'fields': ('slug', 'name', 'display_name', 'type', 'provider')
        }),
        ('Descriptions', {
            'fields': ('description', 'short_description')
        }),
        ('Pricing', {
            'fields': ('cost_unit', 'base_cost_usd', 'unit_cost_usd', 'price')
        }),
        ('Technical Settings', {
            'fields': ('api_endpoint', 'api_model_name', 'max_prompt_length',
                      'supports_image_input', 'max_input_images')
        }),
        ('Generation Parameters', {
            'fields': ('default_params', 'allowed_params')
        }),
        ('Limitations', {
            'fields': ('max_quantity', 'cooldown_seconds', 'daily_limit')
        }),
        ('Management', {
            'fields': ('is_active', 'is_beta', 'min_user_level', 'order')
        }),
        ('Statistics', {
            'fields': ('total_generations', 'total_errors', 'average_generation_time')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    actions = ['activate_models', 'deactivate_models']

    def activate_models(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} model(s) activated.')
    activate_models.short_description = "Activate selected models"

    def deactivate_models(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} model(s) deactivated.')
    deactivate_models.short_description = "Deactivate selected models"


@admin.register(PricingSettings)
class PricingSettingsAdmin(admin.ModelAdmin):
    list_display = ('usd_to_token_rate', 'markup_multiplier', 'updated_at')
    readonly_fields = ('updated_at',)

    fieldsets = (
        (None, {
            'fields': ('usd_to_token_rate', 'markup_multiplier', 'updated_at')
        }),
    )

    def has_add_permission(self, request):
        if PricingSettings.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(GenRequest)
class GenRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'chat_id', 'generation_type', 'ai_model_name',
                    'status', 'cost', 'cost_usd', 'quantity', 'created_at')
    search_fields = ('chat_id', 'prompt', 'run_code', 'user__username')
    list_filter = ('status', 'generation_type', 'ai_model', 'created_at')
    readonly_fields = (
        'run_code',
        'created_at',
        'started_at',
        'completed_at',
        'processing_time',
        'result_urls',
        'file_sizes',
        'provider_job_id',
        'provider_metadata',
        'source_media',
    )
    raw_id_fields = ('user', 'ai_model', 'transaction')
    ordering = ('-created_at',)

    fieldsets = (
        ('Request Info', {
            'fields': ('run_code', 'user', 'chat_id', 'status', 'generation_type')
        }),
        ('Model & Prompt', {
            'fields': ('ai_model', 'prompt', 'input_images', 'generation_params')
        }),
        ('Generation Details', {
            'fields': ('quantity', 'duration', 'video_resolution', 'aspect_ratio')
        }),
        ('Financial', {
            'fields': ('cost', 'cost_usd', 'transaction')
        }),
        ('Provider', {
            'fields': ('provider_job_id', 'provider_metadata', 'source_media')
        }),
        ('Results', {
            'fields': ('result_urls', 'file_sizes', 'error_message')
        }),
        ('Performance', {
            'fields': ('processing_time', 'created_at', 'started_at', 'completed_at')
        }),
    )

    def ai_model_name(self, obj):
        return obj.ai_model.display_name if obj.ai_model else 'N/A'
    ai_model_name.short_description = 'Model'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'ai_model', 'transaction')

    actions = ['retry_failed_requests']

    def retry_failed_requests(self, request, queryset):
        failed = queryset.filter(status='error')
        for req in failed:
            req.status = 'queued'
            req.save()
            # Здесь нужно будет вызвать Celery task
        self.message_user(request, f'{failed.count()} request(s) queued for retry.')
    retry_failed_requests.short_description = "Retry failed requests"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'type', 'formatted_amount', 'balance_after',
                    'payment_method', 'is_completed', 'created_at')
    search_fields = ('user__username', 'user__chat_id', 'payment_id', 'description')
    list_filter = ('type', 'payment_method', 'is_completed', 'is_pending', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'generation_request', 'related_transaction')
    ordering = ('-created_at',)

    fieldsets = (
        ('Transaction Info', {
            'fields': ('user', 'type', 'amount', 'balance_after')
        }),
        ('Description', {
            'fields': ('description', 'description_en')
        }),
        ('Payment', {
            'fields': ('payment_method', 'payment_id', 'payment_data')
        }),
        ('Relations', {
            'fields': ('generation_request', 'related_transaction')
        }),
        ('Status', {
            'fields': ('is_completed', 'is_pending')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def formatted_amount(self, obj):
        color = 'green' if obj.amount > 0 else 'red'
        sign = '+' if obj.amount > 0 else ''
        return format_html(
            '<span style="color: {};">{}{}</span>',
            color,
            sign,
            obj.amount
        )
    formatted_amount.short_description = 'Amount'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'generation_request')

    actions = ['mark_as_completed', 'mark_as_pending']

    def mark_as_completed(self, request, queryset):
        updated = queryset.update(is_completed=True, is_pending=False)
        self.message_user(request, f'{updated} transaction(s) marked as completed.')
    mark_as_completed.short_description = "Mark as completed"

    def mark_as_pending(self, request, queryset):
        updated = queryset.update(is_completed=False, is_pending=True)
        self.message_user(request, f'{updated} transaction(s) marked as pending.')
    mark_as_pending.short_description = "Mark as pending"


@admin.register(BotErrorEvent)
class BotErrorEventAdmin(admin.ModelAdmin):
    list_display = (
        'occurred_at',
        'origin',
        'severity',
        'status',
        'chat_id',
        'handler',
        'short_message',
    )
    list_filter = ('origin', 'severity', 'status', 'occurred_at')
    search_fields = ('message', 'handler', 'error_class', 'chat_id', 'user__username')
    readonly_fields = ('occurred_at', 'created_at', 'updated_at', 'stacktrace', 'payload', 'extra')
    raw_id_fields = ('user', 'gen_request')
    ordering = ('-occurred_at',)
    actions = ['mark_in_progress', 'mark_resolved']

    fieldsets = (
        ('Общее', {
            'fields': ('origin', 'severity', 'status', 'occurred_at', 'handler', 'error_class')
        }),
        ('Сообщение', {
            'fields': ('message', 'stacktrace')
        }),
        ('Связи', {
            'fields': ('user', 'chat_id', 'username_snapshot', 'gen_request')
        }),
        ('Контекст', {
            'fields': ('payload', 'extra', 'created_at', 'updated_at')
        }),
    )

    def short_message(self, obj):
        return (obj.message or obj.error_class)[:60]
    short_message.short_description = "Message"

    def mark_in_progress(self, request, queryset):
        updated = queryset.update(status=BotErrorEvent.Status.IN_PROGRESS)
        self.message_user(request, f"{updated} ошибке(ам) присвоен статус In progress")
    mark_in_progress.short_description = "Отметить как in_progress"

    def mark_resolved(self, request, queryset):
        updated = queryset.update(status=BotErrorEvent.Status.RESOLVED)
        self.message_user(request, f"{updated} ошибке(ам) присвоен статус Resolved")
    mark_resolved.short_description = "Отметить как resolved"


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'interface_language', 'notifications_enabled',
                    'user_level', 'total_generations', 'last_generation_at')
    search_fields = ('user__username', 'user__chat_id')
    list_filter = ('interface_language', 'notifications_enabled', 'user_level')
    raw_id_fields = ('user', 'preferred_image_model', 'preferred_video_model')
    readonly_fields = (
        'total_generations',
        'total_images_generated',
        'total_videos_generated',
        'daily_reward_streak',
        'last_daily_reward_at',
        'created_at',
        'updated_at',
    )

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Notifications', {
            'fields': ('notifications_enabled', 'notify_on_completion',
                      'notify_on_bonus', 'notify_on_news')
        }),
        ('Preferences', {
            'fields': ('interface_language', 'default_image_quantity',
                      'default_video_duration', 'preferred_image_model',
                      'preferred_video_model')
        }),
        ('Statistics', {
            'fields': (
                'total_generations',
                'total_images_generated',
                'total_videos_generated',
                'last_generation_at',
                'daily_reward_streak',
                'last_daily_reward_at',
            )
        }),
        ('Gamification', {
            'fields': ('user_level', 'experience_points', 'achievements')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user')


@admin.register(Promocode)
class PromocodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'formatted_value', 'is_active', 'current_uses',
                    'max_uses', 'valid_from', 'valid_until', 'total_bonus_given')
    search_fields = ('code', 'description')
    list_filter = ('is_active', 'is_percentage', 'valid_from', 'valid_until')
    readonly_fields = ('current_uses', 'total_activated', 'total_bonus_given',
                      'created_at', 'updated_at')
    ordering = ('-created_at',)

    fieldsets = (
        ('Basic Info', {
            'fields': ('code', 'description')
        }),
        ('Value Settings', {
            'fields': ('is_percentage', 'value', 'min_deposit')
        }),
        ('Usage Limits', {
            'fields': ('max_uses', 'max_uses_per_user', 'current_uses')
        }),
        ('Validity Period', {
            'fields': ('valid_from', 'valid_until', 'is_active')
        }),
        ('Statistics', {
            'fields': ('total_activated', 'total_bonus_given')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def formatted_value(self, obj):
        if obj.is_percentage:
            return f'{obj.value}%'
        return f'{obj.value} токенов'
    formatted_value.short_description = 'Value'

    actions = ['activate_promocodes', 'deactivate_promocodes']

    def activate_promocodes(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} promocode(s) activated.')
    activate_promocodes.short_description = "Activate selected promocodes"

    def deactivate_promocodes(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} promocode(s) deactivated.')
    deactivate_promocodes.short_description = "Deactivate selected promocodes"


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ('user_dialog_link', 'last_message_preview', 'last_message_direction',
                    'last_message_at', 'unread_count', 'dialog_link')
    list_display_links = ('user_dialog_link',)
    search_fields = ('user__username', 'user__chat_id', 'user__first_name', 'user__last_name')
    ordering = ('-last_message_at',)
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('user',)
    WEBAPP_LABELS = {
        "midjourney_settings": "Midjourney",
        "gpt_image_settings": "GPT Image",
        "nano_banana_settings": "Nano Banana",
        "kling_settings": "Kling",
        "veo_video_settings": "Veo",
        "sora2_settings": "Sora 2",
    }

    @staticmethod
    def last_message_preview(obj):
        preview = obj.last_message_text or ""
        return (preview[:50] + '...') if len(preview) > 53 else preview
    last_message_preview.short_description = "Последнее сообщение"

    def dialog_link(self, obj):
        url = reverse('admin:botapp_chatthread_dialog', args=[obj.pk])
        return format_html('<a class="button" href="{}">История</a>', url)
    dialog_link.short_description = 'Диалог'

    def user_dialog_link(self, obj):
        url = reverse('admin:botapp_chatthread_dialog', args=[obj.pk])
        label = obj.user.username or obj.user.first_name or obj.user.last_name or f"ID {obj.user.chat_id}"
        subtitle = f"ID {obj.user.chat_id}"
        return format_html(
            '<div class="user-dialog-cell"><a class="user-dialog-link" href="{}">{}</a>'
            '<div class="user-dialog-sub">{}</div></div>',
            url,
            label,
            subtitle,
        )
    user_dialog_link.short_description = "Пользователь"
    user_dialog_link.admin_order_field = 'user__username'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:thread_id>/dialog/',
                self.admin_site.admin_view(self.dialog_view),
                name='botapp_chatthread_dialog',
            ),
        ]
        return custom + urls

    def dialog_view(self, request, thread_id: int):
        thread = get_object_or_404(ChatThread.objects.select_related('user'), pk=thread_id)
        messages_qs = thread.messages.select_related('user').order_by('-message_date', '-id')

        paginator = Paginator(messages_qs, 200)
        page_number = request.GET.get('page') or 1
        page_obj = paginator.get_page(page_number)

        chat_messages = list(reversed(self._prepare_messages(page_obj.object_list)))


        display_name = (thread.user.first_name or thread.user.username or "").strip()
        if not display_name:
            display_name = f"ID {thread.user.chat_id}"
        normalized_name = display_name.strip()
        avatar_letter = normalized_name[0].upper() if normalized_name else "#"

        context = {
            **self.admin_site.each_context(request),
            "thread": thread,
            "chat_messages": chat_messages,
            "messages_total": paginator.count,
            "messages_shown": len(chat_messages),
            "messages_page": page_obj.number,
            "messages_has_older": page_obj.has_next(),
            "messages_has_newer": page_obj.has_previous(),
            "messages_older_page": page_obj.next_page_number() if page_obj.has_next() else None,
            "messages_newer_page": page_obj.previous_page_number() if page_obj.has_previous() else None,
            "user_display_name": display_name,
            "user_avatar": avatar_letter,
            "bot_display_name": "NanoBanana бот",
            "bot_avatar": "NB",
            "title": f"Диалог с {thread.user.username or thread.user.chat_id}",
        }
        return TemplateResponse(request, "admin/botapp/chatthread/dialog.html", context)

    @classmethod
    def _prepare_messages(cls, messages_qs):
        prepared = []
        for msg in messages_qs:
            media_kind = cls._detect_media_kind(msg)
            webapp_label = cls._extract_webapp_label(msg)
            display_text = (msg.text or "").strip()
            if not display_text and webapp_label:
                display_text = f"Отправлен запрос на генерацию через Webapp {webapp_label}"
            msg.media_kind = media_kind
            msg.webapp_label = webapp_label
            msg.display_text = display_text
            prepared.append(msg)
        return prepared

    @staticmethod
    def _detect_media_kind(message):
        mime = (message.media_mime_type or "").lower()
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"

        if message.media_file_name:
            guessed, _ = mimetypes.guess_type(message.media_file_name)
            if guessed:
                guessed = guessed.lower()
                if guessed.startswith("image/"):
                    return "image"
                if guessed.startswith("video/"):
                    return "video"
        return "file"

    @classmethod
    def _extract_webapp_label(cls, message):
        payload = message.payload if isinstance(message.payload, dict) else {}
        webapp_payload = payload.get("web_app") or {}
        label = webapp_payload.get("label") or payload.get("web_app_label")
        kind = webapp_payload.get("kind") or payload.get("web_app_kind")
        model_slug = webapp_payload.get("model_slug") or payload.get("model_slug")

        if not label and kind:
            label = cls.WEBAPP_LABELS.get(kind)

        if not label and model_slug:
            normalized = str(model_slug).replace("_", " ").replace("-", " ").strip()
            if normalized:
                label = normalized.title()

        if not label and payload.get("content_type") == "web_app_data":
            label = "WebApp"
        return label


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('thread', 'direction', 'message_type', 'short_text', 'message_date')
    search_fields = ('thread__user__username', 'thread__user__chat_id', 'text')
    list_filter = ('direction', 'message_type')
    ordering = ('-message_date',)
    raw_id_fields = ('thread', 'user')
    readonly_fields = (
        'thread',
        'user',
        'direction',
        'message_type',
        'text',
        'media_file_id',
        'media_file_name',
        'payload',
        'message_date',
        'created_at',
    )

    @staticmethod
    def short_text(obj):
        return (obj.text[:60] + '...') if obj.text and len(obj.text) > 63 else (obj.text or '')
    short_text.short_description = 'Text'


# Настройка админ-панели
admin.site.site_header = "TG NanoBanana Admin"
admin.site.site_title = "TG NanoBanana"
admin.site.index_title = "Bot Administration"
