from django.contrib import messages
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from capstone.models import CapstoneProject
from core.forms import ContactForm
from core.models import PortfolioPresentation, PortfolioProject, PortfolioScreenshot, Testimonial
from core.downloads import serve_private_image_inline
from core.network import client_ip
from core.legal import get_document
from core.notifications import send_templated_email
from payments.providers import get_checkout_providers


def _join(labels):
    return ", ".join(labels[:-1]) + " and " + labels[-1] if len(labels) > 1 else "".join(labels)


def _payment_faqs():
    """Answers that describe the payment methods actually enabled, not every method the code supports."""
    providers = [p for p in get_checkout_providers() if p.is_configured()]
    if not providers:
        return [(
            "Which payment methods do you accept?",
            "Online payment is being set up. Contact us to arrange payment for your accepted project quote.",
        )]
    instant = [p.label for p in providers if not p.is_manual]
    manual = [p.label for p in providers if p.is_manual]
    delivery = "After you accept a quote and payment is confirmed, we build your project and upload the agreed deliverables to your private request page."
    if instant:
        delivery += f" {_join(instant)} payments are confirmed online."
    if manual:
        delivery += f" We verify {_join(manual)} payments before work starts."
    methods = f"{_join([p.label for p in providers])}."
    if any(p.method == "card" for p in providers):
        methods += (" Card details are entered in a secure form provided by our payment partner, so we never "
                    "see or store your card number.")
    return [
        ("How do I receive my project?", delivery),
        ("Which payment methods do you accept?", methods),
    ]


FAQS = [
    (
        "Who can request a project?",
        "We build custom web applications, mobile applications and software for student capstone projects, "
        "local government units, military organizations and businesses. Submit your requirements to discuss a suitable scope.",
    ),
    (
        "Do I need to pay before receiving a quote?",
        "Submitting a project request is free. We review your requirements and send a quote with the scope, "
        "price and timeline. You decide whether to accept before making a payment.",
    ),
    (
        "Do you help with installation?",
        "Setup, documentation, training and student walkthroughs can be included in your project scope. "
        "Tell us what support you need so it can be reflected in the quote.",
    ),
]


SERVICE_CARDS = [
    {"value": "web", "label": "Web applications", "icon": "window-stack",
     "text": "Custom websites, portals, dashboards and information systems built around your workflow."},
    {"value": "mobile", "label": "Mobile applications", "icon": "phone",
     "text": "Mobile apps for student projects, field teams, service delivery and business operations."},
    {"value": "desktop", "label": "Software systems", "icon": "pc-display",
     "text": "Desktop applications and tailored software for records, inventory and other operational needs."},
]
CLIENT_CARDS = [
    {"value": "student", "label": "Student capstone projects", "icon": "mortarboard",
     "text": "Project development, technical guidance and walkthroughs aligned with your academic requirements."},
    {"value": "lgu", "label": "Local government units", "icon": "bank",
     "text": "Systems for local services, records, departmental workflows and public administration."},
    {"value": "military", "label": "Military organizations", "icon": "shield-check",
     "text": "Administrative tools for personnel, logistics, records and organizational workflows."},
    {"value": "business", "label": "Businesses", "icon": "briefcase",
     "text": "Applications for daily operations, customer services, reporting and business processes."},
]


def _tech_stack(limit=18):
    """Distinct technologies used by published project services."""
    seen = {}
    stacks = CapstoneProject.objects.published().values_list("tech_stack", flat=True)
    for stack in stacks:
        for name in (stack or "").split(","):
            name = name.strip()
            if name and name.lower() not in seen:
                seen[name.lower()] = name
    return list(seen.values())[:limit]


def _landing_context(request, contact_form=None):
    """Introduce custom development services and the clients we build for."""
    approved = Testimonial.objects.approved()
    summary = approved.aggregate(average=Avg("rating"), total=Count("id"))
    presentation = PortfolioPresentation.load()
    portfolio_projects = list(PortfolioProject.objects.filter(is_published=True).prefetch_related("screenshots")[:6])
    featured_project = portfolio_projects[0] if portfolio_projects and portfolio_projects[0].is_featured else None
    return {
        "services": SERVICE_CARDS,
        "client_types": CLIENT_CARDS,
        "tech_stack": _tech_stack(),
        "capstone_count": CapstoneProject.objects.published().count(),
        "portfolio_presentation": presentation,
        "portfolio_projects": portfolio_projects,
        "featured_portfolio_project": featured_project,
        "portfolio_grid_projects": portfolio_projects[1:] if featured_project else portfolio_projects,
        "testimonials": approved.select_related("user", "portfolio_project__request")[:6],
        "testimonial_summary": summary,
        "can_leave_testimonial": Testimonial.customer_is_eligible(request.user) or (
            request.user.is_authenticated and PortfolioProject.objects.filter(
                Q(customer=request.user) | Q(customer__isnull=True, request__customer=request.user)
            ).exists()
        ),
        "faqs": _payment_faqs() + FAQS,
        "contact_form": contact_form if contact_form is not None else ContactForm(),
    }


def home(request):
    return render(request, "core/home.html", _landing_context(request))


def portfolio_list(request):
    projects = PortfolioProject.objects.filter(is_published=True).prefetch_related("screenshots")
    project_type, stage = request.GET.get("project_type", ""), request.GET.get("stage", "")
    if project_type in PortfolioProject.ProjectType.values:
        projects = projects.filter(project_type=project_type)
    if stage in PortfolioProject.Stage.values:
        projects = projects.filter(stage=stage)
    page = Paginator(projects, 12).get_page(request.GET.get("page"))
    return render(request, "core/portfolio_list.html", {"projects": page.object_list, "page_obj": page,
                  "portfolio_presentation": PortfolioPresentation.load(),
                  "project_type": project_type, "stage": stage, "project_types": PortfolioProject.ProjectType.choices,
                  "stages": PortfolioProject.Stage.choices})


def portfolio_detail(request, slug):
    project = get_object_or_404(PortfolioProject.objects.select_related("request").prefetch_related("screenshots"), slug=slug)
    own = project.customer_can_review(request.user)
    staff = request.user.is_authenticated and request.user.is_active and request.user.is_staff
    if not project.is_published and not (staff or own):
        raise Http404("Project not available.")
    reviews = project.testimonials.approved().select_related("user", "portfolio_project__request")
    return render(request, "core/portfolio_detail.html", {"project": project, "reviews": reviews, "can_review": own})


def portfolio_image(request, pk):
    screenshot = get_object_or_404(PortfolioScreenshot.objects.select_related("project__request"), pk=pk)
    project = screenshot.project
    staff = request.user.is_authenticated and request.user.is_active and request.user.is_staff
    if not project.is_published and not (staff or project.customer_can_review(request.user)):
        raise Http404("Image not available.")
    response = serve_private_image_inline(screenshot.image)
    response["Cache-Control"] = "private, no-store"
    return response


# Each contact message emails the owner, so cap submissions per client address.
# The default cache is per process; use a shared cache (e.g. Redis) to make the cap global.
CONTACT_LIMIT = 5
CONTACT_WINDOW_SECONDS = 60 * 60


def _contact_rate_limited(request):
    key = f"contact-rate:{client_ip(request) or 'unknown'}"
    cache.add(key, 0, CONTACT_WINDOW_SECONDS)
    try:
        return cache.incr(key) > CONTACT_LIMIT
    except ValueError:  # expired between add() and incr()
        cache.set(key, 1, CONTACT_WINDOW_SECONDS)
        return False


@require_POST
def contact(request):
    form = ContactForm(request.POST)
    if form.is_valid() and _contact_rate_limited(request):
        messages.error(request, "You have sent several messages recently. Please wait an hour or email us directly.")
        return render(request, "core/home.html", _landing_context(request, form), status=429)
    if form.is_valid():
        msg = form.save()
        from core.models import SiteSettings

        send_templated_email(
            f"New message: {msg.subject}", "contact_message", {"msg": msg}, [SiteSettings.load().contact_email]
        )
        messages.success(request, "Thanks for reaching out! We usually reply within one business day.")
        return redirect("/#contact")
    messages.error(request, "Please check the contact form and try again.")
    return render(request, "core/home.html", _landing_context(request, form), status=400)


def terms(request):
    return render(request, "core/terms.html", {"document": get_document("license")})


def privacy(request):
    return render(request, "core/privacy.html", {"document": get_document("privacy")})


def license_agreement(request):
    return render(request, "core/legal/document.html", {"document": get_document("license")})


def legal_document(request, kind, version):
    try:
        document = get_document(kind, version)
    except KeyError as exc:
        raise Http404("Document version not found.") from exc
    return render(request, "core/legal/document.html", {"document": document})
