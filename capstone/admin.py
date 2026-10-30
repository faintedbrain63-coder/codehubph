from django.contrib import admin

from capstone.models import CapstoneMessage, CapstoneProject, CapstoneRequest
from core.admin import WorkflowRecordAdmin


@admin.register(CapstoneProject)
class CapstoneProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "field", "suggested_price", "status", "created_at")
    list_filter = ("status", "field")
    search_fields = ("title", "short_description", "tech_stack")
    prepopulated_fields = {"slug": ("title",)}


class CapstoneMessageInline(admin.TabularInline):
    model = CapstoneMessage
    extra = 0
    readonly_fields = ("sender", "created_at")


@admin.register(CapstoneRequest)
class CapstoneRequestAdmin(WorkflowRecordAdmin):
    list_display = ("reference", "customer", "project", "status", "agreed_price", "created_at")
    list_filter = ("status",)
    search_fields = ("reference", "customer__email", "project__title", "request_title", "school_name")
    readonly_fields = (
        "reference", "quoted_at", "accepted_at", "paid_at", "delivered_at", "completed_at", "cancelled_at",
        "created_at", "updated_at",
    )
    list_select_related = ("customer", "project")
    inlines = [CapstoneMessageInline]
