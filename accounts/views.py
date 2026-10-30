from django.contrib import messages
from django.conf import settings as django_settings
from django.contrib.auth import login, views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.debug import sensitive_post_parameters

from accounts.forms import LoginForm, ProfileForm, RegisterForm
from accounts.settings import account_settings_forms
from capstone.models import CapstoneRequest
from core.forms import ProjectTestimonialForm, TestimonialForm
from core.models import PortfolioProject, Testimonial
from orders.models import Order, OrderItem
from orders.views import resume_purchase
from payments.models import Payment


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = RegisterForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="accounts.backends.EmailBackend")
        messages.success(request, f"Welcome, {user.first_name}! Your account is ready.")
        resumed = resume_purchase(request)
        if resumed:
            return resumed
        next_url = request.POST.get("next") or request.GET.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
            return redirect(next_url)
        return redirect("accounts:dashboard")
    return render(request, "accounts/register.html", {"form": form, "next": request.POST.get("next") or request.GET.get("next", "")})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        if self.request.user.is_active and self.request.user.is_staff:
            return reverse_lazy("dashboard:home")
        return super().get_default_redirect_url()

    def form_valid(self, form):
        messages.success(self.request, f"Welcome back, {form.get_user().display_name}.")
        response = super().form_valid(form)
        return resume_purchase(self.request) or response


class LogoutView(auth_views.LogoutView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You have been signed out.")
        return response


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect(reverse_lazy("dashboard:settings") + "#security")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Your password has been changed.")
        return super().form_valid(form)


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "emails/password_reset.txt"
    subject_template_name = "emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


@login_required
def dashboard(request, customer_view=False):
    # Keep existing /account/ bookmarks and login links pointed at the user's
    # workspace. Staff can still access their own purchases explicitly.
    if request.user.is_active and request.user.is_staff and not customer_view:
        return redirect("dashboard:home")
    orders = Order.objects.filter(user=request.user)
    paid_items = OrderItem.objects.filter(order__user=request.user, order__status=Order.Status.PAID).select_related("order", "product")
    purchase_count = paid_items.count()
    q = request.GET.get("q", "").strip()[:100]
    if q:
        paid_items = paid_items.filter(Q(product_name__icontains=q) | Q(product__name__icontains=q) | Q(order__number__icontains=q))
    library_page = Paginator(paid_items.order_by("-order__paid_at", "-pk"), 12).get_page(request.GET.get("page"))
    capstone_requests = CapstoneRequest.objects.filter(customer=request.user).select_related("project")
    payments = Payment.objects.filter(customer=request.user).select_related("order", "capstone_request")
    context = {
        "purchases": library_page.object_list,
        "page_obj": library_page,
        "q": q,
        "open_orders": orders.filter(status__in=[Order.Status.PENDING, Order.Status.REJECTED, Order.Status.AWAITING_VERIFICATION])[:5],
        "capstone_requests": capstone_requests[:5],
        "pending_payments": payments.filter(
            status__in=[Payment.Status.PENDING, Payment.Status.AWAITING_VERIFICATION]
        )[:5],
        "approved_payments": payments.filter(status=Payment.Status.COMPLETED)[:5],
        "stats": {
            "purchases": purchase_count,
            "orders": orders.count(),
            "capstone": capstone_requests.exclude(
                status__in=[CapstoneRequest.Status.COMPLETED, CapstoneRequest.Status.CANCELLED]
            ).count(),
            "awaiting": payments.filter(status=Payment.Status.AWAITING_VERIFICATION).count(),
        },
    }
    template = "accounts/dashboard.html" if customer_view or django_settings.PRODUCT_SALES_ENABLED else "accounts/projects_dashboard.html"
    return render(request, template, context)


@login_required
@require_http_methods(["GET", "POST"])
def testimonial(request):
    existing = Testimonial.objects.filter(user=request.user, portfolio_project__isnull=True).first()
    eligible = Testimonial.customer_is_eligible(request.user)
    if not eligible and not existing:
        if request.method == "POST":
            messages.error(request, "You can leave a comment after your first payment is confirmed.")
            return redirect("accounts:testimonial")
        return render(request, "accounts/testimonial.html", {"eligible": False})

    initial = {} if existing else {"role": request.user.school}
    form = TestimonialForm(request.POST if request.method == "POST" else None, instance=existing, initial=initial)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.user = request.user
        item.name = request.user.get_full_name()[:100] or "Customer"
        item.status = Testimonial.Status.PENDING
        item.save()
        messages.success(
            request,
            "Thank you! Your comment was sent for review and will appear on our home page once approved.",
        )
        return redirect("accounts:testimonial")
    return render(request, "accounts/testimonial.html", {"eligible": True, "form": form, "existing": existing})


@login_required
def project_reviews(request):
    projects = PortfolioProject.objects.filter(
        Q(customer=request.user) | Q(customer__isnull=True, request__customer=request.user)
    ).prefetch_related("screenshots").select_related("request")
    page = Paginator(projects, 12).get_page(request.GET.get("page"))
    return render(request, "accounts/project_reviews.html", {"projects": page.object_list, "page_obj": page})


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def project_testimonial(request, pk):
    projects = PortfolioProject.objects.select_related("request")
    if request.method == "POST":
        projects = projects.select_for_update(of=("self",))
    project = get_object_or_404(projects, pk=pk)
    if not project.customer_can_review(request.user):
        raise Http404("Project not available.")
    existing = Testimonial.objects.filter(user=request.user, portfolio_project=project).first()
    form = ProjectTestimonialForm(request.POST if request.method == "POST" else None, instance=existing,
                                  initial={"name": existing.name if existing else request.user.first_name or "Customer"})
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.user, item.portfolio_project = request.user, project
        item.status = Testimonial.Status.PENDING
        item.publication_consented_at = timezone.now()
        item.save()
        messages.success(request, "Your project review was sent for approval. Editing it requires another review before publication.")
        return redirect("accounts:project_testimonial", pk=project.pk)
    return render(request, "accounts/project_testimonial.html", {"project": project, "form": form, "existing": existing})


@login_required
@require_POST
def onboarding_done(request):
    """Remember that the customer finished or skipped the buying tutorial."""
    if request.user.onboarding_completed_at is None:
        request.user.onboarding_completed_at = timezone.now()
        request.user.save(update_fields=["onboarding_completed_at"])
    if request.headers.get("X-Requested-With") == "fetch":
        return HttpResponse(status=204)
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
        return redirect(next_url)
    return redirect("accounts:dashboard")


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    if request.user.is_staff:
        return redirect(reverse_lazy("dashboard:settings") + "#profile")
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@require_http_methods(["GET", "POST"])
def settings(request):
    if request.user.is_staff:
        return redirect("dashboard:settings")
    if request.method == "POST" and request.POST.get("action") not in {"profile", "password"}:
        return HttpResponseBadRequest("Choose a profile or password update.")
    context, success_message = account_settings_forms(request)
    if success_message:
        messages.success(request, success_message)
        return redirect("accounts:settings")
    return render(request, "accounts/settings.html", context)
