const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/app.js"), "utf8");

function start({ elements = {}, storage, clipboard } = {}) {
  const events = {};
  const attributes = {};
  const document = {
    documentElement: { setAttribute: (key, value) => { attributes[key] = value; }, getAttribute: key => attributes[key] },
    querySelectorAll: selector => elements[selector] || [],
    querySelector: () => null,
    addEventListener: (name, callback) => { events[name] = callback; },
  };
  const window = { addEventListener() {}, dispatchEvent() {}, confirm: () => true };
  vm.runInNewContext(source, {
    document, window, navigator: { clipboard },
    localStorage: storage || { getItem: () => null, setItem() {} },
    setTimeout: () => {}, Event: class {},
  });
  return { events, attributes, window };
}

test("blocked local storage does not stop form and theme initialization", () => {
  const app = start({ storage: {
    getItem() { throw new Error("Storage blocked"); },
    setItem() { throw new Error("Storage blocked"); },
  } });
  assert.equal(app.attributes["data-bs-theme"], "light");
  assert.equal(typeof app.events.DOMContentLoaded, "function");
  assert.equal(typeof app.window.FB.setLoading, "function");
});

test("missing Bootstrap still leaves the rest of the page functional", () => {
  const app = start({ elements: { ".toast": [{ classList: { contains: () => false } }] } });
  assert.doesNotThrow(() => app.events.DOMContentLoaded());
});

test("unavailable clipboard provides an accessible fallback", () => {
  let click;
  const notice = { textContent: "" };
  const button = {
    addEventListener: (_name, callback) => { click = callback; },
    getAttribute: () => "FB-EXAMPLE",
    parentElement: { querySelector: () => notice },
  };
  const app = start({ elements: { "[data-copy]": [button] } });
  app.events.DOMContentLoaded();
  assert.doesNotThrow(() => click());
  assert.match(notice.textContent, /copy.*manually/);
});

test("a second form submission is prevented while its first submission is busy", () => {
  let submit;
  let prevented = false;
  const form = {
    addEventListener: (_name, callback) => { submit = callback; },
    querySelector: () => ({}),
  };
  const app = start({ elements: { form: [form] } });
  app.events.DOMContentLoaded();
  submit({ preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
});
