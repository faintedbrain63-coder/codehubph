const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../static/js/manage.js"), "utf8");
const flush = () => new Promise(setImmediate);

function element(attributes = {}) {
  const listeners = {};
  return {
    attributes, listeners, hidden: false, inert: false, disabled: false,
    addEventListener(name, fn) { listeners[name] = fn; },
    setAttribute(name, value) { attributes[name] = value; },
    getAttribute(name) { return attributes[name] ?? null; },
    hasAttribute(name) { return attributes[name] !== undefined; },
    closest() { return null; }, matches() { return false; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    getClientRects() { return [{}]; }, focus() { this.focused = true; },
  };
}

function start({ small = false, forms = [], confirm, gallery = null, regions = [] } = {}) {
  const listeners = {}, windowListeners = {}, classes = new Set(), assigned = [];
  const sidebar = element(), main = element(), opener = element(), backdrop = element(), close = element();
  const media = { matches: small, addEventListener(_event, fn) { this.changed = fn; } };
  const selectors = { ".manage-main": main, "[data-sidebar-open]": opener, ".manage-backdrop": backdrop,
    "[data-add-screenshot]": gallery?.button, "[data-gallery-forms]": gallery?.container };
  const ids = { manageSidebar: sidebar, "screenshot-empty-form": gallery?.template, "id_images-TOTAL_FORMS": gallery?.total };
  const document = {
    body: { classList: { toggle(name, on) { if (on) classes.add(name); else classes.delete(name); } } },
    activeElement: null, getElementById: id => ids[id] || null,
    querySelector: selector => selectors[selector] || null,
    querySelectorAll: selector => ({ "[data-sidebar-close]": [backdrop, close], ".table-responsive": regions, "[data-dirty-form]": forms }[selector] || []),
    addEventListener(name, fn) { (listeners[name] ||= []).push(fn); },
    createElement: () => element(),
  };
  const window = { matchMedia: () => media, addEventListener(name, fn) { windowListeners[name] = fn; },
    location: { assign: url => assigned.push(url) }, confirm: () => false };
  if (confirm) window.FBAlerts = { confirm };
  vm.runInNewContext(source, { document, window, console });
  function emit(name, properties = {}) {
    const event = { target: element(), defaultPrevented: false, button: 0,
      preventDefault() { this.defaultPrevented = true; }, ...properties };
    for (const listener of listeners[name] || []) listener(event);
    return event;
  }
  function beforeUnload() {
    const event = { prevented: false, preventDefault() { this.prevented = true; } };
    windowListeners.beforeunload(event);
    return event;
  }
  return { document, sidebar, main, opener, backdrop, close, media, classes, assigned, emit, beforeUnload };
}

function navigationLink(href = "/manage/products/") {
  const link = element({ href }); link.href = href;
  return { link, target: { closest: selector => selector === "a[href]" ? link : null } };
}

test("mobile menu makes the sidebar accessible and prevents background interaction", () => {
  const app = start({ small: true });
  assert.equal(app.sidebar.inert, true);
  app.opener.listeners.click();
  assert.equal(app.sidebar.inert, false);
  assert.equal(app.main.inert, true);
  assert.equal(app.backdrop.hidden, false);
  assert.equal(app.opener.attributes["aria-expanded"], "true");
  assert.equal(app.sidebar.focused, true);
});

test("Escape closes the mobile menu and restores focus", () => {
  const app = start({ small: true }); app.opener.listeners.click();
  app.emit("keydown", { key: "Escape" });
  assert.equal(app.sidebar.inert, true);
  assert.equal(app.main.inert, false);
  assert.equal(app.opener.focused, true);
  assert.equal(app.backdrop.hidden, true);
});

test("desktop resizing never leaves content or sidebar inert", () => {
  const app = start({ small: true }); app.opener.listeners.click();
  app.media.matches = false; app.media.changed();
  assert.equal(app.sidebar.inert, false);
  assert.equal(app.main.inert, false);
  assert.equal(app.classes.has("sidebar-open"), false);
});

test("Tab and Shift-Tab wrap inside the open mobile menu", () => {
  const app = start({ small: true });
  const first = element(), last = element(); app.sidebar.querySelectorAll = () => [first, last];
  app.opener.listeners.click(); app.document.activeElement = last;
  assert.equal(app.emit("keydown", { key: "Tab" }).defaultPrevented, true);
  assert.equal(first.focused, true);
  app.document.activeElement = first;
  app.emit("keydown", { key: "Tab", shiftKey: true });
  assert.equal(last.focused, true);
});

test("dirty edits warn before refresh but unchanged forms do not", () => {
  const form = element(), app = start({ forms: [form] });
  assert.equal(app.beforeUnload().prevented, false);
  form.listeners.input();
  assert.equal(app.beforeUnload().prevented, true);
});

test("a cancelled navigation keeps edits and unload protection", async () => {
  const form = element(), app = start({ forms: [form], confirm: () => Promise.resolve(false) });
  form.listeners.change();
  const { target } = navigationLink();
  assert.equal(app.emit("click", { target }).defaultPrevented, true);
  await flush();
  assert.equal(app.assigned.length, 0);
  assert.equal(app.beforeUnload().prevented, true);
});

test("server-rejected edits retain unload protection on the returned form", () => {
  const form = element(); form.querySelector = () => element();
  const app = start({ forms: [form] });
  assert.equal(app.beforeUnload().prevented, true);
});

test("confirmed navigation does not trigger a second unload warning", async () => {
  const form = element(), app = start({ forms: [form], confirm: () => Promise.resolve(true) });
  form.listeners.input(); app.emit("click", { target: navigationLink().target }); await flush();
  assert.equal(app.assigned[0], "/manage/products/");
  assert.equal(app.beforeUnload().prevented, false);
});

test("pending navigation confirmation cannot bypass unload protection or duplicate dialogs", async () => {
  let complete, calls = 0;
  const form = element(), app = start({ forms: [form], confirm: () => { calls++; return new Promise(resolve => { complete = resolve; }); } });
  form.listeners.input(); const target = navigationLink().target;
  app.emit("click", { target }); app.emit("click", { target });
  assert.equal(calls, 1);
  assert.equal(app.beforeUnload().prevented, true);
  complete(false); await flush();
});

test("invalid form submission retains protection; valid save clears it", () => {
  const form = element(), app = start({ forms: [form] }); form.listeners.input();
  app.emit("submit", { target: form, defaultPrevented: true });
  assert.equal(app.beforeUnload().prevented, true);
  app.emit("submit", { target: form });
  assert.equal(app.beforeUnload().prevented, false);
});

test("new-tab, email and same-page links do not interrupt editing", () => {
  let calls = 0;
  const form = element(), app = start({ forms: [form], confirm: () => { calls++; return Promise.resolve(false); } });
  form.listeners.input();
  for (const href of ["#images", "mailto:help@example.com", "tel:123"]) {
    assert.equal(app.emit("click", { target: navigationLink(href).target }).defaultPrevented, false);
  }
  const external = navigationLink(); external.link.target = "_blank";
  app.emit("click", { target: external.target }); assert.equal(calls, 0);
});

test("dynamically added file inputs receive safe local upload feedback", () => {
  const app = start(), input = element(); input.matches = () => true;
  const status = element(); input.parentElement = { querySelector: () => status };
  input.files = [{ name: '<img onerror="bad()">.zip', size: 2097152 }];
  app.emit("change", { target: input });
  assert.match(status.textContent, /^<img onerror="bad\(\)">\.zip · 2.00 MB/);
  assert.equal(status.innerHTML, undefined);
});

test("gallery additions replace form prefixes and stop at twelve", () => {
  const input = element({ name: "images-__prefix__-image", id: "id_images-__prefix__-image" });
  const label = element({ for: "id_images-__prefix__-image" });
  const gallery = { button: element(), total: { value: "11" },
    template: { content: { cloneNode: () => ({ querySelectorAll: () => [input, label] }) } },
    container: { appendChild() { this.appended = true; }, lastElementChild: { querySelector: () => input } } };
  start({ gallery }); gallery.button.listeners.click();
  assert.equal(input.attributes.name, "images-11-image");
  assert.equal(label.attributes.for, "id_images-11-image");
  assert.equal(gallery.total.value, "12");
  assert.equal(gallery.button.disabled, true);
  gallery.button.listeners.click(); assert.equal(gallery.total.value, "12");
});

test("scrollable tables are keyboard accessible", () => {
  const region = element(); start({ regions: [region] });
  assert.equal(region.attributes.tabindex, "0");
  assert.equal(region.attributes.role, "region");
});
