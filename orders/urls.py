from django.urls import path

from orders import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/<slug:slug>/", views.cart_add, name="cart_add"),
    path("cart/remove/<slug:slug>/", views.cart_remove, name="cart_remove"),
    path("cart/checkout/", views.cart_checkout, name="cart_checkout"),
    path("orders/", views.order_list, name="list"),
    path("orders/buy/<slug:slug>/", views.buy_now, name="buy_now"),
    path("orders/download/<int:item_id>/", views.download, name="download"),
    path("orders/<str:number>/", views.order_detail, name="detail"),
    path("orders/<str:number>/invoice/", views.invoice, name="invoice"),
    path("orders/<str:number>/cancel/", views.cancel, name="cancel"),
]
