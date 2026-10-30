from django.conf import settings
from django.core.management.base import BaseCommand

from core.chunked_uploads import expire_stale_uploads


class Command(BaseCommand):
    help = "Delete chunked uploads (and their partial files) untouched for UPLOAD_SESSION_HOURS."

    def handle(self, *args, **options):
        removed = expire_stale_uploads()
        self.stdout.write(f"Removed {removed} upload(s) older than {settings.UPLOAD_SESSION_HOURS} hours.")
