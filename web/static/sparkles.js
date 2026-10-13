function SparkleField(canvas) {
  const ctx = canvas.getContext("2d", { alpha: true });
  const GATHER = 2000;
  const BURST = 5000;
  const TRAIL = 10;
  const BOB = (96 / 2.54) * 0.25;
  const TINTS = [
    "#f6e08a", "#ffe9b0", "#f6e08a", "#ffe9b0", "#ebcf6e",
    "#d8dde3", "#c5ccd4", "#e8eef2",
    "#f4efe6", "#fffcf7",
  ];
  const DIRS = [
    { x: 1, y: 1 },
    { x: -1, y: 1 },
    { x: 1, y: -1 },
    { x: -1, y: -1 },
  ].map((d) => {
    const m = Math.hypot(d.x, d.y);
    return { x: d.x / m, y: d.y / m };
  });

  let raf = 0;
  let on = false;
  let mode = "gather";
  let t0 = 0;
  let last = 0;
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

  function noise(x, y, t, s) {
    return Math.sin(x * 0.006 + s) * Math.cos(y * 0.005 + t * 1.15 + s * 1.3);
  }

  function curl(x, y, t, s) {
    const e = 22;
    const dndx = (noise(x + e, y, t, s) - noise(x - e, y, t, s)) / (2 * e);
    const dndy = (noise(x, y + e, t, s) - noise(x, y - e, t, s)) / (2 * e);
    return { x: dndy * 1200, y: -dndx * 1200 };
  }

  function wrap(p, w, h) {
    const m = 80;
    let jumped = false;
    if (p.x < -m) {
      p.x += w + m * 2;
      jumped = true;
    } else if (p.x > w + m) {
      p.x -= w + m * 2;
      jumped = true;
    }
    if (p.y < -m) {
      p.y += h + m * 2;
      jumped = true;
    } else if (p.y > h + m) {
      p.y -= h + m * 2;
      jumped = true;
    }
    if (jumped) p.trail = [];
  }

  function makeDots(w, h) {
    dots = [];
    for (let i = 0; i < GATHER; i++) {
      const dir = DIRS[i % 4];
      const across = -dir.y;
      const down = dir.x;
      const along = (Math.random() - 0.5) * (w + h);
      const side = (Math.random() - 0.5) * Math.min(w, h) * 0.95;
      dots.push({
        dir,
        seed: Math.random() * 40,
        speed: 110 + Math.random() * 160,
        x: w * 0.5 + dir.x * along + across * side,
        y: h * 0.5 + dir.y * along + down * side,
        trail: [],
        breath: 0.55 + (i % 6) * 0.2,
        phase: (i % 4) * (Math.PI / 2) + (Math.random() - 0.5) * 0.4,
        r: 0.7 + Math.random() * 1.3,
        color: TINTS[i % TINTS.length],
      });
    }
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
    const dt = Math.min(0.05, Math.max(0.008, (now - last) / 1000));
    last = now;
    const t = (now - t0) / 1000;
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = "rgba(0,0,0,0.07)";
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = "lighter";
    for (const p of dots) {
      let x;
      let y;
      let breathe;
      let scale = 1;
      if (mode === "gather") {
        const n = curl(p.x, p.y, t, p.seed);
        p.x += (p.dir.x * p.speed + n.x) * dt;
        p.y += (p.dir.y * p.speed + n.y) * dt;
        wrap(p, w, h);
        x = p.x;
        y = p.y;
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

  function start(gatherSec) {
    canvas.hidden = false;
    const { w, h } = size();
    makeDots(w, h);
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