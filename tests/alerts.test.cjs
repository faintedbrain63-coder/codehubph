const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/alerts.js"), "utf8");
const flush = () => new Promise(setImmediate);

function start({ fire, confirm = () => false, messages = [], errors = [], deletePage = false } = {}) {
  const events = {};
  const forms = [];
  const window = { confirm };
  if (fire) window.Swal = { fire };
  const document = {
    body: { classList: { contains: name => deletePage && name === "delete-confirmation" } },
    addEventListener: (name, fn) => { events[name] = fn; },
    querySelector: () => null,
    querySelectorAll: selector => selector === "[data-site-message]" ? messages : selector === "#content form" ? forms : errors,
  };
  vm.runInNewContext(source, { document, window, console });
  function form({ valid = true, connected = true } = {}) {
    const attrs = { "data-confirm": "Delete <b>this</b>?", "data-confirm-button": "Delete product" };
    const result = {
      tagName: "FORM", isConnected: connected, sent: [],
      checkValidity: () => valid,
      getAttribute: key => attrs[key],
      setAttribute: (key, value) => { attrs[key] = value; },
      requestSubmit(submitter) {
        const event = submit(result, submitter);
        if (!event.defaultPrevented) result.sent.push(submitter);
      },
    };
    forms.push(result);
    return result;
  }
  function submit(form, submitter) {
    const event = { target: form, submitter, defaultPrevented: false, stopped: false,
      preventDefault() { this.defaultPrevented = true; }, stopImmediatePropagation() { this.stopped = true; } };
    events.submit(event);
    return event;
  }
  return { window, events, form, submit };
}

test("a cancelled SweetAlert confirmation never submits the form", async () => {
  const calls = [];
  const app = start({ fire: options => { calls.push(options); return Promise.resolve({ isConfirmed: false }); } });
  const form = app.form();
  const event = app.submit(form);
  await flush();
  assert.equal(event.defaultPrevented, true);
  assert.equal(event.stopped, true);
  assert.equal(form.sent.length, 0);
  assert.equal(calls[0].focusCancel, true);
  assert.equal(calls[0].text, "Delete <b>this</b>?");
  assert.equal(calls[0].html, undefined);
});

test("acceptance submits exactly once and preserves the original submitter", async () => {
  const calls = [];
  const app = start({ fire: options => { calls.push(options); return Promise.resolve({ isConfirmed: true }); } });
  const form = app.form();
  const submitter = { form, name: "action", value: "delete" };
  app.submit(form, submitter);
  await flush();
  assert.equal(calls.length, 1);
  assert.equal(form.sent.length, 1);
  assert.equal(form.sent[0], submitter);
  assert.equal(calls[0].confirmButtonText, "Delete product");
});

test("repeated clicks while confirmation is pending cannot open duplicate dialogs", async () => {
  let complete;
  let calls = 0;
  const app = start({ fire: () => { calls++; return new Promise(resolve => { complete = resolve; }); } });
  const form = app.form();
  app.submit(form);
  app.submit(form);
  await flush();
  assert.equal(calls, 1);
  complete({ isConfirmed: true });
  await flush();
  assert.equal(form.sent.length, 1);
});

test("invalid or detached forms are never submitted by a confirmation", async () => {
  let calls = 0;
  const app = start({ fire: () => { calls++; return Promise.resolve({ isConfirmed: true }); } });
  const invalid = app.form({ valid: false });
  assert.equal(app.submit(invalid).defaultPrevented, false);
  await flush();
  assert.equal(calls, 0);
  const detached = app.form({ connected: false });
  app.submit(detached);
  await flush();
  assert.equal(detached.sent.length, 0);
});

test("missing SweetAlert falls back to the browser confirmation", async () => {
  let calls = 0;
  const app = start({ confirm: () => { calls++; return true; } });
  const form = app.form();
  app.submit(form);
  await flush();
  assert.equal(calls, 1);
  assert.equal(form.sent.length, 1);
});

test("messages use plain text and persistent errors, not HTML", async () => {
  const calls = [];
  const app = start({ fire: options => { calls.push(options); return Promise.resolve({}); } });
  await app.window.FBAlerts.notify('<img src=x onerror="steal()">', "error");
  assert.equal(calls[0].text, '<img src=x onerror="steal()">');
  assert.equal(calls[0].html, undefined);
  assert.equal(calls[0].timer, undefined);
  assert.equal(calls[0].showConfirmButton, true);
});

test("notification queue never replaces a dialog that is awaiting a decision", async () => {
  const calls = [];
  const resolve = [];
  const app = start({ fire: options => { calls.push(options); return new Promise(done => resolve.push(done)); } });
  const decision = app.window.FBAlerts.confirm("Are you sure?");
  const message = app.window.FBAlerts.notify("Saved", "success");
  await flush();
  assert.equal(calls.length, 1);
  resolve[0]({ isConfirmed: false });
  assert.equal(await decision, false);
  await flush();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].toast, true);
  resolve[1]({});
  await message;
});

test("Django messages remain visible when the library is unavailable", () => {
  const element = { hidden: false, textContent: "Saved", getAttribute: () => "25" };
  const app = start({ messages: [element] });
  app.events.DOMContentLoaded();
  assert.equal(element.hidden, false);
});

test("a failed popup restores its visible server-rendered message", async () => {
  const element = { hidden: false, textContent: "Important error", getAttribute: () => "40" };
  const app = start({ fire: () => Promise.reject(new Error("Failed to render")), messages: [element] });
  app.events.DOMContentLoaded();
  await flush();
  assert.equal(element.hidden, false);
});

test("server validation errors are presented through SweetAlert", async () => {
  const calls = [];
  const app = start({ fire: options => { calls.push(options); return Promise.resolve({}); }, errors: [{ textContent: "Select a file." }] });
  app.events.DOMContentLoaded();
  await flush();
  assert.equal(calls[0].titleText, "Please review the form");
  assert.equal(calls[0].text, "Select a file.");
});

test("Django admin deletion pages get the same explicit confirmation", () => {
  const app = start({ deletePage: true });
  const form = app.form();
  app.events.DOMContentLoaded();
  assert.match(form.getAttribute("data-confirm"), /cannot be undone/);
});
