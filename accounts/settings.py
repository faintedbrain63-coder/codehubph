"""Shared profile and password updates for customer and staff settings."""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm

from accounts.forms import ProfileForm


def account_settings_forms(request):
    """Bind only the submitted form, and keep the current session after a password change."""
    action = request.POST.get("action") if request.method == "POST" else None
    profile_form = ProfileForm(request.POST if action == "profile" else None, instance=request.user)
    if request.user.is_staff:
        profile_form.fields.pop("school")
    password_form = PasswordChangeForm(request.user, request.POST if action == "password" else None)
    password_form.fields["old_password"].label = "Current password"
    # The combined page should open at the profile, rather than scroll to this field on mobile.
    password_form.fields["old_password"].widget.attrs.pop("autofocus", None)
    success_message = None
    if action == "profile" and profile_form.is_valid():
        profile_form.save()
        success_message = "Your profile has been updated."
    elif action == "password" and password_form.is_valid():
        user = password_form.save()
        update_session_auth_hash(request, user)
        success_message = "Your password has been changed."
    return {"profile_form": profile_form, "password_form": password_form}, success_message
