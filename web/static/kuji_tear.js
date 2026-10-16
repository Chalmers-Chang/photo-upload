// Ichiban Kuji ticket peel: drag the bottom-left corner C to point P.
// The fold is the perpendicular bisector of CP. The front keeps the far side
// of the fold; the flap is the corner side mirrored across the fold.
function KujiTear(box, opts) {
  const face = box.querySelector(".ticket-face");
  const flap = box.querySelector(".ticket-flap");
  const grip = box.querySelector(".tear-grip");
  const onOpen = opts.onOpen || (() => {});
  let W = 0;
  let H = 0;
  let P = null;
  let rest = null;
  let drag = null;
  let anim = 0;
  let done = false;

  function measure() {
    W = box.clientWidth;
    H = box.clientHeight;
    const s = Math.max(10, Math.min(W, H) * 0.07);
    rest = { x: s, y: H - s };
  }

  function clip(pts, keep) {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i];
      const b = pts[(i + 1) % pts.length];
      const fa = keep(a);
      const fb = keep(b);
      if (fa >= 0) out.push(a);
      if ((fa >= 0) !== (fb >= 0)) {
        const t = fa / (fa - fb);
        out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      }
    }
    return out;
  }

  function poly(pts) {
    if (pts.length < 3) return "polygon(0 0, 0 0, 0 0)";
    return "polygon(" + pts.map((p) => p[0].toFixed(1) + "px " + p[1].toFixed(1) + "px").join(", ") + ")";
  }

  function render() {
    const dx = P.x;
    const dy = P.y - H;
    const len = Math.hypot(dx, dy);
    if (len < 0.5) {
      face.style.clipPath = "none";
      flap.style.clipPath = "polygon(0 0, 0 0, 0 0)";
      return;
    }
    const nx = dx / len;
    const ny = dy / len;
    const d0 = (P.x / 2) * nx + ((H + P.y) / 2) * ny;
    const rect = [[0, 0], [W, 0], [W, H], [0, H]];
    face.style.clipPath = poly(clip(rect, (p) => p[0] * nx + p[1] * ny - d0));
    flap.style.clipPath = poly(clip(rect, (p) => d0 - (p[0] * nx + p[1] * ny)));
    flap.style.transform =
      "matrix(" + [1 - 2 * nx * nx, -2 * nx * ny, -2 * nx * ny, 1 - 2 * ny * ny, 2 * d0 * nx, 2 * d0 * ny].join(",") + ")";
    const deg = (Math.atan2(nx, -ny) * 180) / Math.PI;
    flap.style.backgroundImage =
      "linear-gradient(" + deg + "deg, #fffaf0 0%, #f1e6cf 55%, #d9c7a3 100%)";
    grip.style.left = P.x + "px";
    grip.style.top = P.y + "px";
  }

  function tween(to, ms, then) {
    cancelAnimationFrame(anim);
    const from = { x: P.x, y: P.y };
    const t0 = performance.now();
    function step(now) {
      const u = Math.min(1, (now - t0) / ms);
      const e = 1 - Math.pow(1 - u, 3);
      P = { x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e };
      render();
      if (u < 1) anim = requestAnimationFrame(step);
      else if (then) then();
    }
    anim = requestAnimationFrame(step);
  }

  function local(e) {
    const r = box.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function finish() {
    done = true;
    drag = null;
    grip.hidden = true;
    box.classList.add("is-torn");
    tween({ x: W * 2.1, y: H - Math.min(W, H) * 0.08 }, 420, () => {
      box.classList.add("is-open");
      onOpen();
    });
  }

  box.addEventListener("pointerdown", (e) => {
    if (done) return;
    measure();
    const p = local(e);
    const reach = Math.max(56, Math.min(W, H) * 0.3);
    if (Math.hypot(p.x - P.x, p.y - P.y) > reach) return;
    e.preventDefault();
    cancelAnimationFrame(anim);
    box.setPointerCapture(e.pointerId);
    drag = { id: e.pointerId, ox: p.x - P.x, oy: p.y - P.y };
    box.classList.add("is-dragging");
  });

  box.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const p = local(e);
    P = { x: Math.max(0, p.x - drag.ox), y: Math.min(H * 1.6, Math.max(-H * 0.6, p.y - drag.oy)) };
    render();
    if (P.x >= W) finish();
  });

  function release(e) {
    if (!drag || e.pointerId !== drag.id) return;
    drag = null;
    box.classList.remove("is-dragging");
    if (!done) tween(rest, 300);
  }
  box.addEventListener("pointerup", release);
  box.addEventListener("pointercancel", release);

  function reset() {
    cancelAnimationFrame(anim);
    done = false;
    drag = null;
    box.classList.remove("is-torn", "is-open", "is-dragging");
    grip.hidden = false;
    measure();
    P = { x: rest.x, y: rest.y };
    render();
  }

  window.addEventListener("resize", () => {
    if (!done && !drag && box.clientWidth) reset();
  });

  return { reset };
}
