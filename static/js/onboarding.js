/* First-login "how buying works" tutorial: step navigation, auto-open and remembering completion. */
(function () {
  "use strict";

  function init() {
    const modal = document.getElementById("onboarding");
    if (!modal || !window.bootstrap || !window.bootstrap.Modal) return;
    const form = modal.querySelector("[data-onboarding-form]");
    const steps = Array.from(modal.querySelectorAll("[data-onboarding-step]"));
    const back = modal.querySelector("[data-onboarding-back]");
    const next = modal.querySelector("[data-onboarding-next]");
    const last = modal.querySelector("[data-onboarding-last]");
    const progress = modal.querySelector("[data-onboarding-progress]");
    const dialog = window.bootstrap.Modal.getOrCreateInstance(modal);
    let current = 0;
    let saved = !modal.hasAttribute("data-onboarding-autostart");

    function show(index, focus) {
      current = Math.max(0, Math.min(index, steps.length - 1));
      steps.forEach(function (step, i) { step.hidden = i !== current; });
      back.hidden = current === 0;
      next.hidden = current === steps.length - 1;
      last.hidden = current !== steps.length - 1;
      progress.textContent = "Step " + (current + 1) + " of " + steps.length;
      if (focus) {
        const heading = steps[current].querySelector("h3");
        if (heading) heading.focus();
      }
    }

    // Finishing, skipping or dismissing all count as done, so the tutorial never reappears uninvited.
    function remember() {
      if (saved) return;
      saved = true;
      fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" } }).catch(function () { saved = false; });
    }

    next.addEventListener("click", function () { show(current + 1, true); });
    back.addEventListener("click", function () { show(current - 1, true); });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      dialog.hide();
    });
    modal.addEventListener("hidden.bs.modal", function () { remember(); show(0, false); });
    modal.addEventListener("show.bs.modal", function () { show(0, false); });

    if (!saved) dialog.show();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
