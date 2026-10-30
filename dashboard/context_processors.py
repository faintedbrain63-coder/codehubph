"""Navigation metadata scoped to the staff workspace (no storefront queries)."""
from django.urls import reverse
from django.conf import settings

from capstone.models import CapstoneRequest
from core.models import ContactMessage, Testimonial
from payments.models import Payment
from orders.models import Order


def workspace(request):
    match = getattr(request, "resolver_match", None)
    if not match or match.namespace != "dashboard" or not request.user.is_authenticated or not request.user.is_staff:
        return {}
    counts = {
        "payments": Payment.objects.filter(status=Payment.Status.AWAITING_VERIFICATION).count(),
        "requests": CapstoneRequest.objects.filter(status=CapstoneRequest.Status.SUBMITTED).count(),
        "messages": ContactMessage.objects.filter(is_resolved=False).count(),
        "reviews": Testimonial.objects.filter(status=Testimonial.Status.PENDING).count(),
    }
    section_specs = [
        ("Workspace", [("Overview", "grid-1x2", "home", "", ""), ("Global search", "search", "search", "", "")]),
        ("Commerce", [("Orders", "receipt", "order_list", "orders/", ""),
                      ("Payments", "credit-card", "payment_list", "payments/", "payments"),
                      ("Customers", "people", "customer_list", "customers/", "")]),
        ("Catalog", [("All digital products", "box-seam", "product_list", "products/", ""),
                     ("Capstone projects", "mortarboard", "capstone_project_list", "capstone/projects/", ""),
                     ("Project requests", "kanban", "capstone_request_list", "capstone/requests/", "requests")]),
        ("Store", [("Customer comments", "chat-square-heart", "testimonial_list", "testimonials/", "reviews"),
                   ("Support inbox", "inbox", "message_list", "messages/", "messages"),
                   ("Settings", "gear", "settings", "settings/", "")]),
    ]
    if not settings.PRODUCT_SALES_ENABLED:
        section_specs = [
            ("Workspace", [("Overview", "grid-1x2", "home", "", ""), ("Global search", "search", "search", "", "")]),
            ("Projects", [("Project services", "code-slash", "capstone_project_list", "capstone/projects/", ""),
                          ("Project requests", "kanban", "capstone_request_list", "capstone/requests/", "requests")]),
            ("Clients", [("Payments", "credit-card", "payment_list", "payments/", "payments"),
                        ("Customers", "people", "customer_list", "customers/", "")]),
            ("Administration", [("Customer comments", "chat-square-heart", "testimonial_list", "testimonials/", "reviews"),
                                ("Support inbox", "inbox", "message_list", "messages/", "messages"),
                                ("Settings", "gear", "settings", "settings/", "")]),
        ]
        if Order.objects.exists():
            section_specs.append(("History", [("Purchase history", "receipt", "order_list", "orders/", "")]))
    section_specs.insert(1, ("Assistant", [("AI chatbot", "chat-dots", "assistant", "assistant/", ""),
                                           ("App manual", "book", "manual", "manual/", "")]))
    sections, current, parent = [], "Overview", None
    for heading, specs in section_specs:
        items = []
        for label, icon, name, prefix, counter in specs:
            active = request.path.startswith(f"/manage/{prefix}") if prefix else match.url_name == name
            item = {"label": label, "icon": icon, "url": reverse(f"dashboard:{name}"),
                    "active": active, "count": counts.get(counter, 0)}
            items.append(item)
            if active:
                current = label
                if request.path != item["url"]:
                    parent = item
        sections.append({"label": heading, "items": items})
    portfolio = {"label": "Portfolio projects", "icon": "images", "url": reverse("dashboard:portfolio_list"),
                 "active": request.path.startswith("/manage/portfolio/"), "count": 0}
    sections.insert(1, {"label": "Our work", "items": [portfolio]})
    if portfolio["active"]:
        current = portfolio["label"]
        parent = portfolio if request.path != portfolio["url"] else None
    return {"workspace_nav": sections, "workspace_section": current, "workspace_parent": parent,
            "workspace_counts": counts, "workspace_attention": sum(counts.values())}
