from django.contrib import admin

from core.admin import WorkflowRecordAdmin
from payments.models import Payment, WebhookEvent


@admin.register(Payment)
class PaymentAdmin(WorkflowRecordAdmin):
    list_display = ("id", "customer", "method", "provider", "amount", "status", "provider_reference", "created_at")
    list_filter = ("status", "method", "provider")
    search_fields = ("provider_reference", "customer__email", "order__number", "capstone_request__reference")
    readonly_fields = ("idempotency_key", "raw_response", "verified_by", "verified_at", "created_at", "updated_at")
    list_select_related = ("customer",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(WorkflowRecordAdmin):
    list_display = ("event_id", "provider", "event_type", "processed_at", "created_at")
    list_filter = ("provider", "event_type")
    readonly_fields = ("event_id", "provider", "event_type", "payload", "processed_at", "created_at")
