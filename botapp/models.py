from django.db import models


class TgUser(models.Model):
    chat_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Telegram User"
        verbose_name_plural = "Telegram Users"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.username or 'Unknown'} ({self.chat_id})"


class GenRequest(models.Model):
    run_code = models.CharField(max_length=64, db_index=True)
    chat_id = models.BigIntegerField()
    prompt = models.TextField()
    quantity = models.PositiveSmallIntegerField(default=1)
    model = models.CharField(max_length=64, default="gemini-2.5-flash-image")
    status = models.CharField(max_length=16, default="queued")  # queued|done|error
    result_urls = models.JSONField(default=list)                # публичные URL из Supabase Storage
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Generation Request"
        verbose_name_plural = "Generation Requests"
        ordering = ['-created_at']

    def __str__(self):
        return f"Request {self.id}: {self.prompt[:50]}... ({self.status})"

