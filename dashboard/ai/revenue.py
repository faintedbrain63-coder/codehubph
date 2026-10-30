from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone

from payments.models import Payment


REVENUE_BASIS = (
    "Confirmed payments currently marked Completed, grouped by verification date. "
    "Pending, rejected, failed and refunded payments are excluded. Includes custom-project payments "
    "and historical product payments. Different currencies are never combined. These are retained "
    "receipts before fees and expenses, not profit or a cash-flow/refund ledger. "
    "Payments without a verification timestamp are excluded. Weeks begin Monday."
)


def revenue_snapshot(now=None):
    now = (now or timezone.now()).astimezone(ZoneInfo(settings.TIME_ZONE))
    today = now.date()
    dates = {"today": today, "week": today - timedelta(days=today.weekday()),
             "month": today.replace(day=1), "year": today.replace(month=1, day=1)}
    starts = {key: timezone.make_aware(datetime.combine(date, time.min), now.tzinfo) for key, date in dates.items()}
    aggregates = {}
    for key, start in starts.items():
        aggregates[key] = Sum("amount", filter=Q(verified_at__gte=start))
        aggregates[key + "_count"] = Count("pk", filter=Q(verified_at__gte=start))
    rows = list(Payment.objects.filter(status=Payment.Status.COMPLETED,
                verified_at__gte=min(starts.values()), verified_at__lte=now).order_by().values("currency").annotate(**aggregates).order_by("currency"))
    periods = []
    for key, label in (("today", "Today"), ("week", "This week"), ("month", "This month"), ("year", "This year")):
        totals = [{"currency": row["currency"], "amount": f'{row[key]:.2f}', "payments": row[key + "_count"]}
                  for row in rows if row[key] is not None]
        if not totals:
            totals = [{"currency": settings.CURRENCY, "amount": f'{Decimal("0"):.2f}', "payments": 0}]
        periods.append({"key": key, "label": label, "start": starts[key].isoformat(), "end": now.isoformat(), "totals": totals})
    return {"as_of": now.isoformat(), "timezone": settings.TIME_ZONE, "basis": REVENUE_BASIS, "periods": periods}
