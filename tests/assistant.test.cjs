const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

class Element {
  constructor() { this.listeners = {}; this.children = []; this.dataset = {}; this.value = ''; this.disabled = false; this.textContent = ''; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  dispatchEvent(event) { this.listeners[event.type]?.(event); }
  append(...children) { children.forEach(child => { child.parent = this; this.children.push(child); }); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this); }
  setAttribute(name, value) { this[name] = value; }
  focus() { this.focused = true; }
  add(option) { this.append(option); if (option.selected) this.value = option.value; }
}
function loadChat(fetch) {
  const ids = Object.fromEntries(['assistant-chat-form', 'assistant-question', 'assistant-messages', 'assistant-error',
    'assistant-state', 'assistant-revenue', 'revenue-as-of'].map(id => [id, new Element()]));
  const button = new Element();
  ids['assistant-chat-form'].querySelector = selector => selector.includes('csrf') ? {value: 'csrf'} : button;
  ids['assistant-chat-form'].dataset.url = '/manage/assistant/ask/';
  const document = {getElementById: id => ids[id], querySelectorAll: () => [], createElement: () => new Element()};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/assistant.js'), 'utf8'),
    {document, fetch, AbortController, setTimeout: () => 1, clearTimeout() {}});
  const submit = () => ids['assistant-chat-form'].listeners.submit({preventDefault() {}});
  return {ids, button, submit};
}
function reply(answer = 'Hello') {
  return {ok: true, headers: {get: () => 'application/json'}, json: async () => ({answer,
    revenue: {periods: [{label: 'Today', start: '2026-10-24', totals: [{currency: 'PHP', amount: '123.45', payments: 1}]}], as_of: 'now', timezone: 'Asia/Manila'}})};
}

test('chat sends only the question and CSRF, renders hostile output as text, and refreshes authoritative cards', async () => {
  let outgoing;
  const hostile = '<img src=x onerror=alert(1)>';
  const app = loadChat(async (url, options) => { outgoing = {url, options}; return reply(hostile); });
  app.ids['assistant-question'].value = 'Revenue today?';
  await app.submit();
  assert.equal(outgoing.url, '/manage/assistant/ask/');
  assert.equal(outgoing.options.headers['X-CSRFToken'], 'csrf');
  assert.deepEqual(JSON.parse(outgoing.options.body), {message: 'Revenue today?'});
  const messages = app.ids['assistant-messages'].children;
  assert.equal(messages[1].children[1].textContent, hostile);
  assert.equal(app.ids['assistant-revenue'].children[0].children[1].textContent, 'PHP 123.45');
  assert.equal(app.ids['assistant-question'].value, '');
  assert.equal(app.button.disabled, false);
});

test('failed chat leaves the question editable and removes the optimistic message', async () => {
  const app = loadChat(async () => ({ok: false, headers: {get: () => 'application/json'}, json: async () => ({error: 'Quota reached'})}));
  app.ids['assistant-question'].value = 'Keep this question';
  await app.submit();
  assert.equal(app.ids['assistant-question'].value, 'Keep this question');
  assert.equal(app.ids['assistant-messages'].children.length, 0);
  assert.equal(app.ids['assistant-error'].textContent, 'Quota reached');
  assert.equal(app.ids['assistant-question'].readOnly, false);
});

test('duplicate chat submissions cannot create duplicate paid requests', async () => {
  let finish, calls = 0;
  const app = loadChat(() => { calls++; return new Promise(resolve => { finish = resolve; }); });
  app.ids['assistant-question'].value = 'Question';
  const first = app.submit();
  await app.submit();
  assert.equal(calls, 1);
  assert.equal(app.button.disabled, true);
  finish(reply());
  await first;
  assert.equal(app.button.disabled, false);
});

test('provider changes fill the model text and endpoint; frontier reset restores the default without exposing keys', () => {
  const form = new Element();
  const controls = Object.fromEntries(['provider', 'model_name', 'endpoint', 'api_key', 'is_enabled'].map(name => [name, new Element()]));
  controls.provider.value = 'openai';
  controls.api_key.value = 'unsaved-openai-key';
  const registry = {openai: {endpoint: 'https://api.openai.com/v1', default_model: 'gpt-6-astra', selected: 'saved-model', has_key: true, discovery: true},
    glm: {endpoint: 'https://api.z.ai/api/paas/v4', model_endpoints:{'glm-5.3':'https://api.z.ai/api/coding/paas/v4'},
      default_model: 'glm-5.3', selected: 'glm-5.3', has_key: true, discovery: false}};
  const ids = {'ai-connection-form': form, 'ai-provider-registry': {textContent: JSON.stringify(registry)},
    'ai-action-result': new Element(), 'ai-key-status': new Element(), 'ai-catalog-note': new Element(),
    'ai-model-reference': new Element(), 'ai-reference-models': new Element(), 'ai-use-frontier-default': new Element(), 'ai-frontier-default': new Element()};
  const refresh = new Element(); refresh.dataset.aiAction = 'refresh';
  form.querySelector = selector => controls[selector.match(/name="(.+)"/)?.[1]];
  const document = {getElementById: id => ids[id], querySelectorAll: () => [refresh]};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/ai-settings.js'), 'utf8'),
    {document, Event: class {constructor(type) {this.type = type;}}});
  controls.provider.value = 'glm';
  controls.provider.listeners.change();
  assert.equal(controls.endpoint.value, registry.glm.model_endpoints['glm-5.3']);
  assert.equal(controls.model_name.value, 'glm-5.3');
  assert.equal(controls.api_key.value, '');
  assert.equal(controls.is_enabled.checked, false);
  assert.equal(refresh.disabled, true);
  controls.model_name.value = 'glm-5';
  controls.model_name.listeners.input();
  assert.equal(controls.endpoint.value, registry.glm.endpoint);
  controls.provider.value = 'openai';
  controls.provider.listeners.change();
  assert.equal(controls.model_name.value, 'saved-model');
  ids['ai-use-frontier-default'].listeners.click();
  assert.equal(controls.model_name.value, 'gpt-6-astra');
});
