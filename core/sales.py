"""Keep retired purchase entry points from creating new product orders."""
from functools import wraps

from django.conf import settings
from django.shortcuts import redirect


def product_sales_only(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not settings.PRODUCT_SALES_ENABLED:
            request.session.pop("purchase_intent", None)
            request.session.pop("cart", None)
            return redirect("capstone:list")
        return view(request, *args, **kwargs)
    return wrapper
