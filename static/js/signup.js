/* Sign-up page: form completion progress and the project pipeline preview. Vanilla JS. */
(function () {
  "use strict";

  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");

  // ----- Form completion progress -------------------------------------------
  const form = document.querySelector("[data-signup-form]");
  const progress = document.querySelector("[data-signup-progress]");
  if (form && progress) {
    const field = function (name) { return form.elements.namedItem(name); };
    const filled = function (name) { const input = field(name); return !!input && input.value.trim() !== ""; };
    const checked = function (name) { const input = field(name); return !!input && input.checked; };
    const consent = form.querySelector(".signup-consent");

    function update() {
      const email = field("email");
      const profile = filled("first_name") && filled("last_name") && !!email && email.value.trim() !== "" && email.checkValidity();
      const password = filled("password1") && field("password2").value === field("password1").value;
      const agree = checked("accept_privacy") && checked("accept_license");
      const steps = { profile: profile, security: password, agree: agree };
      Object.keys(steps).forEach(function (step) {
        const label = progress.querySelector('[data-step="' + step + '"]');
        if (label) label.classList.toggle("is-done", steps[step]);
      });
      const parts = [filled("first_name"), filled("last_name"), profile, filled("password1"), password,
        checked("accept_privacy"), checked("accept_license")];
      const done = parts.filter(Boolean).length;
      progress.style.setProperty("--progress", Math.round((done / parts.length) * 100) + "%");
      if (consent) consent.classList.toggle("is-complete", agree);
      form.classList.toggle("is-ready", profile && password && agree);
    }
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    update();
  }

  // ----- Project pipeline preview -------------------------------------------
  const flow = document.querySelector("[data-signup-flow]");
  if (flow) {
    const items = flow.querySelectorAll("li");
    const bar = flow.querySelector(".signup-flow-bar > span");
    let stage = 0, timer = null;

    function paint() {
      items.forEach(function (item, index) {
        item.classList.toggle("is-done", index < stage);
        item.classList.toggle("is-active", index === stage);
      });
      if (bar) bar.style.setProperty("--flow", Math.round((Math.min(stage, items.length) / items.length) * 100) + "%");
    }
    function tick() {
      // Hold on the finished state for one extra beat before starting over.
      stage = stage > items.length ? 0 : stage + 1;
      paint();
    }
    function start() {
      if (timer === null && !document.hidden && !motion.matches) timer = setInterval(tick, 1600);
    }
    function stop() {
      clearInterval(timer);
      timer = null;
    }
    function reset() {
      stop();
      // Without motion, show the complete journey as a static summary.
      stage = motion.matches ? items.length : 0;
      paint();
      start();
    }
    reset();
    document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); else start(); });
    motion.addEventListener("change", reset);
  }
})();
