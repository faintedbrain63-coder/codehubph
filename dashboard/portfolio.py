from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from core.models import PortfolioPresentation, PortfolioProject
from dashboard.decorators import staff_required
from dashboard.forms import PortfolioPresentationForm, PortfolioProjectForm, PortfolioScreenshotFormSet
from dashboard.views import _paginate


@staff_required
@require_http_methods(["GET", "POST"])
def presentation(request):
    instance = PortfolioPresentation.load()
    form = PortfolioPresentationForm(request.POST if request.method == "POST" else None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your portfolio introduction and profile have been saved.")
        return redirect("dashboard:portfolio_presentation")
    return render(request, "dashboard/portfolio_presentation.html", {"form": form})


@staff_required
def project_list(request):
    projects = PortfolioProject.objects.select_related("customer").prefetch_related("screenshots")
    q = request.GET.get("q", "").strip()[:100]
    stage, project_type = request.GET.get("stage", ""), request.GET.get("project_type", "")
    if q:
        projects = projects.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(tech_stack__icontains=q) | Q(customer__email__icontains=q))
    if stage in PortfolioProject.Stage.values:
        projects = projects.filter(stage=stage)
    if project_type in PortfolioProject.ProjectType.values:
        projects = projects.filter(project_type=project_type)
    page = _paginate(request, projects)
    return render(request, "dashboard/portfolio_list.html", {"projects": page.object_list, "page_obj": page, "q": q,
                  "stage": stage, "project_type": project_type, "stages": PortfolioProject.Stage.choices,
                  "project_types": PortfolioProject.ProjectType.choices})


@staff_required
@require_http_methods(["GET", "POST"])
def project_form(request, pk=None):
    project = get_object_or_404(PortfolioProject, pk=pk) if pk else PortfolioProject()
    data = request.POST if request.method == "POST" else None
    form = PortfolioProjectForm(data, instance=project)
    formset = PortfolioScreenshotFormSet(data, request.FILES or None, instance=project, prefix="images")
    if request.method == "POST":
        valid_project, valid_images = form.is_valid(), formset.is_valid()
        if valid_project and valid_images:
            with transaction.atomic():
                project = form.save()
                formset.instance = project
                formset.save()
            messages.success(request, f'Portfolio project “{project.title}” saved.')
            if request.POST.get("save_action") == "continue":
                return redirect("dashboard:portfolio_edit", pk=project.pk)
            return redirect("dashboard:portfolio_list")
    return render(request, "dashboard/portfolio_form.html", {"form": form, "formset": formset, "project": project})


@staff_required
@require_POST
def project_delete(request, pk):
    project = get_object_or_404(PortfolioProject, pk=pk)
    title = project.title
    with transaction.atomic():
        project.delete()
    messages.success(request, f'Portfolio project “{title}” deleted. Its associated project reviews were removed.')
    return redirect("dashboard:portfolio_list")
