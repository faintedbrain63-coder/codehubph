from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count

from catalog.models import Product
from core.notifications import notify_order_received
from orders.models import Order, OrderItem


def owned_product_ids(user):
    return set(
        OrderItem.objects.filter(order__user=user, order__status=Order.Status.PAID).values_list(
            "product_id", flat=True
        )
    )


@transaction.atomic
def create_order(user, products):
    """Create a pending order for the given products. Prices are copied from the DB, never from the form."""
    if not settings.PRODUCT_SALES_ENABLED:
        raise ValueError("Ready-made product sales have ended. Please submit a custom project request.")
    products = list({p.pk: p for p in products}.values())
    if not products:
        raise ValueError("Cannot create an empty order.")

    # Serialize checkout for this customer, including simultaneous Buy Now clicks.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    requested_ids = {p.pk for p in products}
    products = list(Product.objects.published().filter(pk__in=requested_ids))
    if {p.pk for p in products} != requested_ids:
        raise ValueError("A selected product is no longer available. Please review your cart and try again.")
    prices = {p.pk: p.price for p in products}
    # Count all items before filtering by product; counting a filtered join can
    # incorrectly make a multi-product order look like a single-product order.
    candidates = (
        Order.objects.filter(user=user, currency=settings.CURRENCY,
                             status__in=[Order.Status.PENDING, Order.Status.REJECTED])
        .annotate(n=Count("items"))
        .filter(n=len(products))
        .prefetch_related("items")
    )
    for existing in candidates:
        if {item.product_id: item.unit_price for item in existing.items.all()} == prices:
            return existing, False

    order = Order.objects.create(user=user)
    OrderItem.objects.bulk_create(
        [
            OrderItem(order=order, product=p, product_name=p.name, product_version=p.version, unit_price=p.price)
            for p in products
        ]
    )
    order.recalculate_total()
    transaction.on_commit(lambda: notify_order_received(order))
    return order, True
