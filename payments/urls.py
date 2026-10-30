from django.urls import path

from payments import views

app_name = "payments"

urlpatterns = [
    path("pay/<str:kind>/<str:reference>/", views.checkout, name="checkout"),
    path("pay/<str:kind>/<str:reference>/submit/<str:method>/", views.submit_manual, name="submit_manual"),
    path("payments/paypal/create/", views.paypal_create_order, name="paypal_create"),
    path("payments/paypal/capture/", views.paypal_capture_order, name="paypal_capture"),
    path("payments/webhooks/paypal/", views.paypal_webhook, name="paypal_webhook"),
]
