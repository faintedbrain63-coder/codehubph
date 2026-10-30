import json
import time

from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from capstone.models import CapstoneRequest
from dashboard.ai.concept import READ_TIMEOUT, analyze_concept_file
from dashboard.ai.credentials import AIError
from dashboard.ai.forms import AIConnectionForm
from dashboard.ai.knowledge import app_manual, assistant_instructions, manual_version
from dashboard.ai.providers import PROVIDERS, FRONTIER_DEFAULTS_VERIFIED, complete, discover_models, model_choices
from dashboard.ai.revenue import revenue_snapshot
from dashboard.decorators import staff_required
from dashboard.models import AdminAISettings, AIConnection, ConceptAnalysis


def _provider(request, config):
    chosen = request.POST.get("provider") if request.method == "POST" else request.GET.get("provider")
    return chosen or (config.active_connection.provider if config.active_connection else "openai")


@staff_required
@never_cache
@sensitive_post_parameters("api_key")
@sensitive_variables()
@require_http_methods(["GET", "POST"])
def connection_settings(request):
    config = AdminAISettings.load()
    provider = _provider(request, config)
    if provider not in PROVIDERS:
        return HttpResponseBadRequest("Choose a supported AI provider.")
    connection = AIConnection.objects.filter(provider=provider).first()
    form = AIConnectionForm(request.POST if request.method == "POST" else None, provider=provider, connection=connection,
                            active=config.is_enabled and config.active_connection_id == getattr(connection, "pk", None))
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                connection = connection or AIConnection(provider=provider)
                connection.model_name = form.cleaned_data["model_name"]
                if form.cleaned_data["api_key"]:
                    connection.set_api_key(form.cleaned_data["api_key"])
                connection.save()
                # Disabling an inactive connection must not disable another provider.
                if form.cleaned_data["is_enabled"]:
                    config.active_connection = connection
                    config.is_enabled = True
                elif config.active_connection_id == connection.pk:
                    config.is_enabled = False
                config.save()
            messages.success(request, "AI connection saved. Use Test connection to verify the selected key and model.")
            return redirect("/manage/settings/ai/?provider=" + provider)
        except AIError as exc:
            form.add_error(None, str(exc))
    registry = {}
    saved = {item.provider: item for item in AIConnection.objects.all() if item.provider in PROVIDERS}
    for key, spec in PROVIDERS.items():
        item = saved.get(key)
        registry[key] = {"label": spec["label"], "endpoint": spec["base_url"],
                         "model_endpoints": spec.get("model_endpoints", {}),
                         "default_model": spec["default_model"],
                         "selected": item.model_name if item else spec["default_model"],
                         "has_key": bool(item and item.encrypted_api_key), "discovery": spec["discovery"],
                         "active": bool(config.is_enabled and item and config.active_connection_id == item.pk)}
    return render(request, "dashboard/ai_settings.html", {"form": form, "provider_registry": registry,
        "connection": connection, "selected_provider": provider, "ai_config": config,
        "frontier_verified": FRONTIER_DEFAULTS_VERIFIED,
        "frontier_default": PROVIDERS[provider]["default_model"],
        "active_label": PROVIDERS.get(config.active_connection.provider, {}).get("label") if config.active_connection else ""})


def _acquire(user_id, busy_seconds=75):
    key = f"admin-ai-busy:{user_id}"
    if not cache.add(key, True, timeout=busy_seconds):
        return None
    bucket = f"admin-ai-rate:{user_id}:{int(time.time() // 60)}"
    cache.add(bucket, 0, timeout=70)
    try:
        count = cache.incr(bucket)
    except ValueError:
        count = 1
    if count > 12:
        cache.delete(key)
        return None
    return key


@staff_required
@never_cache
@sensitive_post_parameters()
@sensitive_variables()
@require_POST
def connection_action(request):
    provider, action = request.POST.get("provider"), request.POST.get("action")
    if provider not in PROVIDERS or action not in {"refresh", "test", "remove"}:
        return JsonResponse({"error": "Choose a valid provider action."}, status=400)
    connection = AIConnection.objects.filter(provider=provider).first()
    if not connection or not connection.encrypted_api_key:
        return JsonResponse({"error": "Save an API key for this provider first."}, status=400)
    if action == "remove":
        with transaction.atomic():
            connection.encrypted_api_key = ""
            connection.save(update_fields=["encrypted_api_key", "updated_at"])
            AdminAISettings.objects.filter(active_connection=connection).update(is_enabled=False)
        return JsonResponse({"message": "Saved API key removed. This connection is disabled."})
    lock = _acquire(request.user.pk)
    if not lock:
        return JsonResponse({"error": "A request is already running, or the request limit was reached. Please wait."}, status=429)
    try:
        if action == "refresh":
            models = discover_models(provider, connection.get_api_key())
            connection.discovered_models = models
            connection.models_refreshed_at = timezone.now()
            connection.save(update_fields=["discovered_models", "models_refreshed_at", "updated_at"])
            return JsonResponse({"message": "Model list refreshed for reference. Your model text has not changed.",
                                 "models": model_choices(provider, connection)})
        complete(connection, "You are testing an API connection. Respond with a short greeting.",
                 [{"role": "user", "content": "Reply with: Connection successful."}])
        return JsonResponse({"message": "Connection successful. The saved key and model returned a response."})
    except AIError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    finally:
        cache.delete(lock)


def _history_key(request):
    return f"admin_ai_history_{request.user.pk}"


@staff_required
@never_cache
@require_GET
def chat(request):
    config = AdminAISettings.load()
    ready = bool(config.is_enabled and config.active_connection and config.active_connection.encrypted_api_key)
    return render(request, "dashboard/assistant.html", {"ai_ready": ready, "ai_config": config,
        "provider_label": PROVIDERS.get(config.active_connection.provider, {}).get("label") if config.active_connection else "",
        "chat_history": request.session.get(_history_key(request), []), "revenue": revenue_snapshot(), "manual_version": manual_version()})


@staff_required
@never_cache
@sensitive_variables()
@sensitive_post_parameters()
@require_POST
def ask(request):
    if len(request.body) > 14000:
        return JsonResponse({"error": "Keep your message under 3,000 characters."}, status=400)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeError):
        return JsonResponse({"error": "Send a valid message."}, status=400)
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, str) or not message.strip() or len(message) > 3000:
        return JsonResponse({"error": "Enter a message of 1 to 3,000 characters."}, status=400)
    config = AdminAISettings.load()
    if not config.is_enabled or not config.active_connection or not config.active_connection.encrypted_api_key:
        return JsonResponse({"error": "Connect and enable an AI provider in admin settings first."}, status=409)
    lock = _acquire(request.user.pk)
    if not lock:
        return JsonResponse({"error": "A request is already running, or the request limit was reached. Please wait."}, status=429)
    try:
        snapshot = revenue_snapshot()
        history = request.session.get(_history_key(request), [])[-12:]
        outgoing = history + [{"role": "user", "content": message.strip()}]
        answer = complete(config.active_connection, assistant_instructions(snapshot), outgoing)
        request.session[_history_key(request)] = (outgoing + [{"role": "assistant", "content": answer}])[-12:]
        return JsonResponse({"answer": answer, "revenue": snapshot, "manual_version": manual_version()})
    except AIError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    finally:
        cache.delete(lock)


@staff_required
@never_cache
@require_POST
def analyze_concept(request, reference):
    req = get_object_or_404(CapstoneRequest, reference=reference)
    if not req.concept_file:
        raise Http404("The customer did not attach a file.")
    page = reverse("dashboard:capstone_request_concept_view", args=[req.reference]) + "#analysis"
    config = AdminAISettings.load()
    if not config.is_ready:
        messages.error(request, "Connect and enable an AI provider in Settings → AI connection first.")
        return redirect(page)
    lock = _acquire(request.user.pk, busy_seconds=READ_TIMEOUT + 20)
    if not lock:
        messages.error(request, "Another AI request is already running, or the request limit was reached. Please wait.")
        return redirect(page)
    try:
        fields = analyze_concept_file(config.active_connection, req)
        ConceptAnalysis.objects.update_or_create(request=req, defaults={**fields, "created_by": request.user})
        messages.success(request, "AI analysis finished. Review it before sharing or pasting the prompt.")
    except AIError as exc:
        messages.error(request, str(exc))
    finally:
        cache.delete(lock)
    return redirect(page)


@staff_required
@never_cache
@require_POST
def clear_chat(request):
    request.session.pop(_history_key(request), None)
    return redirect("dashboard:assistant")


@staff_required
@never_cache
@require_GET
def manual(request):
    text = app_manual()
    if request.GET.get("download") == "1":
        response = HttpResponse(text, content_type="text/markdown; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="CodehubPh-app-manual.md"'
        return response
    sections = []
    for chunk in text.split("\n## ")[1:]:
        title, _, body = chunk.partition("\n")
        sections.append({"title": title.strip(), "body": body.strip(), "id": f"manual-{len(sections) + 1}"})
    return render(request, "dashboard/manual.html", {"sections": sections, "manual_version": manual_version()})
