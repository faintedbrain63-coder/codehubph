from django.contrib import admin

from core.models import ContactMessage, PortfolioPresentation, PortfolioProject, PortfolioScreenshot, SiteSettings, Testimonial
from dashboard.forms import BasePortfolioScreenshotFormSet, PortfolioPresentationForm, PortfolioProjectForm, PortfolioScreenshotForm


class WorkflowRecordAdmin(admin.ModelAdmin):
    """Inspect transaction records here; use /manage/ for audited state changes."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "is_resolved", "created_at")
    list_filter = ("is_resolved",)
    search_fields = ("subject", "name", "email", "message")


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("name", "portfolio_project", "role", "rating", "status", "is_featured", "created_at")
    list_filter = ("status", "rating", "is_featured")
    search_fields = ("name", "role", "message", "user__email")
    raw_id_fields = ("user", "portfolio_project")
    readonly_fields = ("publication_consented_at",)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.user_id and obj.portfolio_project_id:
            return self.readonly_fields + ("user", "name", "role", "rating", "message", "portfolio_project")
        return self.readonly_fields


class PortfolioScreenshotInline(admin.TabularInline):
    model = PortfolioScreenshot
    extra = 1
    max_num = 12
    form = PortfolioScreenshotForm
    formset = BasePortfolioScreenshotFormSet


@admin.register(PortfolioProject)
class PortfolioProjectAdmin(admin.ModelAdmin):
    form = PortfolioProjectForm
    list_display = ("title", "project_type", "stage", "is_published", "is_featured")
    list_filter = ("project_type", "stage", "is_published")
    search_fields = ("title", "summary", "customer__email")
    inlines = [PortfolioScreenshotInline]


@admin.register(PortfolioPresentation)
class PortfolioPresentationAdmin(admin.ModelAdmin):
    form = PortfolioPresentationForm

    def has_add_permission(self, request):
        return not PortfolioPresentation.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
