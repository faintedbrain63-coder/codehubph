from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import User, AuthEmailJob
from django.utils import timezone
from accounts.forms import EmailAdminUserCreationForm


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = EmailAdminUserCreationForm
    list_display = ("email", "first_name", "last_name", "is_active", "email_verified_at", "is_staff", "date_joined")
    search_fields = ("email", "first_name", "last_name", "school")
    ordering = ("email",)
    readonly_fields = ("legal_accepted_at", "privacy_policy_version", "license_agreement_version")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number", "school")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        ("Registration agreements", {"fields": readonly_fields}),
        ("Email verification", {"fields": ("email_verification_required", "email_verified_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + ("email_verification_required", "email_verified_at")

    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "usable_password", "password1", "password2")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number", "school")}),
    )


@admin.register(AuthEmailJob)
class AuthEmailJobAdmin(admin.ModelAdmin):
    list_display = ("id", "purpose", "status", "attempts", "created_at", "sent_at", "error_code")
    list_filter = ("status", "purpose")
    readonly_fields = ("user", "purpose", "recipient", "status", "created_at", "available_at", "attempted_at", "sent_at", "attempts", "error_code")
    fields = readonly_fields
    actions = ("retry_failed",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Retry selected failed deliveries")
    def retry_failed(self, request, queryset):
        count = queryset.filter(status=AuthEmailJob.Status.FAILED).update(
            status=AuthEmailJob.Status.PENDING, attempts=0, available_at=timezone.now(), error_code="",
        )
        self.message_user(request, f"Queued {count} failed delivery job(s) for retry.")
