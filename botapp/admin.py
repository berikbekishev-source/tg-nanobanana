from django.contrib import admin
from .models import TgUser, GenRequest


@admin.register(TgUser)
class TgUserAdmin(admin.ModelAdmin):
    list_display = ('chat_id', 'username', 'created_at')
    search_fields = ('chat_id', 'username')
    list_filter = ('created_at',)
    ordering = ('-created_at',)


@admin.register(GenRequest)
class GenRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_id', 'model', 'status', 'quantity', 'created_at')
    search_fields = ('chat_id', 'prompt', 'run_code')
    list_filter = ('status', 'model', 'created_at')
    readonly_fields = ('created_at', 'result_urls')
    ordering = ('-created_at',)

    fieldsets = (
        ('Request Info', {
            'fields': ('run_code', 'chat_id', 'status')
        }),
        ('Generation Details', {
            'fields': ('prompt', 'model', 'quantity')
        }),
        ('Results', {
            'fields': ('result_urls', 'created_at')
        }),
    )
