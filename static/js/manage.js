/* Workspace interactions: accessible navigation, upload feedback and safe editing. */
(function () {
  "use strict";
  const sidebar = document.getElementById("manageSidebar");
  const main = document.querySelector(".manage-main");
  const opener = document.querySelector("[data-sidebar-open]");
  const backdrop = document.querySelector(".manage-backdrop");
  const mobile = window.matchMedia("(max-width: 991.98px)");
  let open = false;

  function setSidebar(value, restoreFocus) {
    if (!sidebar) return;
    open = Boolean(value && mobile.matches);
    document.body.classList.toggle("sidebar-open", open);
    sidebar.inert = mobile.matches && !open;
    if (main) main.inert = open;
    sidebar.setAttribute("aria-hidden", String(mobile.matches && !open));
    if (backdrop) backdrop.hidden = !open;
    if (opener) opener.setAttribute("aria-expanded", String(open));
    if (open) sidebar.focus();
    else if (restoreFocus && opener) opener.focus();
  }
  if (opener) opener.addEventListener("click", function () { setSidebar(true); });
  document.querySelectorAll("[data-sidebar-close]").forEach(function (button) {
    button.addEventListener("click", function () { setSidebar(false, true); });
  });
  mobile.addEventListener("change", function () { setSidebar(false); });
  setSidebar(false);
  document.addEventListener("keydown", function (event) {
    if (!open || event.defaultPrevented || event.target.closest(".swal2-container")) return;
    if (event.key === "Escape") { event.preventDefault(); setSidebar(false, true); }
    if (event.key !== "Tab") return;
    const focusable = Array.from(sidebar.querySelectorAll('a[href], button:not([disabled]), summary, [tabindex="0"]')).filter(function (el) { return el.getClientRects().length; });
    if (!focusable.length) { event.preventDefault(); return; }
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === sidebar)) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === sidebar)) {
      event.preventDefault(); first.focus();
    }
  });

  // File names are local feedback, never inserted as HTML or uploaded in advance.
  document.addEventListener("change", function (event) {
      const input = event.target;
      if (!input.matches('input[type="file"]')) return;
      let status = input.parentElement.querySelector("[data-upload-status]");
      if (!status) {
        status = document.createElement("span"); status.className = "workspace-upload-status";
        status.setAttribute("data-upload-status", ""); status.setAttribute("role", "status");
        input.parentElement.appendChild(status);
      }
      const file = input.files && input.files[0];
      status.textContent = file ? file.name + " · " + (file.size / (1024 * 1024)).toFixed(2) + " MB · Ready to upload on save" : "No replacement selected.";
  });

  const galleryButton = document.querySelector("[data-add-screenshot]");
  const gallery = document.querySelector("[data-gallery-forms]");
  const empty = document.getElementById("screenshot-empty-form");
  const total = document.getElementById("id_images-TOTAL_FORMS");
  if (galleryButton && gallery && empty && total) {
    function syncGallery() { galleryButton.disabled = Number(total.value) >= 12; }
    syncGallery();
    galleryButton.addEventListener("click", function () {
      const index = Number(total.value);
      if (!Number.isInteger(index) || index < 0 || index >= 12) return;
      const fragment = empty.content.cloneNode(true);
      fragment.querySelectorAll("[name], [id], [for], [aria-describedby]").forEach(function (el) {
        ["name", "id", "for", "aria-describedby"].forEach(function (attribute) {
          const value = el.getAttribute(attribute);
          if (value) el.setAttribute(attribute, value.replace(/__prefix__/g, String(index)));
        });
      });
      gallery.appendChild(fragment);
      total.value = String(index + 1);
      syncGallery();
      const added = gallery.lastElementChild.querySelector('input[type="file"]');
      if (added) added.focus();
    });
  }

  document.querySelectorAll(".table-responsive").forEach(function (region) {
    region.setAttribute("tabindex", "0");
    region.setAttribute("role", "region");
    region.setAttribute("aria-label", "Scrollable data table");
  });

  const forms = Array.from(document.querySelectorAll("[data-dirty-form]"));
  const dirty = new Set();
  let leaving = false;
  let navigationPending = false;
  forms.forEach(function (form) {
    function markDirty() { dirty.add(form); }
    if (form.querySelector(".is-invalid, [data-form-summary]")) dirty.add(form);
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);
  });
  document.addEventListener("submit", function (event) {
    if (!event.defaultPrevented && forms.includes(event.target)) dirty.delete(event.target);
  });
  window.addEventListener("beforeunload", function (event) {
    if (!leaving && dirty.size) { event.preventDefault(); event.returnValue = ""; }
  });
  document.addEventListener("click", function (event) {
    const link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button > 0 || !dirty.size) return;
    const href = link.getAttribute("href");
    if (!href || href.startsWith("#") || /^(mailto:|tel:)/i.test(href) || link.target === "_blank" || link.hasAttribute("download")) return;
    event.preventDefault();
    if (navigationPending || leaving) return;
    navigationPending = true;
    const decision = window.FBAlerts ? window.FBAlerts.confirm("You have unsaved changes. Leave this page without saving?", "Leave without saving") : Promise.resolve(window.confirm("Leave without saving your changes?"));
    decision.then(function (confirmed) {
      navigationPending = false;
      if (confirmed) { leaving = true; window.location.assign(link.href); }
    }).catch(function () { navigationPending = false; });
  });
})();
