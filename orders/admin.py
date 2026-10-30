from django.contrib import admin

from core.admin import WorkflowRecordAdmin
from orders.models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "product_version", "unit_price", "download_count", "last_downloaded_at")


@admin.register(Order)
class OrderAdmin(WorkflowRecordAdmin):
    list_display = ("number", "user", "status", "total", "created_at", "paid_at")
    list_filter = ("status",)
    search_fields = ("number", "user__email")
    readonly_fields = ("number", "total", "paid_at", "refunded_at", "created_at", "updated_at")
    list_select_related = ("user",)
    inlines = [OrderItemInline]
