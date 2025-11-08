from celery import current_app
from django.core.management.base import BaseCommand
from botapp.models import GenRequest

IMAGE_TYPES = {"text2image", "image2image"}

class Command(BaseCommand):
    help = "Re-enqueue queued generation requests"

    def handle(self, *args, **options):
        queued = GenRequest.objects.filter(status="queued").order_by("created_at")
        if not queued.exists():
            self.stdout.write("No queued requests")
            return
        app = current_app
        for req in queued:
            if req.generation_type in IMAGE_TYPES:
                task_name = "botapp.tasks.generate_image_task"
                task = "image"
            else:
                task_name = "botapp.tasks.generate_video_task"
                task = "video"
            app.send_task(task_name, args=[req.id])
            self.stdout.write(f"Requeued {task} request #{req.id}")
        self.stdout.write(self.style.SUCCESS("Done"))
