/* Landing page behaviour: reveal on scroll, count-up stats, headline rotation,
   the hero paragraph type-on, a subtle 3D panel, review rail and a calm particle field. Vanilla JS. */
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

  // Compose the lower page in short sequences; content stays readable without JS.
  const motionSections = document.querySelectorAll(".landing main section:not(.lp-hero):not(.lp-tech):not(.lp-experience)");
  motionSections.forEach(function (section) {
    section.classList.add("lp-motion-section");
    const trace = document.createElement("div");
    trace.className = "lp-motion-trace";
    trace.setAttribute("aria-hidden", "true");
    section.prepend(trace);
    section.querySelectorAll(".lp-path, .portfolio-case, .developer-portrait").forEach(function (panel) {
      const sweep = document.createElement("span");
      sweep.className = "lp-reveal-sweep";
      sweep.setAttribute("aria-hidden", "true");
      panel.append(sweep);
    });
    const items = section.querySelectorAll(".developer-portrait, .developer-intro, .developer-expertise article, .developer-principles, .portfolio-heading, .portfolio-profile, .portfolio-case, .portfolio-grid > *, .lp-review, .accordion-item");
    items.forEach(function (item, index) {
      if (!item.hasAttribute("data-reveal")) item.setAttribute("data-reveal", "rise");
      item.style.setProperty("--d", String(index % 3));
    });
    section.querySelectorAll(".lp-path, .row > [data-reveal], .lp-timeline li").forEach(function (item, index) {
      item.style.setProperty("--d", String(index % 4));
    });
  });

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

  // Keyboard navigation must never land on content that is still transparent.
  document.addEventListener("focusin", function (event) {
    if (!event.target.closest) return;
    let target = event.target.closest("[data-reveal]");
    while (target) {
      target.classList.add("is-visible");
      target = target.parentElement && target.parentElement.closest("[data-reveal]");
    }
  });

  const activeSections = new Set();
  if ("IntersectionObserver" in window && !reduceMotion) {
    const sectionObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) activeSections.add(entry.target);
        else activeSections.delete(entry.target);
      });
      scheduleScroll();
    }, { rootMargin: "80px 0px" });
    motionSections.forEach(function (section) { sectionObserver.observe(section); });
  }

  // ----- Hero paragraph type-on ---------------------------------------------
  const typed = document.querySelector("[data-type]");
  if (typed) {
    const full = typed.textContent;
    const caret = typed.parentElement.querySelector(".lp-lead-caret");
    if (!reduceMotion) {
      typed.textContent = "";
      typed.classList.add("is-typing");
      if (caret) caret.hidden = false;
      let index = 0;
      const typeNext = function () {
        index += 1;
        typed.textContent = full.slice(0, index);
        if (index >= full.length) {
          typed.classList.add("is-done");
          if (caret) caret.hidden = true;
          return;
        }
        const character = full.charAt(index - 1);
        const delay = character === "." ? 420 : character === "," ? 180 : 16;
        window.setTimeout(typeNext, delay);
      };
      window.setTimeout(typeNext, 500);
    }
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

  let scrollFrame = null;
  function scheduleScroll() {
    if (scrollFrame !== null) return;
    scrollFrame = requestAnimationFrame(onScroll);
  }
  function onScroll() {
    scrollFrame = null;
    const doc = document.documentElement;
    const max = doc.scrollHeight - window.innerHeight;
    if (progress) progress.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
    if (!reduceMotion && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const measurements = Array.from(activeSections, function (section) {
        const rect = section.getBoundingClientRect();
        return { section: section, value: Math.max(0, Math.min(1, (window.innerHeight - rect.top) / (window.innerHeight + rect.height))) };
      });
      measurements.forEach(function (entry) {
        entry.section.style.setProperty("--section-progress", entry.value.toFixed(4));
      });
    }
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
  window.addEventListener("scroll", scheduleScroll, { passive: true });
  window.addEventListener("resize", scheduleScroll, { passive: true });

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

  // ----- Continuous 3D engineering sequence ----------------------------------
  const experience = document.querySelector("[data-experience]");
  if (experience) {
    const surface = experience.querySelector("[data-experience-canvas]");
    const context = surface && surface.getContext && surface.getContext("2d");
    const stage = experience.querySelector(".lp-experience-stage");
    const platforms = experience.querySelectorAll(".lp-platform");
    const counter = experience.querySelector(".lp-experience-counter");
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let experienceVisible = false, experienceFrame = null, lastPaint = 0;
    let sceneWidth = 0, sceneHeight = 0, sceneProgress = 0;
    // One full pass through the three platforms; the sequence then loops.
    const cycleDuration = 12000;
    const vertices = Array.from({ length: 96 }, function (_, index) {
      const y = 1 - (index / 95) * 2;
      const radius = Math.sqrt(1 - y * y);
      const angle = index * Math.PI * (3 - Math.sqrt(5));
      return { x: Math.cos(angle) * radius, y: y, z: Math.sin(angle) * radius, angle: angle };
    });
    function sizeExperience() {
      if (!context) return;
      sceneWidth = stage.clientWidth;
      sceneHeight = stage.clientHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 1.75);
      surface.width = Math.round(sceneWidth * ratio);
      surface.height = Math.round(sceneHeight * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
    function paintExperience(now) {
      experienceFrame = null;
      if (!experienceVisible || document.hidden || motionPreference.matches) return;
      if (now - lastPaint >= 32) {
        // Clamp the step so resuming after a pause does not skip ahead.
        sceneProgress = (sceneProgress + Math.min(now - lastPaint, 100) / cycleDuration) % 1;
        lastPaint = now;
        // Eases 0 → 1 → 0 across a cycle so the loop has no visible seam.
        const wave = (1 - Math.cos(sceneProgress * Math.PI * 2)) / 2;
        experience.style.setProperty("--experience", wave.toFixed(5));
        const phase = Math.min(2, Math.floor(sceneProgress * 3));
        platforms.forEach(function (panel, index) {
          panel.classList.toggle("is-current", index === phase);
          panel.style.setProperty("--platform-progress", Math.max(0, Math.min(1, sceneProgress * 3 - index)).toFixed(4));
        });
        if (counter) counter.textContent = "0" + (phase + 1) + " — 03";
        if (context) {
          context.clearRect(0, 0, sceneWidth, sceneHeight);
          const mobile = sceneWidth < 768;
          const centerX = sceneWidth * (mobile ? .89 : .74);
          const centerY = sceneHeight * (mobile ? .39 : .44);
          const radius = Math.min(sceneWidth * (mobile ? .3 : .185), sceneHeight * .31);
          const rotation = sceneProgress * Math.PI * 2 + now * .000055;
          const morph = wave;
          const projected = vertices.map(function (point) {
            // The sphere opens into a helical system, then resolves into a sphere.
            const spiral = point.angle + sceneProgress * 4;
            const x = point.x * (1 - morph * .55) + Math.cos(spiral) * morph * .8;
            const z = point.z * (1 - morph * .55) + Math.sin(spiral) * morph * .8;
            const y = point.y * (1 + morph * .28);
            const rx = x * Math.cos(rotation) - z * Math.sin(rotation);
            const rz = x * Math.sin(rotation) + z * Math.cos(rotation);
            const ry = y * Math.cos(.35) - rz * Math.sin(.35);
            const depth = y * Math.sin(.35) + rz * Math.cos(.35);
            const scale = 3.6 / (3.6 + depth);
            return { x: centerX + rx * radius * scale, y: centerY + ry * radius * scale, depth: depth, opacity: .25 + (1 - (depth + 1.5) / 3) * .65 };
          });
          context.lineWidth = .6;
          projected.forEach(function (point, index) {
            for (let next = index + 1; next < projected.length; next++) {
              const other = projected[next];
              const distance = Math.hypot(point.x - other.x, point.y - other.y);
              if (distance < radius * .34 && distance > 8) {
                context.strokeStyle = "rgba(109,182,255," + ((1 - distance / (radius * .34)) * point.opacity * .55).toFixed(3) + ")";
                context.beginPath(); context.moveTo(point.x, point.y); context.lineTo(other.x, other.y); context.stroke();
              }
            }
          });
          projected.sort(function (a, b) { return b.depth - a.depth; }).forEach(function (point, index) {
            context.fillStyle = index % 7 === 0 ? "rgba(167,139,250," + point.opacity + ")" : "rgba(103,232,249," + point.opacity + ")";
            context.beginPath(); context.arc(point.x, point.y, index % 7 === 0 ? 2.4 : 1.3, 0, Math.PI * 2); context.fill();
          });
          // Thin connections extend the central system into the interface.
          context.strokeStyle = "rgba(103,232,249,.18)";
          for (let line = 0; line < 3; line++) {
            const y = centerY + (line - 1) * radius * .7;
            context.beginPath(); context.moveTo(centerX + radius * .7, y);
            context.lineTo(centerX + radius * 1.15, y);
            context.lineTo(centerX + radius * 1.4, y + radius * .25);
            context.lineTo(sceneWidth, y + radius * .25); context.stroke();
          }
        }
      }
      experienceFrame = requestAnimationFrame(paintExperience);
    }
    function resumeExperience() {
      if (experienceFrame === null && experienceVisible && !document.hidden && !motionPreference.matches) experienceFrame = requestAnimationFrame(paintExperience);
    }
    function pauseExperience() {
      if (experienceFrame !== null) cancelAnimationFrame(experienceFrame);
      experienceFrame = null;
    }
    if ("IntersectionObserver" in window && !motionPreference.matches) experience.classList.add("is-enhanced");
    sizeExperience();
    if ("IntersectionObserver" in window) new IntersectionObserver(function (entries) {
      experienceVisible = entries[0].isIntersecting;
      if (experienceVisible) resumeExperience(); else pauseExperience();
    }).observe(experience);
    window.addEventListener("resize", sizeExperience, { passive: true });
    document.addEventListener("visibilitychange", function () { if (document.hidden) pauseExperience(); else resumeExperience(); });
    motionPreference.addEventListener("change", function () {
      experience.classList.toggle("is-enhanced", !motionPreference.matches && "IntersectionObserver" in window);
      if (motionPreference.matches) pauseExperience(); else { sizeExperience(); resumeExperience(); }
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
