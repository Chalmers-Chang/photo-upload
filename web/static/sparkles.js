function SparkleField(canvas) {
  const ctx = canvas.getContext("2d", { alpha: true });
  const GATHER = 2000;
  const BURST = 5000;
  const TRAIL = 10;
  const BOB = (96 / 2.54) * 0.25;
  const SPHERE_Y_MAX = 2880;
  const SPHERE_X_FROM = -18;
  const SPHERE_X_TO = 16;
  const TINTS = [
    "#f6e08a", "#ffe9b0", "#f6e08a", "#ffe9b0", "#ebcf6e",
    "#d8dde3", "#c5ccd4", "#e8eef2",
    "#f4efe6", "#fffcf7",
  ];
  const s2 = Math.SQRT1_2;
  const RINGS = [
    { u: { x: s2, y: s2, z: 0 }, v: { x: 0, y: 0, z: 1 } },
    { u: { x: -s2, y: s2, z: 0 }, v: { x: 0, y: 0, z: 1 } },
  ];

  let raf = 0;
  let on = false;
  let mode = "gather";
  let t0 = 0;
  let last = 0;
  let gatherSec = 10;
  let dots = [];

  function size() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    canvas.width = Math.max(1, Math.floor(w * dpr));
    canvas.height = Math.max(1, Math.floor(h * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { w, h };
  }

  function sphereU(t, durationSec) {
    const k = -Math.log(0.02) / durationSec;
    return 1 - Math.exp(-k * Math.min(Math.max(t, 0), durationSec));
  }

  function makeDots(w, h, durationSec) {
    const cx = w * 0.5;
    const cy = h * 0.48;
    const maxR = Math.min(w, h) * 0.42;
    dots = [];
    for (let i = 0; i < GATHER; i++) {
      dots.push({
        cx,
        cy,
        ring: RINGS[i % 2],
        sign: i % 4 < 2 ? 1 : -1,
        seed: Math.random() * 40,
        theta: Math.random() * Math.PI * 2,
        omega: 0.9 + Math.random() * 0.7,
        spawn: Math.random() * durationSec,
        rMax: maxR * (0.55 + Math.random() * 0.45),
        trail: [],
        breath: 0.55 + (i % 6) * 0.2,
        phase: (i % 4) * (Math.PI / 2) + (Math.random() - 0.5) * 0.4,
        r: 0.7 + Math.random() * 1.3,
        color: TINTS[i % TINTS.length],
        x: cx,
        y: cy,
      });
    }
  }

  function gatherPos(p, t) {
    if (t < p.spawn) return null;
    const u = sphereU(t, gatherSec);
    const rotY = SPHERE_Y_MAX * Math.PI / 180 * u;
    const rotX = (SPHERE_X_FROM + (SPHERE_X_TO - SPHERE_X_FROM) * u) * Math.PI / 180;
    const rad = p.rMax * (0.08 + 0.92 * u);
    const th = p.theta + p.sign * (t - p.spawn) * p.omega + 0.14 * Math.sin(t * 1.5 + p.seed);
    const { u: U, v: V } = p.ring;
    let x = (Math.cos(th) * U.x + Math.sin(th) * V.x) * rad;
    let y = (Math.cos(th) * U.y + Math.sin(th) * V.y) * rad;
    let z = (Math.cos(th) * U.z + Math.sin(th) * V.z) * rad;
    const cy = Math.cos(rotY);
    const sy = Math.sin(rotY);
    const x1 = x * cy + z * sy;
    const z1 = -x * sy + z * cy;
    const cxr = Math.cos(rotX);
    const sxr = Math.sin(rotX);
    const y1 = y * cxr - z1 * sxr;
    const z2 = y * sxr + z1 * cxr;
    const s = 1100 / (1100 + z2);
    return {
      x: p.cx + x1 * s,
      y: p.cy + y1 * s,
    };
  }

  function pushTrail(p, x, y) {
    const trail = p.trail;
    const lastPt = trail[trail.length - 1];
    if (lastPt && Math.hypot(lastPt.x - x, lastPt.y - y) < 0.6) return;
    trail.push({ x, y });
    if (trail.length > TRAIL) trail.shift();
  }

  function drawRibbon(pts, color, headW, alpha) {
    const n = pts.length;
    if (n < 2) return;
    ctx.strokeStyle = color;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (let i = 1; i < n; i++) {
      const a = i / (n - 1);
      ctx.globalAlpha = alpha * a * 0.55;
      ctx.lineWidth = Math.max(0.35, headW * (0.25 + 0.75 * a));
      const a0 = pts[i - 1];
      const a1 = pts[i];
      ctx.beginPath();
      if (i === 1) {
        ctx.moveTo(a0.x, a0.y);
        ctx.lineTo(a1.x, a1.y);
      } else {
        const prev = pts[i - 2];
        ctx.moveTo((prev.x + a0.x) * 0.5, (prev.y + a0.y) * 0.5);
        ctx.quadraticCurveTo(a0.x, a0.y, (a0.x + a1.x) * 0.5, (a0.y + a1.y) * 0.5);
      }
      ctx.stroke();
    }
  }

  function tick(now) {
    raf = 0;
    if (!on || document.hidden) return;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    last = now;
    const t = (now - t0) / 1000;
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = "rgba(0,0,0,0.08)";
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = "lighter";
    for (const p of dots) {
      let x;
      let y;
      let breathe;
      let scale = 1;
      if (mode === "gather") {
        const pos = gatherPos(p, t);
        if (!pos) continue;
        x = pos.x;
        y = pos.y;
        p.x = x;
        p.y = y;
        breathe = 0.5 + 0.5 * Math.sin(t * p.breath + p.phase);
      } else {
        const age = (now - p.burstAt) / 1000;
        const u = 1 - Math.exp(-3.2 * age);
        breathe = 0.5 + 0.5 * Math.sin(t * p.breath + p.phase);
        x = p.x0 + (p.tx - p.x0) * u;
        y = p.y0 + (p.ty - p.y0) * u + Math.sin(t * p.bob + p.phase) * BOB * u;
        const u4 = Math.min(1, Math.max(0, age));
        const seg = Math.min(3, Math.floor(u4 * 4 - 1e-9));
        const local = Math.min(1, u4 * 4 - seg);
        const e = 1 - (1 - local) * (1 - local);
        const from = 1 - 0.2 * seg;
        const to = 1 - 0.2 * (seg + 1);
        scale = from + (to - from) * e;
      }
      const alpha = (0.85 + 0.15 * breathe) * 0.22;
      const s = p.r * scale;
      pushTrail(p, x, y);
      drawRibbon(p.trail, p.color, Math.max(1.2, s * 2.2), alpha);
      ctx.globalAlpha = alpha;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(x, y, Math.max(0.4, s), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    raf = requestAnimationFrame(tick);
  }

  function start(durationSec) {
    canvas.hidden = false;
    const { w, h } = size();
    gatherSec = durationSec || 10;
    makeDots(w, h, gatherSec);
    mode = "gather";
    t0 = performance.now();
    last = t0;
    on = true;
    if (!raf) tick(t0);
  }

  function burst() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const parents = dots.map((p) => ({
      x: p.x,
      y: p.y,
      trail: p.trail,
    }));
    const cols = Math.ceil(Math.sqrt(BURST * w / h));
    const rows = Math.ceil(BURST / cols);
    const now = performance.now();
    const out = [];
    for (let i = 0; i < BURST; i++) {
      const src = parents[i % parents.length];
      const col = i % cols;
      const row = Math.floor(i / cols);
      const tx = ((col + 0.5 + (Math.random() - 0.5) * 0.85) / cols) * w;
      const ty = ((row + 0.5 + (Math.random() - 0.5) * 0.85) / rows) * h;
      out.push({
        x0: src.x + (Math.random() - 0.5) * 8,
        y0: src.y + (Math.random() - 0.5) * 8,
        tx,
        ty,
        trail: src.trail ? src.trail.slice(-4) : [],
        burstAt: now,
        bob: 0.4 + Math.random() * 0.7,
        breath: 0.55 + (i % 6) * 0.2,
        phase: (i % 4) * (Math.PI / 2) + (Math.random() - 0.5) * 0.4,
        r: (0.6 + Math.random() * 1.1) * 3,
        color: TINTS[i % TINTS.length],
      });
    }
    dots = out;
    mode = "burst";
    last = now;
  }

  function stop() {
    on = false;
    canvas.hidden = true;
    if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (raf) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
    } else if (on) {
      last = performance.now();
      tick(last);
    }
  });

  return { start, burst, stop, size };
}
