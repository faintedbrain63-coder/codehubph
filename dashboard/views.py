from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.debug import sensitive_post_parameters

from accounts.settings import account_settings_forms
from capstone.concept_reader import ConceptFileError, read_concept_file
from capstone.models import CapstoneProject, CapstoneRequest
from catalog.models import Product
from core.downloads import serve_private_document, serve_private_file, serve_private_image_inline
from core.models import ContactMessage, PortfolioProject, SiteSettings, Testimonial
from core.notifications import notify_capstone_status, notify_download_access_reset
from core.sales import product_sales_only
from dashboard.ai.providers import PROVIDERS
from dashboard.insights import storage_usage, visitor_locations
from dashboard.decorators import staff_required
from dashboard.forms import (
    AdminMessageForm,
    CapstoneProjectForm,
    DeliverablesForm,
    ProductForm,
    ProductImageFormSet,
    QuoteForm,
    RejectPaymentForm,
    SiteSettingsForm,
    CustomerAdminForm,
    TestimonialAdminForm,
)
from dashboard.models import AdminAISettings, ConceptAnalysis
from orders.models import Order
from payments.models import Payment
from payments.services import PaymentError, approve_payment, refund_payable, reject_payment

User = get_user_model()


def _paginate(request, qs, per_page=20):
    requested_size = request.GET.get("per_page", str(per_page))
    if requested_size in {"20", "50", "100"}:
        per_page = int(requested_size)
    if not qs.ordered:
        qs = qs.order_by("-pk")
    return Paginator(qs, per_page).get_page(request.GET.get("page"))


def _safe_next(request, fallback):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return nxt
    return fallback


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------
@staff_required
def home(request):
    completed = Payment.objects.filter(status=Payment.Status.COMPLETED)
    days = int(request.GET.get("days", "14")) if request.GET.get("days", "14") in {"7", "14", "30"} else 14
    since = timezone.localtime() - timedelta(days=days - 1)
    daily = dict(
        completed.filter(verified_at__gte=since.replace(hour=0, minute=0, second=0, microsecond=0))
        .annotate(day=TruncDate("verified_at"))
        .order_by()
        .values("day")
        .annotate(total=Sum("amount"))
        .values_list("day", "total")
    )
    today = timezone.localdate()
    chart = []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        chart.append({"label": day.strftime("%b %d"), "value": float(daily.get(day, Decimal("0")))})

    context = {
        "stats": {
            "revenue": completed.aggregate(total=Sum("amount"))["total"] or Decimal("0"),
            "orders": Order.objects.count(),
            "paid_orders": Order.objects.filter(status=Order.Status.PAID).count(),
            "pending_payments": Payment.objects.filter(status=Payment.Status.AWAITING_VERIFICATION).count(),
            "new_customers": User.objects.filter(
                is_staff=False, date_joined__gte=timezone.now() - timedelta(days=30)
            ).count(),
            "open_capstone": CapstoneRequest.objects.exclude(
                status__in=[CapstoneRequest.Status.COMPLETED, CapstoneRequest.Status.CANCELLED]
            ).count(),
            "published_products": Product.objects.published().count(),
            "project_requests": CapstoneRequest.objects.count(),
            "published_services": CapstoneProject.objects.published().count(),
            "unread_messages": ContactMessage.objects.filter(is_resolved=False).count(),
            "draft_products": Product.objects.filter(status=Product.Status.DRAFT).count(),
            "period_revenue": sum(daily.values(), Decimal("0")),
        },
        "recent_orders": Order.objects.select_related("user")[:8],
        "pending_payments": Payment.objects.filter(status=Payment.Status.AWAITING_VERIFICATION)
        .select_related("customer", "order", "capstone_request")[:5],
        "new_requests": CapstoneRequest.objects.filter(status=CapstoneRequest.Status.SUBMITTED)
        .select_related("customer", "project")[:5],
        "chart": chart,
        "days": days,
        "today": today,
        "locations": visitor_locations(),
        "storage": storage_usage(),
    }
    return render(request, "dashboard/home.html", context)


@staff_required
def search(request):
    q = request.GET.get("q", "").strip()[:100]
    groups = []
    if len(q) >= 2:
        products = Product.objects.filter(Q(name__icontains=q) | Q(tech_stack__icontains=q)).order_by("name")[:5]
        if settings.PRODUCT_SALES_ENABLED:
            groups.append({"title": "Digital products", "url": reverse("dashboard:product_list"), "rows": [
                {"title": p.name, "subtitle": f"{p.get_category_display()} · {p.get_status_display()}",
                 "url": reverse("dashboard:product_detail", args=[p.pk])} for p in products]})
        projects = CapstoneProject.objects.filter(Q(title__icontains=q) | Q(tech_stack__icontains=q)).order_by("title")[:5]
        groups.append({"title": "Project services", "url": reverse("dashboard:capstone_project_list"), "rows": [
            {"title": p.title, "subtitle": p.get_status_display(),
             "url": reverse("dashboard:capstone_project_detail", args=[p.pk])} for p in projects]})
        portfolio = PortfolioProject.objects.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(tech_stack__icontains=q))[:5]
        groups.append({"title": "Portfolio projects", "url": reverse("dashboard:portfolio_list"), "rows": [
            {"title": p.title, "subtitle": f"{p.get_project_type_display()} · {p.get_stage_display()}",
             "url": reverse("dashboard:portfolio_edit", args=[p.pk])} for p in portfolio]})
        orders = Order.objects.select_related("user").filter(Q(number__icontains=q) | Q(user__email__icontains=q))[:5]
        groups.append({"title": "Orders", "url": reverse("dashboard:order_list"), "rows": [
            {"title": o.number, "subtitle": f"{o.user.email} · {o.get_status_display()}",
             "url": reverse("dashboard:order_detail", args=[o.number])} for o in orders]})
        requests = CapstoneRequest.objects.select_related("project").filter(
            Q(reference__icontains=q) | Q(customer__email__icontains=q) | Q(project__title__icontains=q)
            | Q(request_title__icontains=q) | Q(school_name__icontains=q))[:5]
        groups.append({"title": "Project requests", "url": reverse("dashboard:capstone_request_list"), "rows": [
            {"title": r.reference, "subtitle": r.title,
             "url": reverse("dashboard:capstone_request_detail", args=[r.reference])} for r in requests]})
        customers = User.objects.filter(is_staff=False).filter(
            Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)).order_by("email")[:5]
        groups.append({"title": "Customers", "url": reverse("dashboard:customer_list"), "rows": [
            {"title": c.display_name, "subtitle": c.email,
             "url": reverse("dashboard:customer_list") + "?" + urlencode({"q": c.email})}
            for c in customers]})
    return render(request, "dashboard/search.html", {"q": q, "groups": groups,
                  "result_count": sum(len(g["rows"]) for g in groups)})


# --------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------
@staff_required
def product_list(request):
    products = Product.objects.annotate(sales=Count("order_items", filter=Q(order_items__order__status="paid")))
    q = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    category = request.GET.get("category", "")
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(slug__icontains=q) | Q(short_description__icontains=q)
            | Q(description__icontains=q) | Q(tech_stack__icontains=q)
        )
    if status in Product.Status.values:
        products = products.filter(status=status)
    else:
        status = ""
    if category in Product.Category.values:
        products = products.filter(category=category)
    else:
        category = ""
    page = _paginate(request, products.order_by("-created_at", "-pk"))
    return render(
        request, "dashboard/product_list.html",
        {"page_obj": page, "products": page.object_list, "q": q, "status": status,
         "statuses": Product.Status.choices, "category": category, "categories": Product.Category.choices},
    )


@staff_required
def product_detail(request, pk):
    product = get_object_or_404(Product.objects.prefetch_related("images"), pk=pk)
    return render(request, "dashboard/product_detail.html", {"product": product})


@staff_required
@require_http_methods(["GET", "HEAD"])
def product_file(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return serve_private_file(product.file, f"{product.slug}-{product.version}")


@staff_required
@require_http_methods(["GET", "POST"])
@product_sales_only
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    data = request.POST if request.method == "POST" else None
    category = request.GET.get("category", "")
    initial = {"category": category} if category in Product.Category.values else {}
    form = ProductForm(
        data, request.FILES or None, instance=product, initial=initial if not product else None, user=request.user
    )
    formset = ProductImageFormSet(data, request.FILES or None, instance=product, prefix="images")
    # Validate both so gallery errors are shown even when the main form is invalid.
    valid = False
    if request.method == "POST":
        form_valid = form.is_valid()
        gallery_valid = formset.is_valid()
        valid = form_valid and gallery_valid
    if valid:
        with transaction.atomic():
            product = form.save()
            formset.instance = product
            formset.save()
        verb = "updated" if pk else "created"
        extra = " It is now live on the store." if product.is_published else " It is saved as a draft."
        messages.success(request, f"“{product.name}” was {verb}.{extra}")
        if request.POST.get("save_action") == "continue":
            return redirect("dashboard:product_edit", pk=product.pk)
        return redirect("dashboard:product_list")
    return render(request, "dashboard/product_form.html", {"form": form, "formset": formset, "product": product})


@staff_required
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    try:
        product.delete()
        messages.success(request, f"“{product.name}” was deleted.")
    except ProtectedError:
        product.status = Product.Status.DRAFT
        product.save(update_fields=["status", "updated_at"])
        messages.warning(
            request,
            f"“{product.name}” has orders, so it cannot be deleted. It was moved to Draft instead "
            "(hidden from the store, still downloadable by buyers).",
        )
    return redirect("dashboard:product_list")


# --------------------------------------------------------------------------
# Capstone projects
# --------------------------------------------------------------------------
@staff_required
def capstone_project_list(request):
    projects = CapstoneProject.objects.annotate(request_count=Count("requests"))
    q = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    field = request.GET.get("field", "")
    if q:
        projects = projects.filter(
            Q(title__icontains=q) | Q(slug__icontains=q) | Q(short_description__icontains=q)
            | Q(description__icontains=q) | Q(tech_stack__icontains=q)
        )
    if status in CapstoneProject.Status.values:
        projects = projects.filter(status=status)
    else:
        status = ""
    if field in CapstoneProject.Field.values:
        projects = projects.filter(field=field)
    else:
        field = ""
    page = _paginate(request, projects.order_by("-created_at", "-pk"))
    return render(request, "dashboard/capstone_project_list.html", {
        "page_obj": page, "projects": page.object_list, "q": q, "status": status, "field": field,
        "statuses": CapstoneProject.Status.choices, "fields": CapstoneProject.Field.choices,
    })


@staff_required
def capstone_project_detail(request, pk):
    project = get_object_or_404(CapstoneProject, pk=pk)
    return render(request, "dashboard/capstone_project_detail.html", {"project": project})


@staff_required
@require_http_methods(["GET", "HEAD"])
def capstone_project_file(request, pk, kind):
    project = get_object_or_404(CapstoneProject, pk=pk)
    # Never resolve arbitrary attributes or paths from user input.
    files = {"source": project.source_code, "documentation": project.documentation}
    return serve_private_file(files.get(kind), f"{project.slug}-{kind}")


@staff_required
@require_http_methods(["GET", "POST"])
def capstone_project_form(request, pk=None):
    project = get_object_or_404(CapstoneProject, pk=pk) if pk else None
    form = CapstoneProjectForm(
        request.POST if request.method == "POST" else None, request.FILES or None, instance=project, user=request.user
    )
    if request.method == "POST" and form.is_valid():
        project = form.save()
        messages.success(request, f"Capstone project “{project.title}” was saved.")
        if request.POST.get("save_action") == "continue":
            return redirect("dashboard:capstone_project_edit", pk=project.pk)
        return redirect("dashboard:capstone_project_list")
    return render(request, "dashboard/capstone_project_form.html", {"form": form, "project": project})


@staff_required
@require_POST
def capstone_project_delete(request, pk):
    project = get_object_or_404(CapstoneProject, pk=pk)
    try:
        project.delete()
        messages.success(request, f"“{project.title}” was deleted.")
    except ProtectedError:
        project.status = CapstoneProject.Status.DRAFT
        project.save(update_fields=["status", "updated_at"])
        messages.warning(request, f"“{project.title}” has requests, so it was moved to Draft instead of deleted.")
    return redirect("dashboard:capstone_project_list")


# --------------------------------------------------------------------------
# Capstone requests
# --------------------------------------------------------------------------
@staff_required
def capstone_request_list(request):
    reqs = CapstoneRequest.objects.select_related("customer", "project")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()[:100]
    if status in CapstoneRequest.Status.values:
        reqs = reqs.filter(status=status)
    else:
        status = ""
    if q:
        reqs = reqs.filter(Q(reference__icontains=q) | Q(customer__email__icontains=q) | Q(school_name__icontains=q)
                           | Q(project__title__icontains=q) | Q(request_title__icontains=q))
    page = _paginate(request, reqs)
    return render(
        request, "dashboard/capstone_request_list.html",
        {"page_obj": page, "requests": page.object_list, "status": status, "q": q,
         "statuses": CapstoneRequest.Status.choices},
    )


ADMIN_STATUS_ACTIONS = {
    "in_progress": ("Start work", CapstoneRequest.Status.IN_PROGRESS),
    "delivered": ("Mark as delivered", CapstoneRequest.Status.DELIVERED),
    "completed": ("Mark as completed", CapstoneRequest.Status.COMPLETED),
    "cancelled": ("Cancel request", CapstoneRequest.Status.CANCELLED),
}


@staff_required
def capstone_request_detail(request, reference):
    req = get_object_or_404(CapstoneRequest.objects.select_related("customer", "project"), reference=reference)
    actions = [(key, label) for key, (label, status) in ADMIN_STATUS_ACTIONS.items() if req.can_transition_to(status)]
    return render(
        request,
        "dashboard/capstone_request_detail.html",
        {
            "req": req,
            "quote_form": QuoteForm(instance=req),
            "deliverables_form": DeliverablesForm(instance=req),
            "message_form": AdminMessageForm(),
            "reject_form": RejectPaymentForm(),
            "thread": req.messages.select_related("sender"),
            "payments": req.payments.select_related("verified_by"),
            "actions": actions,
            "can_quote": req.can_transition_to(CapstoneRequest.Status.QUOTED),
        },
    )


@staff_required
@xframe_options_sameorigin  # The in-app viewer embeds PDFs from this URL.
def capstone_request_concept_file(request, reference):
    req = get_object_or_404(CapstoneRequest, reference=reference)
    return serve_private_document(req.concept_file, f"{req.reference}-concept")


@staff_required
def capstone_request_concept_view(request, reference):
    req = get_object_or_404(CapstoneRequest.objects.select_related("customer"), reference=reference)
    if not req.concept_file:
        raise Http404("The customer did not attach a file.")
    content, read_error = None, ""
    if not req.concept_file_is_pdf:
        try:
            content = read_concept_file(req.concept_file)
        except ConceptFileError as exc:
            read_error = str(exc)
    config = AdminAISettings.load()
    return render(request, "dashboard/capstone_concept_file.html", {
        "req": req, "content": content, "read_error": read_error,
        "analysis": ConceptAnalysis.objects.filter(request=req).first(),
        "ai_ready": config.is_ready,
        "provider_label": PROVIDERS.get(config.active_connection.provider, {}).get("label") if config.active_connection else "",
    })


@staff_required
@require_POST
def capstone_request_quote(request, reference):
    with transaction.atomic():
        req = get_object_or_404(CapstoneRequest.objects.select_for_update(), reference=reference)
        form = QuoteForm(request.POST, instance=req)
        if not form.is_valid():
            messages.error(request, "Enter a valid price for the quote.")
            return redirect("dashboard:capstone_request_detail", reference=reference)
        req = form.save(commit=False)
        try:
            req.transition_to(CapstoneRequest.Status.QUOTED)  # also saves the price/notes
            req.save(update_fields=["agreed_price", "quote_notes"])
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:capstone_request_detail", reference=reference)
        transaction.on_commit(lambda: notify_capstone_status(req))
    messages.success(request, f"Quote sent to {req.customer.email}.")
    return redirect("dashboard:capstone_request_detail", reference=reference)


@staff_required
@require_POST
def capstone_request_status(request, reference):
    action = request.POST.get("action")
    if action not in ADMIN_STATUS_ACTIONS:
        messages.error(request, "Unknown action.")
        return redirect("dashboard:capstone_request_detail", reference=reference)
    label, new_status = ADMIN_STATUS_ACTIONS[action]
    with transaction.atomic():
        req = get_object_or_404(CapstoneRequest.objects.select_for_update(), reference=reference)
        try:
            req.transition_to(new_status)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:capstone_request_detail", reference=reference)
        if new_status == CapstoneRequest.Status.CANCELLED:
            req.cancel_reason = request.POST.get("reason", "").strip()[:500] or "Cancelled by the store."
            req.save(update_fields=["cancel_reason"])
        transaction.on_commit(lambda: notify_capstone_status(req))
    messages.success(request, f"Request {req.reference} is now {req.get_status_display()}.")
    return redirect("dashboard:capstone_request_detail", reference=reference)


@staff_required
@require_POST
def capstone_request_deliverables(request, reference):
    req = get_object_or_404(CapstoneRequest, reference=reference)
    form = DeliverablesForm(request.POST, request.FILES, instance=req, user=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "Deliverables saved. The customer can download them once the request is paid.")
    else:
        errors = "; ".join(e for errs in form.errors.values() for e in errs)
        messages.error(request, f"Upload failed: {errors}")
    return redirect("dashboard:capstone_request_detail", reference=reference)


@staff_required
@require_POST
def capstone_request_refund(request, reference):
    req = get_object_or_404(CapstoneRequest, reference=reference)
    try:
        refund_payable(req, request.user, request.POST.get("notes", "").strip())
    except PaymentError as exc:
        messages.error(request, str(exc))
    else:
        notify_capstone_status(CapstoneRequest.objects.get(pk=req.pk))
        messages.success(request, "Refund recorded. The request is cancelled and download access was revoked.")
    return redirect("dashboard:capstone_request_detail", reference=reference)


@staff_required
@require_POST
def capstone_request_message(request, reference):
    req = get_object_or_404(CapstoneRequest, reference=reference)
    form = AdminMessageForm(request.POST)
    if form.is_valid():
        msg = form.save(commit=False)
        msg.request = req
        msg.sender = request.user
        msg.save()
        from core.notifications import send_templated_email

        send_templated_email(
            f"New message about {req.reference}", "capstone_message", {"req": req, "msg": msg}, [req.customer.email]
        )
        messages.success(request, "Reply sent.")
    else:
        messages.error(request, "Write a reply within the allowed length before sending.")
    return redirect(reverse("dashboard:capstone_request_detail", kwargs={"reference": reference}) + "#messages")


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------
@staff_required
def order_list(request):
    orders = Order.objects.select_related("user").annotate(item_count=Count("items"))
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()[:100]
    if status in Order.Status.values:
        orders = orders.filter(status=status)
    else:
        status = ""
    if q:
        orders = orders.filter(Q(number__icontains=q) | Q(user__email__icontains=q))
    page = _paginate(request, orders)
    return render(
        request, "dashboard/order_list.html",
        {"page_obj": page, "orders": page.object_list, "status": status, "q": q, "statuses": Order.Status.choices},
    )


@staff_required
def order_detail(request, number):
    order = get_object_or_404(Order.objects.select_related("user").prefetch_related("items__product"), number=number)
    return render(
        request,
        "dashboard/order_detail.html",
        {"order": order, "payments": order.payments.select_related("verified_by"), "reject_form": RejectPaymentForm()},
    )


@staff_required
@require_POST
def order_refund(request, number):
    order = get_object_or_404(Order, number=number)
    if order.status != Order.Status.PAID:
        messages.error(request, "Only paid orders can be marked as refunded.")
    else:
        try:
            refund_payable(order, request.user, request.POST.get("notes", ""))
        except PaymentError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Order {order.number} marked as refunded. Download access was revoked.")
    return redirect("dashboard:order_detail", number=number)


@staff_required
@require_POST
def order_resend_access(request, number):
    with transaction.atomic():
        order = get_object_or_404(Order.objects.select_for_update(), number=number)
        if order.status != Order.Status.PAID:
            messages.error(request, "Download access can only be resent for paid orders.")
        else:
            order.grant_download_access()
            transaction.on_commit(lambda: notify_download_access_reset(order))
            messages.success(request, f"Download access reset and emailed to {order.user.email}.")
    return redirect("dashboard:order_detail", number=number)


# --------------------------------------------------------------------------
# Payments
# --------------------------------------------------------------------------
@staff_required
def payment_list(request):
    payments = Payment.objects.select_related("customer", "order", "capstone_request", "verified_by")
    status = request.GET.get("status", "awaiting_verification")
    if status in Payment.Status.values:
        payments = payments.filter(status=status)
    else:
        status = ""
    q = request.GET.get("q", "").strip()[:100]
    method = request.GET.get("method", "")
    if q:
        payments = payments.filter(Q(customer__email__icontains=q) | Q(provider_reference__icontains=q)
                                   | Q(order__number__icontains=q) | Q(capstone_request__reference__icontains=q))
    if method in Payment.Method.values:
        payments = payments.filter(method=method)
    else:
        method = ""
    page = _paginate(request, payments)
    return render(
        request, "dashboard/payment_list.html",
        {"page_obj": page, "payments": page.object_list, "status": status,
         "statuses": Payment.Status.choices, "reject_form": RejectPaymentForm(), "q": q,
         "method": method, "methods": Payment.Method.choices},
    )


@staff_required
@require_POST
def payment_approve(request, pk):
    try:
        payment, changed = approve_payment(pk, request.user, request.POST.get("notes", "").strip())
        if changed:
            messages.success(request, f"Payment approved. {payment.payable.reference} is now paid and the customer was notified.")
        else:
            messages.info(request, "This payment was already approved.")
    except Payment.DoesNotExist:
        messages.error(request, "Payment not found.")
    except PaymentError as exc:
        messages.error(request, str(exc))
    return redirect(_safe_next(request, "dashboard:payment_list"))


@staff_required
@require_POST
def payment_reject(request, pk):
    form = RejectPaymentForm(request.POST)
    try:
        if not form.is_valid():
            raise PaymentError("Please give a reason. The customer will see it.")
        reject_payment(pk, request.user, form.cleaned_data["reason"])
        messages.success(request, "Payment rejected. The customer was notified with your reason.")
    except Payment.DoesNotExist:
        messages.error(request, "Payment not found.")
    except PaymentError as exc:
        messages.error(request, str(exc))
    return redirect(_safe_next(request, "dashboard:payment_list"))


@staff_required
def payment_proof(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    return serve_private_image_inline(payment.proof_image)


# --------------------------------------------------------------------------
# Customers and settings
# --------------------------------------------------------------------------
CUSTOMER_STATUSES = (("active", "Can sign in"), ("inactive", "Sign-in blocked"))


def _customer_queryset():
    paid_total = (
        Payment.objects.filter(customer=OuterRef("pk"), status=Payment.Status.COMPLETED)
        .order_by()
        .values("customer")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    return User.objects.filter(is_staff=False).annotate(
        order_count=Count("orders", distinct=True),
        request_count=Count("capstone_requests", distinct=True),
        paid_total=Subquery(paid_total),
    )


@staff_required
def customer_list(request):
    customers = _customer_queryset()
    q = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    if q:
        customers = customers.filter(
            Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(school__icontains=q) | Q(phone_number__icontains=q)
        )
    if status == "active":
        customers = customers.filter(is_active=True)
    elif status == "inactive":
        customers = customers.filter(is_active=False)
    else:
        status = ""
    page = _paginate(request, customers.order_by("-date_joined"))
    return render(request, "dashboard/customer_list.html", {
        "page_obj": page, "customers": page.object_list, "q": q, "status": status,
        "statuses": CUSTOMER_STATUSES,
    })


@staff_required
@sensitive_post_parameters("password1", "password2")
@require_http_methods(["GET", "POST"])
def customer_form(request, pk=None):
    customer = get_object_or_404(User, pk=pk, is_staff=False) if pk else None
    form = CustomerAdminForm(request.POST if request.method == "POST" else None, instance=customer)
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        verb = "updated" if pk else "created"
        messages.success(request, f"{customer.display_name} was {verb}.")
        return redirect("dashboard:customer_list")
    return render(request, "dashboard/customer_form.html", {"form": form, "customer": customer})


@staff_required
@require_POST
def customer_activate(request, pk):
    """Let a customer sign in when their verification email never arrived."""
    customer = get_object_or_404(User, pk=pk, is_staff=False)
    already = customer.is_active and (not customer.email_verification_required or customer.email_verified_at)
    if already:
        messages.info(request, f"{customer.display_name} can already sign in.")
    else:
        customer.is_active = True
        if customer.email_verified_at is None:
            customer.email_verified_at = timezone.now()
        customer.save(update_fields=["is_active", "email_verified_at"])
        messages.success(request, f"{customer.display_name} can now sign in. Email verification was confirmed by staff.")
    return redirect(_safe_next(request, "dashboard:customer_list"))


def _delete_files(files):
    for storage, name in files:
        storage.delete(name)


@staff_required
@require_POST
def customer_delete(request, pk):
    """Delete the account with its project requests, their conversations and contact-form messages.

    Orders and payments are financial records, so an account that has any is deactivated instead.
    """
    customer = get_object_or_404(User, pk=pk, is_staff=False)
    label = customer.display_name
    try:
        with transaction.atomic():
            requests = CapstoneRequest.objects.filter(customer=customer)
            delivered = [
                (field.storage, field.name)
                for req in requests
                for field in (req.concept_file, req.delivered_source, req.delivered_documentation) if field
            ]
            requests.delete()  # Cascades to every message in each request's conversation.
            ContactMessage.objects.filter(email__iexact=customer.email).delete()
            customer.delete()
            transaction.on_commit(lambda: _delete_files(delivered))
        messages.success(request, f"{label} was deleted with their project requests and messages.")
    except ProtectedError:
        if customer.is_active:
            customer.is_active = False
            customer.save(update_fields=["is_active"])
        messages.warning(
            request,
            f"{label} has orders or payments, so the account was deactivated instead of deleted.",
        )
    return redirect("dashboard:customer_list")


@staff_required
def message_list(request):
    msgs = ContactMessage.objects.all()
    q = request.GET.get("q", "").strip()[:100]
    resolution = request.GET.get("resolution", "open")
    if q:
        msgs = msgs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(subject__icontains=q) | Q(message__icontains=q))
    if resolution in {"open", "resolved"}:
        msgs = msgs.filter(is_resolved=resolution == "resolved")
    else:
        resolution = ""
    page = _paginate(request, msgs)
    return render(request, "dashboard/message_list.html", {"page_obj": page, "contact_messages": page.object_list,
                  "q": q, "resolution": resolution})


@staff_required
@require_POST
def message_resolve(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    message.is_resolved = True
    message.save(update_fields=["is_resolved"])
    messages.success(request, "Message marked as resolved.")
    return redirect(_safe_next(request, reverse("dashboard:message_list")))


# --------------------------------------------------------------------------
# Customer comments (testimonials)
# --------------------------------------------------------------------------
@staff_required
def testimonial_list(request):
    status = request.GET.get("status", "")
    items = Testimonial.objects.select_related("user", "portfolio_project").order_by("-created_at")
    if status in Testimonial.Status.values:
        items = items.filter(status=status)
    else:
        status = ""
    q = request.GET.get("q", "").strip()[:100]
    if q:
        items = items.filter(Q(name__icontains=q) | Q(message__icontains=q) | Q(user__email__icontains=q)
                             | Q(portfolio_project__title__icontains=q))
    counts = dict(Testimonial.objects.order_by().values_list("status").annotate(n=Count("id")))
    tabs = [("", "All", sum(counts.values()))] + [
        (value, label, counts.get(value, 0)) for value, label in Testimonial.Status.choices
    ]
    page = _paginate(request, items)
    return render(
        request, "dashboard/testimonial_list.html",
        {"page_obj": page, "testimonials": page.object_list, "status": status, "tabs": tabs, "q": q,
         "statuses": Testimonial.Status.choices},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def testimonial_form(request, pk=None):
    item = get_object_or_404(Testimonial, pk=pk) if pk else None
    form = TestimonialAdminForm(
        request.POST if request.method == "POST" else None, instance=item, initial=None if item else {"status": Testimonial.Status.APPROVED}
    )
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(request, f"Comment from {item.name} saved ({item.get_status_display().lower()}).")
        return redirect("dashboard:testimonial_list")
    return render(request, "dashboard/testimonial_form.html", {"form": form, "item": item})


TESTIMONIAL_ACTIONS = {
    "approve": ({"status": Testimonial.Status.APPROVED}, "Comment approved. It is now on the home page."),
    "hide": ({"status": Testimonial.Status.HIDDEN, "is_featured": False}, "Comment hidden from the home page."),
    "feature": ({"is_featured": True}, "Comment featured. It will show first."),
    "unfeature": ({"is_featured": False}, "Comment is no longer featured."),
}


@staff_required
@require_POST
def testimonial_action(request, pk):
    item = get_object_or_404(Testimonial, pk=pk)
    action = TESTIMONIAL_ACTIONS.get(request.POST.get("action"))
    if action is None:
        messages.error(request, "Unknown action.")
    else:
        changes, text = action
        for field, value in changes.items():
            setattr(item, field, value)
        item.save()
        messages.success(request, text)
    return redirect(_safe_next(request, reverse("dashboard:testimonial_list")))


@staff_required
@require_POST
def testimonial_delete(request, pk):
    item = get_object_or_404(Testimonial, pk=pk)
    item.delete()
    messages.success(request, f"Comment from {item.name} deleted.")
    return redirect("dashboard:testimonial_list")


@staff_required
@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@require_http_methods(["GET", "POST"])
def site_settings(request):
    action = request.POST.get("action", "store") if request.method == "POST" else None
    if action not in {None, "store", "profile", "password"}:
        return HttpResponseBadRequest("Choose a profile, password or store update.")
    instance = SiteSettings.load()
    form = SiteSettingsForm(request.POST if action == "store" else None,
                            request.FILES if action == "store" else None, instance=instance)
    if action == "store" and form.is_valid():
        form.save()
        messages.success(request, "Store settings saved.")
        return redirect("dashboard:settings")
    context, success_message = account_settings_forms(request)
    if success_message:
        messages.success(request, success_message)
        return redirect("dashboard:settings")
    return render(request, "dashboard/settings.html", {"form": form, **context})
