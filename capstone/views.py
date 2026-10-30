from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from capstone.forms import CapstoneMessageForm, CapstoneRequestForm
from capstone.models import CapstoneProject, CapstoneRequest
from core.downloads import serve_private_file
from core.notifications import notify_admin_capstone, notify_capstone_status
from payments.models import Payment


def service_list(request):
    projects = CapstoneProject.objects.published()
    q = request.GET.get("q", "").strip()[:100]
    if q:
        projects = projects.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(tech_stack__icontains=q))
    field = request.GET.get("field", "")
    if field in CapstoneProject.Field.values:
        projects = projects.filter(field=field)
    else:
        field = ""
    page = Paginator(projects, 9).get_page(request.GET.get("page"))
    return render(
        request,
        "capstone/service_list.html",
        {"page_obj": page, "projects": page.object_list, "field": field, "fields": CapstoneProject.Field.choices, "q": q},
    )


def project_detail(request, slug):
    project = get_object_or_404(CapstoneProject.objects.published(), slug=slug)
    return render(request, "capstone/project_detail.html", {"project": project})


@login_required(login_url="accounts:register")  # new visitors register first, then return to this form
@require_http_methods(["GET", "POST"])
def request_create(request, slug=None):
    project = get_object_or_404(CapstoneProject.objects.published(), slug=slug) if slug else None
    initial = {"school_name": request.user.school}
    if project:
        initial.update(request_title=project.title, project_type=project.field)
    for key, values in (("client_type", CapstoneRequest.ClientType.values), ("project_type", CapstoneProject.Field.values)):
        if request.GET.get(key) in values:
            initial[key] = request.GET[key]
    form = CapstoneRequestForm(request.POST if request.method == "POST" else None, initial=initial, project=project)
    if request.method == "POST" and form.is_valid():
        req = form.save(commit=False)
        req.customer = request.user
        req.project = project
        req.save()
        transaction.on_commit(lambda: notify_admin_capstone(req, "new request submitted"))
        messages.success(
            request,
            f"Request {req.reference} sent. We will review it and send you a quote, usually within one business day.",
        )
        return redirect(req.get_absolute_url())
    return render(request, "capstone/request_form.html", {"project": project, "form": form})


@login_required
def my_requests(request):
    requests_qs = CapstoneRequest.objects.filter(customer=request.user).select_related("project")
    q = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    if q:
        requests_qs = requests_qs.filter(Q(reference__icontains=q) | Q(project__title__icontains=q) | Q(request_title__icontains=q))
    if status in CapstoneRequest.Status.values:
        requests_qs = requests_qs.filter(status=status)
    else:
        status = ""
    page = Paginator(requests_qs, 10).get_page(request.GET.get("page"))
    return render(request, "capstone/my_requests.html", {"requests": page.object_list, "page_obj": page,
                  "q": q, "status": status, "statuses": CapstoneRequest.Status.choices})


def _get_own_request(request, reference, lock=False):
    qs = CapstoneRequest.objects.select_related("project", "customer")
    if lock:
        qs = qs.select_for_update(of=("self",))
    return get_object_or_404(qs, reference=reference, customer=request.user)


@login_required
def request_detail(request, reference):
    req = _get_own_request(request, reference)
    payments = Payment.objects.filter(capstone_request=req).order_by("-created_at")
    return render(
        request,
        "capstone/request_detail.html",
        {
            "req": req,
            "thread": req.messages.select_related("sender"),
            "message_form": CapstoneMessageForm(),
            "payments": payments,
            "pending_payment": payments.filter(status=Payment.Status.AWAITING_VERIFICATION).first(),
            "steps": [(s, CapstoneRequest.Status(s).label) for s in CapstoneRequest.STEPS],
        },
    )


def _customer_transition(request, reference, new_status, success_message, admin_event):
    with transaction.atomic():
        req = _get_own_request(request, reference, lock=True)
        try:
            req.transition_to(new_status)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(req.get_absolute_url())
        if new_status == CapstoneRequest.Status.CANCELLED:
            req.cancel_reason = "Cancelled by customer."
            req.save(update_fields=["cancel_reason"])
        transaction.on_commit(lambda: notify_admin_capstone(req, admin_event))
        transaction.on_commit(lambda: notify_capstone_status(req))
    messages.success(request, success_message)
    return redirect(req.get_absolute_url())


@login_required
@require_POST
def request_accept(request, reference):
    return _customer_transition(
        request, reference, CapstoneRequest.Status.ACCEPTED,
        "Quote accepted. You can now pay to start the project.", "quote accepted by customer",
    )


@login_required
@require_POST
def request_cancel(request, reference):
    return _customer_transition(
        request, reference, CapstoneRequest.Status.CANCELLED,
        "Your request has been cancelled.", "cancelled by customer",
    )


@login_required
@require_POST
def request_complete(request, reference):
    return _customer_transition(
        request, reference, CapstoneRequest.Status.COMPLETED,
        "Thank you! The project is now marked as completed.", "marked completed by customer",
    )


@login_required
@require_POST
def request_message(request, reference):
    req = _get_own_request(request, reference)
    form = CapstoneMessageForm(request.POST)
    if form.is_valid():
        msg = form.save(commit=False)
        msg.request = req
        msg.sender = request.user
        msg.save()
        notify_admin_capstone(req, "new message from customer")
        messages.success(request, "Message sent.")
    else:
        messages.error(request, "Please write a message before sending.")
    return redirect(f"{req.get_absolute_url()}#messages")


@login_required
def request_download(request, reference, kind):
    req = _get_own_request(request, reference)
    if not req.files_unlocked:
        messages.info(request, "Files become available after payment is confirmed and the project files are uploaded.")
        return redirect(req.get_absolute_url())
    if kind == "source":
        return serve_private_file(req.source_file, f"{req.reference}-source")
    if kind == "documentation":
        if not req.documentation_file:
            raise Http404("No documentation for this project.")
        return serve_private_file(req.documentation_file, f"{req.reference}-documentation")
    raise Http404
