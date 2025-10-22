from django.db import models

class TgUser(models.Model):
    chat_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

class GenRequest(models.Model):
    run_code = models.CharField(max_length=64, db_index=True)
    chat_id = models.BigIntegerField()
    prompt = models.TextField()
    quantity = models.PositiveSmallIntegerField(default=1)
    model = models.CharField(max_length=64, default="gemini-2.5-flash-image")
    status = models.CharField(max_length=16, default="queued")  # queued|done|error
    result_urls = models.JSONField(default=list)                # публичные URL из Supabase Storage
    created_at = models.DateTimeField(auto_now_add=True)

