const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/onboarding.js"), "utf8");

function element(extra = {}) {
  const listeners = {};
  return {
    hidden: false, textContent: "", listeners,
    addEventListener(name, callback) { listeners[name] = callback; },
    fire(name, event = {}) { listeners[name] && listeners[name]({ preventDefault() { event.prevented = true; }, ...event }); return event; },
    querySelector: () => null, focus() { this.focused = true; },
    ...extra,
  };
}

function start({ autostart = true, bootstrap = true, fetchFails = false } = {}) {
  const steps = [1, 2, 3, 4].map(() => element({ querySelector: () => element() }));
  const parts = {
    "[data-onboarding-form]": element({ action: "/account/onboarding/done/" }),
    "[data-onboarding-back]": element(), "[data-onboarding-next]": element(),
    "[data-onboarding-last]": element(), "[data-onboarding-progress]": element(),
  };
  const modal = element({
    hasAttribute: name => name === "data-onboarding-autostart" && autostart,
    querySelector: selector => parts[selector],
    querySelectorAll: () => steps,
  });
  const state = { shown: 0, hidden: 0, posts: [] };
  const dialog = { show() { state.shown++; modal.fire("show.bs.modal"); }, hide() { state.hidden++; modal.fire("hidden.bs.modal"); } };
  const window = bootstrap ? { bootstrap: { Modal: { getOrCreateInstance: () => dialog } } } : {};
  vm.runInNewContext(source, {
    window, FormData: class {},
    document: { readyState: "complete", getElementById: id => (id === "onboarding" ? modal : null), addEventListener() {} },
    fetch: (url, options) => { state.posts.push({ url, options }); return fetchFails ? Promise.reject(new Error("offline")) : Promise.resolve({}); },
  });
  return { modal, steps, parts, state };
}

test("opens automatically for first-time customers and walks through every step", () => {
  const { steps, parts, state } = start();
  assert.equal(state.shown, 1);
  assert.deepEqual(steps.map(s => s.hidden), [false, true, true, true]);
  assert.equal(parts["[data-onboarding-back]"].hidden, true);
  for (let i = 0; i < 3; i++) parts["[data-onboarding-next]"].fire("click");
  assert.deepEqual(steps.map(s => s.hidden), [true, true, true, false]);
  assert.equal(parts["[data-onboarding-next]"].hidden, true);
  assert.equal(parts["[data-onboarding-last]"].hidden, false);
  assert.equal(parts["[data-onboarding-progress]"].textContent, "Step 4 of 4");
  parts["[data-onboarding-back]"].fire("click");
  assert.equal(parts["[data-onboarding-progress]"].textContent, "Step 3 of 4");
});

test("finishing or dismissing saves completion once and stays in the page", () => {
  const { modal, parts, state } = start();
  const event = parts["[data-onboarding-form]"].fire("submit", {});
  assert.equal(event.prevented, true);
  assert.equal(state.posts.length, 1);
  assert.equal(state.posts[0].url, "/account/onboarding/done/");
  assert.equal(state.posts[0].options.headers["X-Requested-With"], "fetch");
  modal.fire("hidden.bs.modal");
  assert.equal(state.posts.length, 1);
});

test("returning customers are not interrupted but can replay the tutorial", () => {
  const { modal, state } = start({ autostart: false });
  assert.equal(state.shown, 0);
  modal.fire("hidden.bs.modal");
  assert.equal(state.posts.length, 0);
});

test("missing Bootstrap leaves the plain form to submit normally", () => {
  const { parts, state } = start({ bootstrap: false });
  assert.equal(parts["[data-onboarding-form]"].listeners.submit, undefined);
  assert.equal(state.shown, 0);
});
