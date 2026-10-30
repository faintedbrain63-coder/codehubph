/* Shared SweetAlert2 integration for the storefront, staff console and Django admin.
   Untrusted messages always use text/titleText, never HTML. */
(function () {
  "use strict";

  let queue = Promise.resolve();
  const approved = new WeakSet();
  const pending = new WeakSet();
  const icons = { success: "success", error: "error", danger: "error", warning: "warning", info: "info" };
  const titles = { success: "Success", error: "Please check", warning: "Please note", info: "Notice" };

  function enqueue(action) {
    const result = queue.then(action);
    queue = result.catch(function () {});
    return result;
  }

  function available() { return window.Swal && typeof window.Swal.fire === "function"; }

  function notify(message, level, title) {
    if (!available()) return Promise.resolve(false);
    const icon = icons[level] || "info";
    return enqueue(function () {
      return window.Swal.fire({
        titleText: title || titles[icon], text: String(message), icon: icon,
        target: document.querySelector(".modal.show") || "body", keydownListenerCapture: true,
        heightAuto: false, confirmButtonText: "OK", returnFocus: true,
        // Only routine success messages auto-dismiss. Errors stay readable.
        toast: icon === "success", position: icon === "success" ? "top-end" : "center",
        timer: icon === "success" ? 6000 : undefined, timerProgressBar: icon === "success",
        showConfirmButton: icon !== "success", showCloseButton: true,
      });
    });
  }

  function confirmAction(message, buttonText) {
    return enqueue(function () {
      if (!available()) return window.confirm(message);
      return window.Swal.fire({
        titleText: "Confirm action", text: String(message), icon: "warning", heightAuto: false,
        target: document.querySelector(".modal.show") || "body", keydownListenerCapture: true,
        showCancelButton: true, confirmButtonText: buttonText || "Continue",
        cancelButtonText: "Cancel", focusCancel: true, returnFocus: true,
        confirmButtonColor: "#b42336",
      }).then(function (result) { return result.isConfirmed === true; });
    });
  }

  // Capture before loading indicators and other submit handlers. Re-submit through
  // the browser so validation, CSRF fields and the original submitter are retained.
  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!form || form.tagName !== "FORM" || event.defaultPrevented) return;
    if (approved.has(form)) { approved.delete(form); return; }
    const message = form.getAttribute("data-confirm");
    if (!message) return;
    // Let the normal validation UI handle invalid forms before opening a dialog.
    if (!form.checkValidity()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (pending.has(form)) return;
    pending.add(form);
    const submitter = event.submitter;
    confirmAction(message, form.getAttribute("data-confirm-button")).then(function (confirmed) {
      pending.delete(form);
      if (!confirmed || !form.isConnected) return;
      approved.add(form);
      try {
        if (submitter && submitter.form === form) form.requestSubmit(submitter);
        else form.requestSubmit();
      } finally {
        // An invalidated form may not have dispatched another submit event.
        approved.delete(form);
      }
    }).catch(function () { pending.delete(form); });
  }, true);

  document.addEventListener("DOMContentLoaded", function () {
    // Django's delete-confirmation pages retain their server-rendered related-object
    // list; add the same explicit confirmation used by the staff console.
    if (document.body.classList.contains("delete-confirmation") || document.body.classList.contains("delete-selected-confirmation")) {
      document.querySelectorAll("#content form").forEach(function (form) {
        form.setAttribute("data-confirm", "Delete the selected records and their related objects listed on this page? This cannot be undone.");
        form.setAttribute("data-confirm-button", "Delete records");
      });
    }
    document.querySelectorAll("[data-site-message]").forEach(function (element) {
      if (!available()) return; // The visible server-rendered message is the fallback.
      const level = Number(element.getAttribute("data-level"));
      const icon = level >= 40 ? "error" : level >= 30 ? "warning" : level >= 25 ? "success" : "info";
      notify(element.textContent.trim(), icon).then(function (result) {
        element.hidden = result !== false;
      }).catch(function () { element.hidden = false; });
      element.hidden = true;
    });
    const errors = document.querySelectorAll(".invalid-feedback.d-block, .errorlist, .errornote, form > .alert-danger");
    if (errors.length && available()) {
      const texts = Array.from(errors).map(function (el) { return el.textContent.trim(); }).filter(Boolean);
      if (texts.length) notify(texts.join("\n").slice(0, 1800), "error", "Please review the form").catch(function () {});
    }
  });

  window.FBAlerts = { notify: notify, confirm: confirmAction };
})();
