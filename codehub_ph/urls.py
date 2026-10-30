from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = f"{settings.SITE_NAME} — Django admin"
admin.site.site_title = settings.SITE_NAME

urlpatterns = [
    path("admin/", admin.site.urls),
    path("manage/", include("dashboard.urls")),
    path("account/", include("accounts.urls")),
    path("products/", include("catalog.urls")),
    path("", include("capstone.urls")),
    path("", include("orders.urls")),
    path("", include("payments.urls")),
    path("", include("core.urls")),
]

# Public media only. Private files are never routed; they go through download views.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
