/* Site-wide behaviour in vanilla JS: theme toggle, loading buttons,
   client-side validation hints, gallery, and copy-to-clipboard. */
(function () {
  "use strict";

  // ----- Light / dark theme -------------------------------------------------
  const THEME_KEY = "fb-theme";
  const root = document.documentElement;

  function applyTheme(theme) {
    root.setAttribute("data-bs-theme", theme);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      const dark = theme === "dark";
      btn.setAttribute("aria-pressed", String(dark));
      btn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
      const icon = btn.querySelector("i");
      if (icon) icon.className = dark ? "bi bi-sun" : "bi bi-moon-stars";
    });
  }

  let savedTheme = "light";
  try { savedTheme = localStorage.getItem(THEME_KEY) || "light"; } catch (e) {}
  applyTheme(savedTheme === "dark" ? "dark" : "light");

  document.addEventListener("click", function (event) {
    const toggle = event.target.closest("[data-theme-toggle]");
    if (!toggle) return;
    const next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
    applyTheme(next);
    window.dispatchEvent(new Event("themechange"));
  });

  document.addEventListener("DOMContentLoaded", function () {
    // ----- Bootstrap validation + loading state on submit ------------------
    document.querySelectorAll("form").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (event.defaultPrevented) return;
        if (form.querySelector('[type="submit"][aria-busy="true"]:not([data-no-loading])')) {
          event.preventDefault();
          return;
        }
        if (form.classList.contains("needs-validation") && !form.checkValidity()) {
          event.preventDefault();
          event.stopPropagation();
          form.classList.add("was-validated");
          const firstInvalid = form.querySelector(":invalid");
          if (window.FBAlerts) {
            window.FBAlerts.notify("Check the highlighted fields and try again.", "error", "Please review the form").then(function () {
              if (firstInvalid) firstInvalid.focus();
            }).catch(function () { if (firstInvalid) firstInvalid.focus(); });
          } else if (firstInvalid) firstInvalid.focus();
          return;
        }
        const button = event.submitter || form.querySelector("[type=submit]");
        if (button && !button.hasAttribute("data-no-loading")) {
          setLoading(button, true);
        }
      });
    });

    // ----- Filters that apply as soon as they change ------------------------
    document.querySelectorAll("select[data-auto-submit]").forEach(function (select) {
      select.addEventListener("change", function () {
        if (select.form && select.form.requestSubmit) select.form.requestSubmit();
        else if (select.form) select.form.submit();
      });
    });

    // ----- Product gallery --------------------------------------------------
    const main = document.querySelector("[data-gallery-main]");
    document.querySelectorAll("[data-gallery-thumb]").forEach(function (thumb) {
      thumb.addEventListener("click", function () {
        if (!main) return;
        main.src = thumb.getAttribute("data-src");
        main.alt = thumb.getAttribute("data-alt") || main.alt;
        document.querySelectorAll("[data-gallery-thumb]").forEach(function (t) {
          t.setAttribute("aria-current", String(t === thumb));
        });
      });
    });

    // ----- Copy to clipboard ------------------------------------------------
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const text = btn.getAttribute("data-copy");
        function copyFailed() {
          let notice = btn.parentElement.querySelector("[data-copy-status]");
          if (!notice) {
            notice = document.createElement("span");
            notice.setAttribute("data-copy-status", "");
            notice.setAttribute("role", "status");
            notice.className = "small text-body-secondary";
            btn.parentElement.appendChild(notice);
          }
          notice.textContent = "Please select and copy the reference manually.";
        }
        if (!navigator.clipboard || !navigator.clipboard.writeText) {
          copyFailed();
          return;
        }
        navigator.clipboard.writeText(text).then(function () {
          const original = btn.innerHTML;
          btn.innerHTML = '<i class="bi bi-check2" aria-hidden="true"></i> Copied';
          setTimeout(function () { btn.innerHTML = original; }, 1800);
        }).catch(copyFailed);
      });
    });
  });

  // Exposed for checkout.js
  function setLoading(button, loading) {
    if (loading) {
      if (button.getAttribute("aria-busy") === "true") return;
      button.dataset.originalHtml = button.innerHTML;
      button.classList.add("is-loading");
      button.setAttribute("aria-busy", "true");
      button.innerHTML =
        '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>' +
        (button.getAttribute("data-loading-text") || "Please wait…");
    } else if (button.dataset.originalHtml) {
      button.classList.remove("is-loading");
      button.removeAttribute("aria-busy");
      button.innerHTML = button.dataset.originalHtml;
    }
  }

  // Reset spinners when the page is restored from the back/forward cache.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll(".btn.is-loading").forEach(function (b) { setLoading(b, false); });
  });

  window.FB = { setLoading: setLoading };
})();
