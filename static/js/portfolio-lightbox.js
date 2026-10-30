/* Project screenshot viewer: one dialog, keyboard, swipe, and a thumbnail rail. */
(function () {
  "use strict";

  const root = document.getElementById("portfolio-lightbox");
  if (!root || !window.bootstrap || !window.bootstrap.Modal) return;

  const slides = Array.from(root.querySelectorAll("[data-lightbox-slide]"));
  const image = root.querySelector("[data-lightbox-image]");
  const caption = root.querySelector("[data-lightbox-caption]");
  const frame = root.querySelector("[data-lightbox-frame]");
  const count = root.querySelector("[data-lightbox-count]");
  const stage = root.querySelector(".portfolio-lightbox-stage");
  if (!slides.length || !image || !frame) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const modal = window.bootstrap.Modal.getOrCreateInstance(root);
  let index = 0;
  let pointerStart = null;

  if (slides.length < 2) root.classList.add("is-solo");

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function show(next, direction) {
    const total = slides.length;
    index = (next + total) % total;
    const slide = slides[index];
    image.src = slide.getAttribute("data-src");
    image.alt = slide.getAttribute("data-alt") || "";
    const text = slide.getAttribute("data-caption") || "";
    if (caption) {
      caption.textContent = text;
      caption.hidden = !text;
    }
    if (count) count.textContent = pad(index + 1) + "  /  " + pad(total);
    slides.forEach(function (thumb, thumbIndex) {
      const active = thumbIndex === index;
      thumb.classList.toggle("is-active", active);
      if (active) thumb.setAttribute("aria-current", "true");
      else thumb.removeAttribute("aria-current");
      if (active && root.classList.contains("show")) {
        thumb.scrollIntoView({ inline: "center", block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
      }
    });
    frame.classList.remove("is-next", "is-prev");
    if (!reduceMotion && direction) {
      void frame.offsetWidth;
      frame.classList.add(direction > 0 ? "is-next" : "is-prev");
    }
  }

  function step(direction) {
    if (slides.length < 2) return;
    show(index + direction, direction);
  }

  document.querySelectorAll("[data-lightbox-open]").forEach(function (trigger) {
    trigger.addEventListener("click", function () {
      const start = Number(trigger.getAttribute("data-lightbox-open"));
      show(Number.isInteger(start) ? start : 0, 0);
      modal.show();
    });
  });

  slides.forEach(function (thumb, thumbIndex) {
    thumb.addEventListener("click", function () {
      show(thumbIndex, thumbIndex > index ? 1 : thumbIndex < index ? -1 : 0);
    });
  });

  const previous = root.querySelector("[data-lightbox-prev]");
  const next = root.querySelector("[data-lightbox-next]");
  if (previous) previous.addEventListener("click", function () { step(-1); });
  if (next) next.addEventListener("click", function () { step(1); });

  root.addEventListener("keydown", function (event) {
    if (event.key === "ArrowRight") { event.preventDefault(); step(1); }
    else if (event.key === "ArrowLeft") { event.preventDefault(); step(-1); }
  });

  if (stage) {
    stage.addEventListener("pointerdown", function (event) {
      if (event.target.closest("button")) return;
      pointerStart = event.clientX;
    });
    stage.addEventListener("pointerup", function (event) {
      if (pointerStart === null) return;
      const delta = event.clientX - pointerStart;
      pointerStart = null;
      if (Math.abs(delta) < 48) return;
      step(delta < 0 ? 1 : -1);
    });
    stage.addEventListener("pointercancel", function () { pointerStart = null; });
  }

  root.addEventListener("show.bs.modal", function () {
    document.body.classList.add("portfolio-lightbox-open");
  });
  root.addEventListener("hidden.bs.modal", function () {
    document.body.classList.remove("portfolio-lightbox-open");
    frame.classList.remove("is-next", "is-prev");
  });
})();
