from django.contrib import admin
from django.conf import settings

from catalog.models import Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return settings.PRODUCT_SALES_ENABLED and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return settings.PRODUCT_SALES_ENABLED and super().has_change_permission(request, obj)

    list_display = ("name", "category", "price", "status", "is_featured", "published_at")
    list_filter = ("status", "category", "is_featured")
    search_fields = ("name", "short_description", "tech_stack")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("file_size", "published_at", "created_at", "updated_at")
    inlines = [ProductImageInline]
