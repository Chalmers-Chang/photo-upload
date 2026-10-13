function SparkleField(canvas) {
  const ctx = canvas.getContext("2d", { alpha: true });
  const GATHER = 2000;
  const BURST = 5000;
  const TRAIL = 12;
  const ARC = 0.7;
  const BOB = (96 / 2.54) * 0.25;
  const SPHERE_Y_MAX = 2880;
  const SPHERE_X_FROM = -18;
  const SPHERE_X_TO = 16;
  const TINTS = [
    "#f6e08a", "#ffe9b0", "#f6e08a", "#ffe9b0", "#ebcf6e",
    "#d8dde3", "#c5ccd4", "#e8eef2",
    "#f4efe6", "#fffcf7",
  ];
  const AXES = [];
  for (const sx of [-1, 1]) {
    for (const sy of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const m = Math.hypot(sx, sy, sz);
        AXES.push({ x: sx / m, y: sy / m, z: sz / m });
      }
    }
  }

  function cross(a, b) {
    return {
      x: a.y * b.z - a.z * b.y,
      y: a.z * b.x - a.x * b.z,
      z: a.x * b.y - a.y * b.x,
    };
  }

  function ringBasis(axis) {
    const ref = Math.abs(axis.y) < 0.9 ? { x: 0, y: 1, z: 0 } : { x: 1, y: 0, z: 0 };
    const v = cross(axis, ref);
    const vm = Math.hypot(v.x, v.y, v.z) || 1;
    const V = { x: v.x / vm, y: v.y / vm, z: v.z / vm };
    const u = cross(V, axis);
    const um = Math.hypot(u.x, u.y, u.z) || 1;
    return { u: { x: u.x / um, y: u.y / um, z: u.z / um }, v: V };
  }

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
      const lane = i % 8;
      const k = Math.floor(i / 8);
      const per = Math.ceil(GATHER / 8);
      dots.push({
        cx,
        cy,
        ring: ringBasis(AXES[lane]),
        sign: 1,
        seed: Math.random() * 40,
        theta: (k / per) * Math.PI * 2 + lane * 0.11,
        omega: 0.55 + lane * 0.03,
        spawn: Math.random() * Math.min(1.2, durationSec * 0.25),
        rMax: maxR * (0.62 + Math.random() * 0.38),
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

  function projectOnSphere(p, th, rad, rotY, rotX) {
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
    return { x: p.cx + x1 * s, y: p.cy + y1 * s };
  }

  function gatherArc(p, t) {
    if (t < p.spawn) return null;
    const u = sphereU(t, gatherSec);
    const rotY = SPHERE_Y_MAX * Math.PI / 180 * u;
    const rotX = (SPHERE_X_FROM + (SPHERE_X_TO - SPHERE_X_FROM) * u) * Math.PI / 180;
    const rad = p.rMax;
    const thNow = p.theta + p.sign * (t - p.spawn) * p.omega;
    const pts = [];
    for (let i = 0; i < TRAIL; i++) {
      const k = i / (TRAIL - 1);
      const th = thNow - p.sign * ARC * (1 - k);
      pts.push(projectOnSphere(p, th, rad, rotY, rotX));
    }
    return pts;
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
        const arc = gatherArc(p, t);
        if (!arc) continue;
        const pos = arc[arc.length - 1];
        x = pos.x;
        y = pos.y;
        p.x = x;
        p.y = y;
        breathe = 0.5 + 0.5 * Math.sin(t * p.breath + p.phase);
        const alphaG = (0.85 + 0.15 * breathe) * 0.22;
        drawRibbon(arc, p.color, Math.max(1.2, p.r * 2.2), alphaG);
        ctx.globalAlpha = alphaG;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(x, y, Math.max(0.4, p.r), 0, Math.PI * 2);
        ctx.fill();
        continue;
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
    return t0;
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
