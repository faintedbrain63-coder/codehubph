import time
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from accounts.email_security import deliver_auth_emails, email_link
from accounts.models import AuthEmailJob, AuthEmailRateLimit


class Command(BaseCommand):
    help = "Deliver queued account-security emails. Use --loop under a process supervisor."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        try:
            email_link("/")
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from None
        if settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and not all((settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)):
            raise CommandError("Set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in .env before starting SMTP delivery.")
        if options["limit"] < 1 or options["limit"] > 1000:
            self.stderr.write("--limit must be between 1 and 1000.")
            return
        try:
            while True:
                close_old_connections()
                processed = deliver_auth_emails(options["limit"])
                # Bound retention of recipient addresses and keyed request counters.
                AuthEmailRateLimit.objects.filter(started_at__lt=timezone.now() - timedelta(days=1)).delete()
                AuthEmailJob.objects.filter(created_at__lt=timezone.now() - timedelta(days=30)).delete()
                if not options["loop"]:
                    self.stdout.write(f"Processed {processed} queued email job(s).")
                    break
                time.sleep(3)
        except KeyboardInterrupt:
            self.stdout.write("Email worker stopped.")
