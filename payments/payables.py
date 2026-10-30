"""Resolve the thing being paid for (an Order or a CapstoneRequest) from URL parameters."""

from django.http import Http404
from django.shortcuts import get_object_or_404

from capstone.models import CapstoneRequest
from orders.models import Order

PAYABLES = {
    "order": (Order, "number", "user"),
    "capstone": (CapstoneRequest, "reference", "customer"),
}


def get_user_payable_or_404(user, kind, reference, lock=False):
    if not isinstance(kind, str) or kind not in PAYABLES:
        raise Http404
    model, ref_field, owner_field = PAYABLES[kind]
    qs = model.objects.all()
    if lock:
        qs = qs.select_for_update()
    return get_object_or_404(qs, **{ref_field: reference, owner_field: user})


def lock_payable(payable):
    """Re-read a payable row with SELECT ... FOR UPDATE (call inside transaction.atomic)."""
    return type(payable).objects.select_for_update().get(pk=payable.pk)


def payment_filter(payable):
    return {"order": payable} if payable.payable_kind == "order" else {"capstone_request": payable}
