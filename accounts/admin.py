from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import User
from accounts.forms import EmailAdminUserCreationForm


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = EmailAdminUserCreationForm
    list_display = ("email", "first_name", "last_name", "is_staff", "date_joined")
    search_fields = ("email", "first_name", "last_name", "school")
    ordering = ("email",)
    readonly_fields = ("legal_accepted_at", "privacy_policy_version", "license_agreement_version")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number", "school")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        ("Registration agreements", {"fields": readonly_fields}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "usable_password", "password1", "password2")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number", "school")}),
    )
