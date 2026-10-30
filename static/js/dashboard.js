/* Small dependency-free bar chart for the admin dashboard (canvas, vanilla JS). */
(function () {
  "use strict";

  const canvas = document.getElementById("revenue-chart");
  const source = document.getElementById("chart-data");
  if (!canvas || !source) return;
  const points = JSON.parse(source.textContent);

  function draw() {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);

    const styles = getComputedStyle(document.documentElement);
    const brand = styles.getPropertyValue("--brand").trim() || "#4f46e5";
    const muted = styles.getPropertyValue("--muted").trim() || "#64748b";
    const border = styles.getPropertyValue("--line").trim() || "#e2e8f0";

    const padding = { top: 16, right: 8, bottom: 28, left: 8 };
    const chartH = height - padding.top - padding.bottom;
    const max = Math.max.apply(null, points.map(function (p) { return p.value; }).concat([1]));
    const slot = (width - padding.left - padding.right) / points.length;
    const barW = Math.max(6, slot * 0.6);

    ctx.strokeStyle = border;
    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top + chartH + 0.5);
    ctx.lineTo(width - padding.right, padding.top + chartH + 0.5);
    ctx.stroke();

    ctx.font = "14px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    points.forEach(function (p, i) {
      const h = (p.value / max) * (chartH - 4);
      const x = padding.left + i * slot + (slot - barW) / 2;
      const y = padding.top + chartH - h;
      ctx.fillStyle = p.value > 0 ? brand : border;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, barW, Math.max(h, 2), 4);
      else ctx.rect(x, y, barW, Math.max(h, 2));
      ctx.fill();
      if (i % 2 === 0 || points.length <= 7) {
        ctx.fillStyle = muted;
        ctx.fillText(p.label, x + barW / 2, height - 8);
      }
    });
  }

  draw();
  window.addEventListener("resize", draw);
  window.addEventListener("themechange", draw);
})();
