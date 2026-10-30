from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


def lockout_email(request, credentials=None):
    """Normalize email for both the storefront and Django's admin login form."""
    identifier = (credentials or {}).get("email") or (credentials or {}).get("username")
    if identifier is None:
        data = getattr(request, "POST", {})
        identifier = data.get("email") or data.get("username", "")
    return str(identifier or "").strip().lower()


class EmailBackend(ModelBackend):
    """Authenticate exclusively by email; username is Django's internal credential argument."""

    def user_can_authenticate(self, user):
        return (super().user_can_authenticate(user)
                and (not user.email_verification_required or user.email_verified_at is not None))

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        User = get_user_model()
        identifier = email if email is not None else username
        if not identifier or password is None:
            return None
        try:
            user = User.objects.get_by_natural_key(identifier)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            User().set_password(password)  # equalise timing to avoid user enumeration
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
