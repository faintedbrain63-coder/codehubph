from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("portfolio/", views.portfolio_list, name="portfolio_list"),
    path("portfolio/images/<int:pk>/", views.portfolio_image, name="portfolio_image"),
    path("portfolio/<slug:slug>/", views.portfolio_detail, name="portfolio_detail"),
    path("contact/", views.contact, name="contact"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("license/", views.license_agreement, name="license"),
    path("legal/<slug:kind>/<slug:version>/", views.legal_document, name="legal_document"),
]
