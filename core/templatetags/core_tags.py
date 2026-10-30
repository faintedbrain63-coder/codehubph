from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.utils.html import format_html

register = template.Library()

# Status value -> (Bootstrap colour, icon). Shared by orders, payments, capstone and products.
STATUS_STYLES = {
    "pending": ("secondary", "hourglass"),
    "awaiting_verification": ("warning", "hourglass-split"),
    "paid": ("success", "check-circle"),
    "completed": ("success", "check-circle"),
    "rejected": ("danger", "x-circle"),
    "failed": ("danger", "x-circle"),
    "cancelled": ("danger", "slash-circle"),
    "refunded": ("info", "arrow-counterclockwise"),
    "submitted": ("secondary", "send"),
    "quoted": ("info", "tag"),
    "accepted": ("primary", "hand-thumbs-up"),
    "in_progress": ("primary", "gear"),
    "delivered": ("success", "box-seam"),
    "draft": ("secondary", "pencil"),
    "published": ("success", "globe"),
    "approved": ("success", "check-circle"),
    "hidden": ("secondary", "eye-slash"),
    "active": ("success", "check-circle"),
    "inactive": ("secondary", "slash-circle"),
}


@register.filter
def money(value, show_code=False):
    """Format a Decimal as e.g. ₱1,499.00."""
    try:
        amount = Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return value
    whole, _, cents = f"{amount:.2f}".partition(".")
    text = f"{settings.CURRENCY_SYMBOL}{intcomma(int(whole))}.{cents}"
    if show_code:
        text = f"{text} {settings.CURRENCY}"
    return text


@register.simple_tag
def status_badge(value, label=None):
    colour, icon = STATUS_STYLES.get(value, ("secondary", "circle"))
    return format_html(
        '<span class="status-badge status-{}"><i class="bi bi-{}" aria-hidden="true"></i>{}</span>',
        colour,
        icon,
        label or str(value).replace("_", " ").title(),
    )


@register.filter
def bs(field):
    """Render a bound form field with Bootstrap classes and ARIA attributes."""
    from django import forms

    widget = field.field.widget
    if isinstance(widget, forms.CheckboxInput):
        css = "form-check-input"
    elif isinstance(widget, (forms.Select, forms.SelectMultiple)) and not isinstance(
        widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)
    ):
        css = "form-select"
    elif isinstance(widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
        css = ""
    else:
        css = "form-control"
    attrs = {}
    described_by = []
    if field.help_text:
        described_by.append(f"{field.auto_id}_help")
    if field.errors:
        css += " is-invalid"
        attrs["aria-invalid"] = "true"
        described_by.append(f"{field.auto_id}_error")
    existing = widget.attrs.get("class", "")
    attrs["class"] = f"{css} {existing}".strip()
    if described_by:
        attrs["aria-describedby"] = " ".join(described_by)
    return field.as_widget(attrs=attrs)


@register.filter
def is_checkbox(field):
    from django import forms

    return isinstance(field.field.widget, forms.CheckboxInput)


@register.filter
def split_lines(value):
    return [line.strip(" -•\t") for line in (value or "").splitlines() if line.strip(" -•\t")]


@register.filter
def split_tags(value):
    return [tag.strip() for tag in (value or "").split(",") if tag.strip()]


@register.simple_tag(takes_context=True)
def pagination_range(context, page_obj):
    return page_obj.paginator.get_elided_page_range(page_obj.number)


@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    """Rebuild the current query string with some keys replaced (used by pagination)."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.simple_tag(takes_context=True)
def active(context, *url_prefixes):
    path = context["request"].path
    return "active" if any(path.startswith(p) for p in url_prefixes) else ""
