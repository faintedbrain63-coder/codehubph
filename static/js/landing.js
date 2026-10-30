/* Landing page behaviour: reveal on scroll, count-up stats, headline rotation,
   a subtle 3D panel, review rail and a calm particle field. Vanilla JS. */
(function () {
  "use strict";

  window.__lpReady = true;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(pointer: fine)").matches;

  // ----- Scroll reveal + count-up -------------------------------------------
  function countUp(el) {
    const target = parseFloat(el.getAttribute("data-count-to"));
    if (isNaN(target)) return;
    const decimals = parseInt(el.getAttribute("data-decimals") || "0", 10);
    if (reduceMotion) { el.textContent = target.toFixed(decimals); return; }
    const duration = 1500;
    const start = performance.now();
    function tick(now) {
      const t = Math.min((now - start) / duration, 1);
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
      el.textContent = (target * eased).toFixed(decimals);
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  const revealTargets = document.querySelectorAll("[data-reveal], [data-timeline]");
  if ("IntersectionObserver" in window && !reduceMotion) {
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        entry.target.querySelectorAll("[data-count-to]").forEach(countUp);
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -36px 0px" });
    revealTargets.forEach(function (el) { observer.observe(el); });
  } else {
    revealTargets.forEach(function (el) {
      el.classList.add("is-visible");
      el.querySelectorAll("[data-count-to]").forEach(countUp);
    });
  }

  // ----- Headline word rotation ---------------------------------------------
  const rotator = document.querySelector("[data-rotate]");
  if (rotator && !reduceMotion) {
    let words = [];
    try { words = JSON.parse(rotator.getAttribute("data-rotate")); } catch (e) { words = []; }
    if (words.length > 1) {
      let index = 0;
      const cycle = function () {
        setTimeout(function () {
          rotator.classList.add("is-swapping");
          setTimeout(function () {
            index = (index + 1) % words.length;
            rotator.textContent = words[index];
            rotator.classList.remove("is-swapping");
            cycle();
          }, 300);
        }, 3600);
      };
      cycle();
    }
  }

  // ----- Spotlight + 3D tilt -------------------------------------------------
  if (finePointer && !reduceMotion) {
    document.querySelectorAll("[data-spotlight]").forEach(function (card) {
      card.addEventListener("pointermove", function (event) {
        const rect = card.getBoundingClientRect();
        card.style.setProperty("--mx", (event.clientX - rect.left) + "px");
        card.style.setProperty("--my", (event.clientY - rect.top) + "px");
      });
    });
  }

  const tilt = document.querySelector("[data-tilt]");
  if (tilt && finePointer && !reduceMotion) {
    const panel = tilt.querySelector(".lp-console");
    if (panel) {
      tilt.addEventListener("pointermove", function (event) {
        const rect = tilt.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - 0.5;
        const y = (event.clientY - rect.top) / rect.height - 0.5;
        panel.style.setProperty("--ry", (x * 5).toFixed(2) + "deg");
        panel.style.setProperty("--rx", (-y * 4).toFixed(2) + "deg");
      });
      tilt.addEventListener("pointerleave", function () {
        panel.style.setProperty("--ry", "0deg");
        panel.style.setProperty("--rx", "0deg");
      });
    }
  }

  // ----- Scroll progress, navbar state, aurora parallax ----------------------
  const progress = document.querySelector("[data-scroll-progress] span");
  const nav = document.querySelector(".landing .site-navbar");
  const hero = document.querySelector(".lp-hero");
  const auroras = document.querySelectorAll("[data-parallax]");
  let pointerX = 0.5;
  let pointerY = 0.5;

  function onScroll() {
    const doc = document.documentElement;
    const max = doc.scrollHeight - window.innerHeight;
    if (progress) progress.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
    if (nav && hero) {
      const past = hero.getBoundingClientRect().bottom < 72;
      nav.classList.toggle("is-past-hero", past);
      nav.classList.toggle("is-over-hero", !past);
      if (past) {
        nav.removeAttribute("data-bs-theme");
      } else {
        nav.setAttribute("data-bs-theme", "dark");
      }
    }
  }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  if (finePointer && !reduceMotion && auroras.length) {
    window.addEventListener("pointermove", function (event) {
      pointerX = event.clientX / window.innerWidth - 0.5;
      pointerY = event.clientY / window.innerHeight - 0.5;
      auroras.forEach(function (el) {
        const strength = parseFloat(el.getAttribute("data-parallax")) || 0.03;
        el.style.setProperty("--px", (pointerX * 110 * strength).toFixed(1) + "px");
        el.style.setProperty("--py", (pointerY * 110 * strength).toFixed(1) + "px");
      });
    }, { passive: true });
  }

  // ----- Review rail ---------------------------------------------------------
  document.querySelectorAll("[data-review-rail]").forEach(function (rail) {
    const track = rail.querySelector(".lp-reviews");
    if (!track) return;
    const step = function () {
      const card = track.querySelector(".lp-review");
      return card ? card.getBoundingClientRect().width + 16 : 320;
    };
    const prev = rail.querySelector("[data-rail-prev]");
    const next = rail.querySelector("[data-rail-next]");
    if (prev) prev.addEventListener("click", function () { track.scrollBy({ left: -step(), behavior: reduceMotion ? "auto" : "smooth" }); });
    if (next) next.addEventListener("click", function () { track.scrollBy({ left: step(), behavior: reduceMotion ? "auto" : "smooth" }); });
  });

  // ----- Back to top ----------------------------------------------------------
  const backTop = document.querySelector("[data-back-top]");
  if (backTop) {
    function toggleBackTop() {
      const show = window.scrollY > 520;
      backTop.classList.toggle("is-visible", show);
      backTop.setAttribute("aria-hidden", show ? "false" : "true");
      if (show) backTop.removeAttribute("tabindex");
      else backTop.setAttribute("tabindex", "-1");
    }
    toggleBackTop();
    window.addEventListener("scroll", toggleBackTop, { passive: true });
    backTop.addEventListener("click", function () {
      const main = document.getElementById("main");
      window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
      if (main) main.focus({ preventScroll: true });
    });
  }

  // ----- Particle field ------------------------------------------------------
  const canvas = document.querySelector("[data-particles]");
  if (!canvas || reduceMotion || !canvas.getContext) return;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const heroSection = canvas.closest(".lp-hero");
  const LINK_DISTANCE = 120;
  const pointer = { x: -9999, y: -9999 };
  let width = 0;
  let height = 0;
  let points = [];
  let frameId = null;
  let heroVisible = true;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = Math.min(38, Math.round((width * height) / 24000));
    points = Array.from({ length: count }, function () {
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16,
        r: Math.random() * 1.1 + 0.4,
      };
    });
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > width) p.vx *= -1;
      if (p.y < 0 || p.y > height) p.vy *= -1;

      for (let j = i + 1; j < points.length; j++) {
        const q = points[j];
        const dist = Math.hypot(p.x - q.x, p.y - q.y);
        if (dist < LINK_DISTANCE) {
          ctx.strokeStyle = "rgba(129, 140, 248," + (0.12 * (1 - dist / LINK_DISTANCE)).toFixed(3) + ")";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.stroke();
        }
      }

      const pd = Math.hypot(p.x - pointer.x, p.y - pointer.y);
      if (pd < LINK_DISTANCE * 1.35) {
        ctx.strokeStyle = "rgba(34, 211, 238," + (0.28 * (1 - pd / (LINK_DISTANCE * 1.35))).toFixed(3) + ")";
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(pointer.x, pointer.y);
        ctx.stroke();
      }

      ctx.fillStyle = "rgba(199, 210, 254, 0.55)";
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    frameId = requestAnimationFrame(draw);
  }

  function start() { if (frameId === null && heroVisible && !document.hidden) frameId = requestAnimationFrame(draw); }
  function stop() { if (frameId !== null) { cancelAnimationFrame(frameId); frameId = null; } }

  resize();
  start();

  let resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 200);
  }, { passive: true });

  if (heroSection) {
    heroSection.addEventListener("pointermove", function (event) {
      const rect = canvas.getBoundingClientRect();
      pointer.x = event.clientX - rect.left;
      pointer.y = event.clientY - rect.top;
    });
    heroSection.addEventListener("pointerleave", function () { pointer.x = pointer.y = -9999; });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        heroVisible = entries[0].isIntersecting;
        if (heroVisible) { start(); } else { stop(); }
      }).observe(heroSection);
    }
  }
  document.addEventListener("visibilitychange", function () { if (document.hidden) { stop(); } else { start(); } });
})();
