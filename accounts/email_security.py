"""Account email tokens, durable delivery and cross-process abuse controls."""

from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import AuthEmailJob, AuthEmailRateLimit
from core.network import client_ip

VERIFY_SALT = "accounts.verify-email.v1"


def email_link(path):
    """Never derive security links from request Host or forwarded headers."""
    base = settings.SITE_URL.rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.query or parsed.fragment
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or (not settings.DEBUG and parsed.scheme != "https")):
        raise ImproperlyConfigured("SITE_URL must be an absolute HTTPS origin (HTTP is permitted only in DEBUG).")
    return base + path


def verification_token(user):
    return signing.dumps({"email": user.email, "nonce": user.email_verification_nonce.hex}, salt=VERIFY_SALT)


def verification_token_valid(user, token):
    if not user or not user.email_verification_required or user.is_active or user.email_verified_at is not None:
        return False
    try:
        data = signing.loads(token, salt=VERIFY_SALT, max_age=settings.EMAIL_VERIFICATION_TIMEOUT)
    except (signing.BadSignature, ValueError, TypeError):
        return False
    return (isinstance(data, dict) and data.get("email") == user.email
            and constant_time_compare(str(data.get("nonce", "")), user.email_verification_nonce.hex))


def verification_path(user):
    return reverse("accounts:verify_email", kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(user.pk)), "token": verification_token(user),
    })


def allow_auth_email(request, email, purpose):
    """Consume both address and trusted client-IP budgets, even for unknown accounts."""
    now = timezone.now()
    window = timedelta(seconds=settings.AUTH_EMAIL_WINDOW_SECONDS)
    # Lock the IP first, then the address, consistently. Reject an exhausted IP
    # before creating new address keys, bounding rows created by a single client.
    budgets = [
        (salted_hmac("auth-email-limit", f"all:ip:{client_ip(request)}").hexdigest(), settings.AUTH_EMAIL_PER_IP),
        (salted_hmac("auth-email-limit", f"{purpose}:email:{email.strip().lower()}").hexdigest(), settings.AUTH_EMAIL_PER_ADDRESS),
    ]
    with transaction.atomic():
        for key, limit in budgets:
            AuthEmailRateLimit.objects.get_or_create(key=key, defaults={"started_at": now})
            bucket = AuthEmailRateLimit.objects.select_for_update().get(pk=key)
            if now - bucket.started_at >= window:
                bucket.started_at, bucket.attempts = now, 0
            if bucket.attempts >= limit:
                return False
            bucket.attempts += 1
            bucket.save(update_fields=["started_at", "attempts"])
    return True


def queue_auth_email(user, purpose):
    return AuthEmailJob.objects.create(
        user=user, purpose=purpose, recipient=user.email,
        credential_fingerprint=user.get_session_auth_hash(), available_at=timezone.now(),
    )


def _deliver(job):
    user = job.user
    if (user.email != job.recipient or not user.has_usable_password()
            or not constant_time_compare(user.get_session_auth_hash(), job.credential_fingerprint)
            or timezone.now() - job.created_at > timedelta(hours=24)):
        return False
    if job.purpose == AuthEmailJob.Purpose.VERIFY:
        if not user.email_verification_required or user.is_active or user.email_verified_at:
            return False
        link = email_link(verification_path(user))
        subject = f"Verify your email address | {settings.SITE_NAME}"
        heading, button = "Confirm your email address", "Verify email address"
        introduction = "Welcome! Confirm this email address to activate your account and securely access your projects."
        expiry = settings.EMAIL_VERIFICATION_TIMEOUT
    else:
        if not user.is_active or (user.email_verification_required and not user.email_verified_at):
            return False
        link = email_link(reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)), "token": default_token_generator.make_token(user),
        }))
        subject = f"Reset your password | {settings.SITE_NAME}"
        heading, button = "Reset your password", "Choose a new password"
        introduction = "We received a request to reset the password for your account. Use the secure link below to choose a new one."
        expiry = settings.PASSWORD_RESET_TIMEOUT
    context = {
        "user": user, "site_name": settings.SITE_NAME, "heading": heading, "button": button,
        "introduction": introduction, "action_url": link, "expiry_minutes": max(1, expiry // 60),
        "verification": job.purpose == AuthEmailJob.Purpose.VERIFY,
    }
    message = EmailMultiAlternatives(
        subject, render_to_string("emails/account_security.txt", context), settings.DEFAULT_FROM_EMAIL, [job.recipient],
    )
    message.attach_alternative(render_to_string("emails/account_security.html", context), "text/html")
    if message.send(fail_silently=False) != 1:
        raise RuntimeError("EmailBackendDidNotAcceptMessage")
    return True


def deliver_auth_emails(limit=50):
    """Lease jobs in PostgreSQL, send outside locks, retry without logging secrets.

    Delivery is at least once: a crash after SMTP acceptance can cause a duplicate.
    Security links remain single-use even if a message is delivered more than once.
    """
    completed = 0
    for _ in range(limit):
        now = timezone.now()
        with transaction.atomic():
            job = (AuthEmailJob.objects.select_for_update(skip_locked=True)
                   .filter(Q(status=AuthEmailJob.Status.PENDING, available_at__lte=now)
                           | Q(status=AuthEmailJob.Status.SENDING, attempted_at__lt=now - timedelta(minutes=5)))
                   .order_by("available_at", "pk").first())
            if job is None:
                break
            job.status, job.attempted_at = AuthEmailJob.Status.SENDING, now
            job.attempts += 1
            job.save(update_fields=["status", "attempted_at", "attempts"])
        try:
            sent = _deliver(job)
        except Exception as exc:
            # Exception messages may contain credentials, addresses or security URLs.
            AuthEmailJob.objects.filter(pk=job.pk, attempted_at=now).update(
                status=AuthEmailJob.Status.FAILED if job.attempts >= 6 else AuthEmailJob.Status.PENDING,
                available_at=now + timedelta(seconds=min(3600, 30 * 2 ** min(job.attempts, 7))),
                error_code=type(exc).__name__[:80],
            )
        else:
            AuthEmailJob.objects.filter(pk=job.pk, attempted_at=now).update(
                status=AuthEmailJob.Status.SENT if sent else AuthEmailJob.Status.CANCELLED,
                sent_at=timezone.now() if sent else None, error_code="",
            )
            completed += 1
    return completed
