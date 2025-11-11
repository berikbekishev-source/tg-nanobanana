import mimetypes
from typing import Any, Dict

import requests
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import DetailView, ListView

from botapp.models import ChatMessage, ChatThread


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Общий миксин для всех вью в панели."""

    login_url = reverse_lazy("admin:login")
    permission_denied_message = _("Недостаточно прав для просмотра панели.")

    def test_func(self) -> bool:
        return self.request.user.is_staff


class ChatListView(StaffRequiredMixin, ListView):
    """Список всех чатов бота."""

    model = ChatThread
    template_name = "dashboard/chat_list.html"
    paginate_by = 25

    def get_queryset(self):
        qs = ChatThread.objects.select_related('user').order_by('-last_message_at', '-updated_at')
        query = self.request.GET.get('q', '').strip()
        if query:
            qs = qs.filter(
                Q(user__username__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__chat_id__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '').strip()
        context['section'] = 'chats'
        return context


class ChatDetailView(StaffRequiredMixin, DetailView):
    """История переписки конкретного пользователя."""

    model = ChatThread
    template_name = "dashboard/chat_detail.html"
    context_object_name = "thread"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        if self.object.unread_count:
            self.object.unread_count = 0
            self.object.save(update_fields=['unread_count', 'updated_at'])
        messages_qs = (
            self.object.messages.select_related('user')
            .order_by('-message_date')[:200]
        )
        context['messages'] = list(reversed(messages_qs))
        context['messages_total'] = self.object.messages.count()
        context['section'] = 'chats'
        return context


class MessageMediaProxyView(StaffRequiredMixin, View):
    """Позволяет просматривать медиа через бота без раскрытия токена."""

    def get(self, request, pk: int, *args, **kwargs):
        message = get_object_or_404(ChatMessage, pk=pk)
        if not message.media_file_id:
            raise Http404("Медиа не найдено")

        file_path = message.media_file_path
        if not file_path:
            file_path = self._fetch_file_path(message.media_file_id)
            message.media_file_path = file_path
            message.save(update_fields=['media_file_path'])

        file_bytes = self._download_file(file_path)
        content_type = message.media_mime_type or mimetypes.guess_type(message.media_file_name)[0] or "application/octet-stream"
        filename = message.media_file_name or f"file_{message.pk}"

        response = HttpResponse(file_bytes, content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    @staticmethod
    def _fetch_file_path(file_id: str) -> str:
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise Http404("Токен Telegram не сконфигурирован")

        url = f"https://api.telegram.org/bot{token}/getFile"
        response = requests.get(url, params={'file_id': file_id}, timeout=10)
        if response.status_code != 200:
            raise Http404("Не удалось получить путь к файлу")
        payload = response.json()
        result = payload.get('result')
        if not result or 'file_path' not in result:
            raise Http404("Telegram не вернул путь к файлу")
        return result['file_path']

    @staticmethod
    def _download_file(file_path: str) -> bytes:
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise Http404("Токен Telegram не сконфигурирован")

        url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            raise Http404("Не удалось скачать файл")
        return response.content
