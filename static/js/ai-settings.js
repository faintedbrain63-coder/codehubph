(() => {
  'use strict';
  const form = document.getElementById('ai-connection-form');
  const registryNode = document.getElementById('ai-provider-registry');
  if (!form || !registryNode) return;
  const registry = JSON.parse(registryNode.textContent);
  const provider = form.querySelector('[name="provider"]');
  const model = form.querySelector('[name="model_name"]');
  const endpoint = form.querySelector('[name="endpoint"]');
  const key = form.querySelector('[name="api_key"]');
  const result = document.getElementById('ai-action-result');
  const reference = document.getElementById('ai-model-reference');
  const referenceModels = document.getElementById('ai-reference-models');
  const useDefault = document.getElementById('ai-use-frontier-default');
  const buttons = Array.from(document.querySelectorAll('[data-ai-action]'));
  let busy = false;
  function syncEndpoint() {
    const spec = registry[provider.value];
    endpoint.value = (spec.model_endpoints || {})[model.value.trim()] || spec.endpoint;
  }
  function status() {
    const spec = registry[provider.value];
    document.getElementById('ai-key-status').textContent = spec.has_key ? 'An encrypted API key is saved for this provider.' : 'No API key saved for this provider.';
    document.getElementById('ai-frontier-default').textContent = spec.default_model;
    document.getElementById('ai-catalog-note').textContent = 'Type the exact model ID supported by your API account. The frontier default is a starting value; save and test to verify access.';
    buttons.forEach(button => { button.disabled = busy || !spec.has_key || (button.dataset.aiAction === 'refresh' && !spec.discovery); });
  }
  provider.addEventListener('change', () => {
    const spec = registry[provider.value];
    model.value = spec.selected;
    syncEndpoint();
    key.value = '';
    form.querySelector('[name="is_enabled"]').checked = Boolean(spec.active);
    result.textContent = '';
    reference.hidden = true;
    referenceModels.textContent = '';
    status();
  });
  model.addEventListener('input', syncEndpoint);
  model.addEventListener('change', syncEndpoint);
  useDefault.addEventListener('click', () => {
    model.value = registry[provider.value].default_model;
    model.dispatchEvent(new Event('input', {bubbles: true}));
    model.focus();
  });
  buttons.forEach(button => button.addEventListener('click', async () => {
    if (busy) return;
    const selected = provider.value;
    const action = button.dataset.aiAction;
    if (action === 'remove' && !window.confirm('Remove the saved API key for ' + registry[selected].label + '?')) return;
    busy = true;
    status();
    provider.disabled = true;
    form.querySelector('[type="submit"]').disabled = true;
    result.className = 'small mt-3 text-body-secondary';
    result.textContent = action === 'test' ? 'Testing the saved connection…' : 'Working…';
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 65000);
    try {
      const body = new URLSearchParams({provider: selected, action});
      const response = await fetch(form.dataset.actionUrl, {method: 'POST', body, credentials: 'same-origin',
        headers: {'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value, 'Accept': 'application/json'}, signal: controller.signal});
      if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('Your session may have expired. Reload the page and sign in again.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
      if (data.models) {
        referenceModels.textContent = data.models.join('\n');
        reference.hidden = false;
      }
      if (action === 'remove') {
        registry[selected].has_key = false;
        if (registry[selected].active) {
          const active = document.getElementById('ai-active-summary');
          if (active) active.textContent = 'The chatbot is disabled. Save a key and enable a connection to get started.';
        }
        registry[selected].active = false;
        form.querySelector('[name="is_enabled"]').checked = false;
      }
      result.textContent = data.message;
      result.className = 'small mt-3 text-success';
    } catch (error) {
      result.textContent = error.name === 'AbortError' ? 'The request timed out. Please try again.' : error.message;
      result.className = 'small mt-3 text-danger';
    } finally {
      clearTimeout(timer);
      busy = false;
      provider.disabled = false;
      form.querySelector('[type="submit"]').disabled = false;
      status();
    }
  }));
  syncEndpoint();
  status();
})();
