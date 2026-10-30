"""Fixed official endpoints. Model catalogues are starting choices, not access guarantees.

Provider documentation and catalogue maintenance are recorded in docs/AI_PROVIDERS.md.
"""
import json
import re

import requests
from django.views.decorators.debug import sensitive_variables

from dashboard.ai.credentials import AIError

PROVIDERS = {
    "claude": {"label": "Claude / Anthropic", "base_url": "https://api.anthropic.com/v1", "protocol": "anthropic",
               "default_model": "claude-fable-5-1",
               "models": ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"], "discovery": True},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "protocol": "responses",
               "default_model": "gpt-6-astra",
               "models": ["gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna", "gpt-5-mini"], "discovery": True},
    "kimi": {"label": "Kimi / Moonshot", "base_url": "https://api.moonshot.ai/v1", "protocol": "chat",
             "default_model": "kimi-k3.1-pro",
             "models": ["kimi-k3.1-pro", "kimi-k3.1-pro-highspeed", "kimi-k3"], "discovery": True},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com", "protocol": "chat",
                 "default_model": "deepseek-flash",
                 "models": ["deepseek-flash", "deepseek-v4-pro"], "discovery": True},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "protocol": "chat",
                   "default_model": "openai/gpt-6-astra",
                   "models": ["openai/gpt-6-astra", "anthropic/claude-fable-5.1", "openai/gpt-5-mini"], "discovery": True},
    "glm": {"label": "GLM / Z.ai", "base_url": "https://api.z.ai/api/paas/v4", "protocol": "chat",
            "default_model": "glm-5.3",
            "model_endpoints": {"glm-5.3": "https://api.z.ai/api/coding/paas/v4"},
            "models": ["glm-5.3", "glm-5", "glm-4.7"], "discovery": False},
    "minimax": {"label": "MiniMax", "base_url": "https://api.minimax.io/v1", "protocol": "chat",
                "default_model": "MiniMax-M3.1-Flash",
                "models": ["MiniMax-M3.1-Flash", "MiniMax-M3"], "discovery": False},
}

FRONTIER_DEFAULTS_VERIFIED = "2026-10-24"


def provider_spec(provider):
    if provider not in PROVIDERS:
        raise AIError("Choose a supported AI provider.")
    return PROVIDERS[provider]


def endpoint_for_model(provider, model_name):
    spec = provider_spec(provider)
    return spec.get("model_endpoints", {}).get(model_name, spec["base_url"])


def model_choices(provider, connection=None):
    spec = provider_spec(provider)
    models = list(spec["models"])
    if connection:
        models += [x for x in connection.discovered_models if isinstance(x, str)]
        if connection.model_name:
            models.append(connection.model_name)
    return list(dict.fromkeys(models))


@sensitive_variables()
def request_json(provider, key, path, payload=None):
    spec = provider_spec(provider)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if spec["protocol"] == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    else:
        headers["Authorization"] = "Bearer " + key
    try:
        # Never follow a redirect with credentials. The URL is entirely server-owned.
        endpoint = endpoint_for_model(provider, payload.get("model", "") if payload else "")
        with requests.request("POST" if payload is not None else "GET", endpoint + path,
                              headers=headers, json=payload, timeout=(5, 50), allow_redirects=False, stream=True) as response:
            if response.status_code in (401, 403):
                raise AIError("The provider rejected this API key or model access. Check your key and permissions.")
            if response.status_code == 429:
                raise AIError("The provider's quota or rate limit was reached. Check your API balance or try again later.")
            if response.status_code >= 500:
                raise AIError("The AI provider is temporarily unavailable. Please try again later.")
            if response.status_code < 200 or response.status_code >= 300:
                raise AIError("The provider could not accept the request. Check the selected model and API account.")
            chunks, size = [], 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 4_000_000:
                    raise AIError("The provider response was too large. Please choose another model.")
                chunks.append(chunk)
            data = json.loads(b"".join(chunks))
            if not isinstance(data, dict):
                raise ValueError
            return data
    except requests.Timeout:
        raise AIError("The AI provider took too long to reply. Please try again.") from None
    except requests.RequestException:
        raise AIError("The server could not connect to the AI provider. Please try again later.") from None
    except (ValueError, UnicodeError):
        raise AIError("The AI provider returned an unreadable response. Please try again.") from None


def discover_models(provider, key):
    spec = provider_spec(provider)
    if not spec["discovery"]:
        raise AIError("Enter the model ID directly for this provider; model discovery is not available.")
    path = "/models?limit=1000" if provider == "claude" else "/models"
    data = request_json(provider, key, path)
    items = data.get("data", [])
    if not isinstance(items, list):
        raise AIError("The provider did not return a model list.")
    found = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("id", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}", name):
            continue
        if item.get("lifecycle") == "retired":
            continue
        if provider == "openai" and (not name.startswith(("gpt-", "o1", "o3", "o4")) or
                any(part in name for part in ("audio", "realtime", "transcribe", "tts", "image", "search", "codex", "deep-research", "instruct"))):
            continue
        if provider == "openrouter":
            architecture = item.get("architecture") or {}
            if "text" not in architecture.get("output_modalities", ["text"]):
                continue
        found.append(name)
    if not found:
        raise AIError("No compatible text models were returned. The existing model choices have been kept.")
    return sorted(set(found))[:1000]


@sensitive_variables()
def complete(connection, system, messages):
    provider = connection.provider
    spec = provider_spec(provider)
    key = connection.get_api_key()
    if not key:
        raise AIError("Add an API key in AI connection settings first.")
    protocol = spec["protocol"]
    if protocol == "responses":
        payload = {"model": connection.model_name, "instructions": system, "input": messages,
                   "max_output_tokens": 3000, "store": False}
        if connection.model_name.startswith(("gpt-5", "gpt-6")):
            payload["reasoning"] = {"effort": "low"}
        data = request_json(provider, key, "/responses", payload)
        output = data.get("output")
        parts = [part.get("text", "") for item in output if isinstance(item, dict) and item.get("type") == "message"
                 for part in (item.get("content") or []) if isinstance(part, dict) and part.get("type") == "output_text"] if isinstance(output, list) else []
        if any(not isinstance(part, str) for part in parts):
            raise AIError("The model did not return a text answer. Try another text model.")
        text = "\n".join(parts)
    elif protocol == "anthropic":
        payload = {"model": connection.model_name, "system": system, "messages": messages, "max_tokens": 3000}
        if connection.model_name == "claude-fable-5-1":
            payload["output_config"] = {"effort": "low"}
        data = request_json(provider, key, "/messages", payload)
        content = data.get("content")
        parts = [part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"] if isinstance(content, list) else []
        if any(not isinstance(part, str) for part in parts):
            raise AIError("The model did not return a text answer. Try another text model.")
        text = "\n".join(parts)
    else:
        payload = {"model": connection.model_name, "messages": [{"role": "system", "content": system}] + messages,
                   "max_tokens": 4000, "stream": False}
        if provider in {"deepseek", "glm"} or (provider == "minimax" and connection.model_name == "MiniMax-M3"):
            payload["thinking"] = {"type": "disabled"}
        if provider == "glm" and connection.model_name == "glm-5.3":
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = "low"
        if provider == "openrouter" and connection.model_name == "openai/gpt-6-astra":
            payload["reasoning"] = {"effort": "low"}
        if provider == "kimi" and connection.model_name.startswith("kimi-k3.1"):
            payload["reasoning_effort"] = "low"
        if provider == "minimax":
            payload["max_completion_tokens"] = payload.pop("max_tokens")
            payload["reasoning_split"] = True
            if connection.model_name == "MiniMax-M3.1-Flash":
                payload["reasoning_effort"] = "low"
        data = request_json(provider, key, "/chat/completions", payload)
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        answer_message = first.get("message")
        text = answer_message.get("content", "") if isinstance(answer_message, dict) else ""
    if not isinstance(text, str):
        raise AIError("The model did not return a text answer. Try another text model.")
    # Some compatible APIs put internal reasoning in the text field.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    if "<think>" in text:
        text = text.split("<think>", 1)[0].strip()
    if not text:
        raise AIError("The model returned no answer. Please try again or choose another model.")
    return text[:16000]
