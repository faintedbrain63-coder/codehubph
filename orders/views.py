import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST, require_safe

from catalog.models import Product
from core.downloads import serve_private_file
from core.sales import product_sales_only
from orders.cart import Cart
from orders.models import Order, OrderItem
from orders.services import create_order, owned_product_ids
from payments.models import Payment


@product_sales_only
def cart_detail(request):
    cart = Cart(request)
    products = list(cart.products())
    owned = owned_product_ids(request.user) if request.user.is_authenticated else set()
    total = sum((p.price for p in products if p.pk not in owned), 0)
    return render(request, "orders/cart.html", {"products": products, "owned": owned, "total": total})


@require_POST
@product_sales_only
def cart_add(request, slug):
    product = get_object_or_404(Product.objects.published(), slug=slug)
    if Cart(request).add(product):
        messages.success(request, f"“{product.name}” was added to your cart.")
    else:
        messages.info(request, f"“{product.name}” is already in your cart.")
    return redirect("orders:cart")


@require_POST
@product_sales_only
def cart_remove(request, slug):
    product = get_object_or_404(Product, slug=slug)
    Cart(request).remove(product)
    messages.info(request, f"“{product.name}” was removed from your cart.")
    return redirect("orders:cart")


# What a signed-out visitor was buying, so checkout continues after they register or sign in.
# An abandoned intent expires, so a later unrelated sign-in never creates a surprise order.
PURCHASE_INTENT_KEY = "purchase_intent"
PURCHASE_INTENT_SECONDS = 60 * 60


def _register_to_continue(request, intent, next_url, message):
    request.session[PURCHASE_INTENT_KEY] = {**intent, "at": int(time.time())}
    messages.info(request, message)
    return redirect(f"{reverse('accounts:register')}?{urlencode({'next': next_url})}")


def _checkout_cart(request):
    cart = Cart(request)
    owned = owned_product_ids(request.user)
    products = [p for p in cart.products() if p.pk not in owned]
    if not products:
        messages.warning(request, "Your cart is empty or you already own these products.")
        return redirect("orders:cart")
    try:
        order, _ = create_order(request.user, products)
    except ValueError as exc:
        messages.warning(request, str(exc))
        return redirect("orders:cart")
    cart.clear()
    return redirect(order.get_payment_url())


def _checkout_product(request, product):
    if product.pk in owned_product_ids(request.user):
        messages.info(request, "You already own this product. You can download it from My Orders.")
        return redirect("orders:list")
    try:
        order, _ = create_order(request.user, [product])
    except ValueError as exc:
        messages.warning(request, str(exc))
        return redirect("catalog:list")
    return redirect(order.get_payment_url())


def resume_purchase(request):
    """Continue the checkout a visitor started before signing in. Returns a response, or None if nothing is pending."""
    intent = request.session.pop(PURCHASE_INTENT_KEY, None)
    if not settings.PRODUCT_SALES_ENABLED:
        return None
    if not isinstance(intent, dict) or not request.user.is_authenticated:
        return None
    started = intent.get("at")
    if not isinstance(started, int) or not 0 <= time.time() - started <= PURCHASE_INTENT_SECONDS:
        return None
    if intent.get("cart") is True:
        return _checkout_cart(request)
    slug = intent.get("product")
    if isinstance(slug, str):
        product = Product.objects.published().filter(slug=slug).first()
        if product:
            return _checkout_product(request, product)
    return None


@require_POST
@product_sales_only
def cart_checkout(request):
    if not request.user.is_authenticated:
        return _register_to_continue(
            request, {"cart": True}, reverse("orders:cart"),
            "Create a free account to check out. Your cart is saved and checkout continues right after.",
        )
    return _checkout_cart(request)


@require_POST
@product_sales_only
def buy_now(request, slug):
    product = get_object_or_404(Product.objects.published(), slug=slug)
    if not request.user.is_authenticated:
        return _register_to_continue(
            request, {"product": product.slug}, product.get_absolute_url(),
            f"Create a free account to buy “{product.name}”. Checkout continues right after.",
        )
    return _checkout_product(request, product)


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    status = request.GET.get("status", "")
    if status in Order.Status.values:
        orders = orders.filter(status=status)
    else:
        status = ""
    q = request.GET.get("q", "").strip()[:100]
    if q:
        orders = orders.filter(Q(number__icontains=q) | Q(items__product_name__icontains=q)).distinct()
    page = Paginator(orders, 10).get_page(request.GET.get("page"))
    return render(
        request,
        "orders/order_list.html",
        {"page_obj": page, "orders": page.object_list, "status": status, "statuses": Order.Status.choices, "q": q},
    )


def _get_user_order(request, number):
    return get_object_or_404(
        Order.objects.prefetch_related("items__product"), number=number, user=request.user
    )


@login_required
def order_detail(request, number):
    order = _get_user_order(request, number)
    payments = Payment.objects.filter(order=order).order_by("-created_at")
    return render(request, "orders/order_detail.html", {"order": order, "payments": payments})


@login_required
@require_POST
def cancel(request, number):
    """Cancel an unpaid order; optionally move its still-available, not-yet-owned items back to the cart."""
    with transaction.atomic():
        order = get_object_or_404(Order.objects.select_for_update(), number=number, user=request.user)
        try:
            order.cancel()
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(order.get_absolute_url())
    if request.POST.get("restore_cart") and settings.PRODUCT_SALES_ENABLED:
        owned = owned_product_ids(request.user)
        cart = Cart(request)
        restored = 0
        for item in order.items.filter(product__status=Product.Status.PUBLISHED).select_related("product"):
            if item.product_id not in owned and cart.add(item.product):
                restored += 1
        messages.success(
            request,
            f"Order {order.number} was cancelled."
            + (f" {restored} item{'s' if restored != 1 else ''} moved to your cart." if restored else ""),
        )
        return redirect("orders:cart")
    messages.success(request, f"Order {order.number} was cancelled.")
    return redirect(order.get_absolute_url())


@login_required
def invoice(request, number):
    order = _get_user_order(request, number)
    payment = Payment.objects.filter(order=order, status__in=[Payment.Status.COMPLETED, Payment.Status.REFUNDED]).first()
    return render(request, "orders/invoice.html", {"order": order, "payment": payment})


@login_required
@require_safe
def download(request, item_id):
    """Serve a purchased file after checking ownership, payment status, limit and expiry."""
    with transaction.atomic():
        original = get_object_or_404(OrderItem, pk=item_id, order__user=request.user)
        get_object_or_404(Order.objects.select_for_update(), pk=original.order_id, user=request.user)
        # Read the counter in a separate statement *after* acquiring the lock.
        # A joined SELECT taken before waiting can retain a stale item counter.
        item = get_object_or_404(
            OrderItem.objects.select_related("order", "product"),
            pk=item_id,
            order__user=request.user,
        )
        reason = item.download_block_reason
        if reason:
            messages.error(request, reason)
            return redirect(item.order.get_absolute_url())
        response = serve_private_file(item.product.file, f"{item.product_name}-v{item.product_version}")
        if request.method != "HEAD":
            OrderItem.objects.filter(pk=item.pk).update(
                download_count=F("download_count") + 1, last_downloaded_at=timezone.now()
            )
    return response
