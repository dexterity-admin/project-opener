/* ==========================================================================
   Project Opener 3 - landing page script
   --------------------------------------------------------------------------
   Two independent parts:
     1. HERO   - Three.js scene (floating project cards orbiting a glowing
                 core, particles, grid floor). Skipped when WebGL is missing
                 or the visitor prefers reduced motion; the CSS gradient hero
                 shows instead.
     2. SCROLL - GSAP + ScrollTrigger reveals for the sections below, hover
                 tilt on feature cards, pulse on the Team Hub diagram.

   Tunables live in the CONFIG object just below.
   ========================================================================== */

import * as THREE from "three";

const CONFIG = {
  // Colours (keep in sync with styles.css :root)
  accentA: 0x2f5bff,
  accentB: 0x19c8ff,
  bg: 0x070b18,
  fogColor: 0x0a1026,

  // Scene
  maxPixelRatio: 1.5,          // cap DPR for laptop GPUs
  cardCount: 14,               // number of floating project cards
  particleCount: 900,
  orbitRadius: [4.2, 7.5],     // min / max distance of cards from the core
  orbitSpeed: [0.05, 0.14],    // radians per second
  burstScale: 2.2,             // how far cards fly out on load (x radius)
  burstDuration: 1.6,          // seconds for the burst-and-settle
  parallax: 0.9,               // camera offset for mouse-move (world units)
  cameraZ: 15,

  // Reveal animations
  revealDistance: 40,          // px slide for scroll reveals
};

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const isTouch = window.matchMedia("(hover: none)").matches;

/* ==========================================================================
   1. HERO SCENE
   ========================================================================== */

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch { return false; }
}

/** Rounded-rectangle Shape used for the card fill and outline. */
function roundedRectShape(w, h, r) {
  const s = new THREE.Shape();
  const x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

/** Soft radial-gradient texture, used for the core glow and particles. */
function glowTexture(size, inner, outer) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const grd = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grd.addColorStop(0, inner);
  grd.addColorStop(0.35, inner.replace(/[\d.]+\)$/, "0.45)"));
  grd.addColorStop(1, outer);
  g.fillStyle = grd;
  g.fillRect(0, 0, size, size);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function buildCard(index) {
  const w = 1.6 + Math.random() * 0.6;
  const h = w * 0.66;
  const group = new THREE.Group();

  const shape = roundedRectShape(w, h, 0.18);
  const geo = new THREE.ShapeGeometry(shape, 6);

  // translucent glass fill
  const fill = new THREE.Mesh(
    geo,
    new THREE.MeshBasicMaterial({
      color: index % 3 === 0 ? CONFIG.accentB : CONFIG.accentA,
      transparent: true,
      opacity: 0.10,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
  );
  group.add(fill);

  // emissive edge (drawn as a line loop over the shape outline)
  const pts = shape.getPoints(10);
  const edgeGeo = new THREE.BufferGeometry().setFromPoints(pts);
  const edge = new THREE.LineLoop(
    edgeGeo,
    new THREE.LineBasicMaterial({
      color: index % 3 === 0 ? CONFIG.accentB : 0x7aa2ff,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
    })
  );
  group.add(edge);

  // "content" lines - a small title bar and two text rows
  const lineMat = new THREE.MeshBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0.35,
    blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
  });
  const rows = [
    [w * 0.5, 0.09, h * 0.26],
    [w * 0.72, 0.045, h * 0.02],
    [w * 0.58, 0.045, -h * 0.14],
  ];
  rows.forEach(([rw, rh, ry]) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(rw, rh), lineMat);
    m.position.set(-w / 2 + 0.18 + rw / 2, ry, 0.001);
    group.add(m);
  });

  // a tiny folder "tab" dot top-left
  const dot = new THREE.Mesh(
    new THREE.CircleGeometry(0.06, 12),
    new THREE.MeshBasicMaterial({ color: CONFIG.accentB, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending })
  );
  dot.position.set(w / 2 - 0.2, h / 2 - 0.2, 0.002);
  group.add(dot);

  // orbit parameters
  const [rMin, rMax] = CONFIG.orbitRadius;
  const [sMin, sMax] = CONFIG.orbitSpeed;
  group.userData = {
    radius: rMin + Math.random() * (rMax - rMin),
    speed: (sMin + Math.random() * (sMax - sMin)) * (Math.random() < 0.5 ? 1 : -1),
    phase: Math.random() * Math.PI * 2,
    tilt: (Math.random() - 0.5) * 0.9,          // orbit-plane inclination
    yOffset: (Math.random() - 0.5) * 3.2,
    wobble: Math.random() * Math.PI * 2,
    scale: 1,                                    // animated during the burst
    spread: 0.001,                               // 0 = at core, 1 = on orbit
  };
  return group;
}

function initHero() {
  const mount = document.getElementById("hero-scene");
  const hero = document.querySelector(".hero");
  if (!mount) return;

  if (reduceMotion || !webglAvailable()) {
    hero.classList.add("hero--fallback");
    return;
  }

  /* --- renderer ------------------------------------------------------- */
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, CONFIG.maxPixelRatio));
  renderer.setSize(mount.clientWidth, mount.clientHeight);
  renderer.setClearColor(0x000000, 0);
  mount.appendChild(renderer.domElement);

  /* --- scene / camera ------------------------------------------------- */
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(CONFIG.fogColor, 10, 34);

  const camera = new THREE.PerspectiveCamera(50, mount.clientWidth / mount.clientHeight, 0.1, 100);
  camera.position.set(0, 1.2, CONFIG.cameraZ);
  const camBase = camera.position.clone();

  /* --- grid floor (fades into fog) ------------------------------------ */
  const grid = new THREE.GridHelper(80, 60, 0x2f5bff, 0x1b2a5c);
  grid.material.transparent = true;
  grid.material.opacity = 0.22;
  grid.position.y = -4.5;
  scene.add(grid);

  /* --- particle field ------------------------------------------------- */
  const pCount = CONFIG.particleCount;
  const pPos = new Float32Array(pCount * 3);
  const pSize = new Float32Array(pCount);
  for (let i = 0; i < pCount; i++) {
    pPos[i * 3 + 0] = (Math.random() - 0.5) * 50;
    pPos[i * 3 + 1] = (Math.random() - 0.5) * 24;
    pPos[i * 3 + 2] = (Math.random() - 0.5) * 40 - 5;
    pSize[i] = 0.5 + Math.random();
  }
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
  const particles = new THREE.Points(
    pGeo,
    new THREE.PointsMaterial({
      map: glowTexture(64, "rgba(140,200,255,1)", "rgba(140,200,255,0)"),
      size: 0.22, sizeAttenuation: true, transparent: true, opacity: 0.7,
      depthWrite: false, blending: THREE.AdditiveBlending, color: 0x9fd3ff,
    })
  );
  scene.add(particles);

  /* --- glowing core ---------------------------------------------------- */
  const core = new THREE.Group();
  core.position.y = -0.6;      // sits just below the headline on most viewports
  scene.add(core);

  const glow = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTexture(256, "rgba(47,120,255,1)", "rgba(25,200,255,0)"),
    transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  glow.scale.set(9, 9, 1);
  core.add(glow);

  const glowInner = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTexture(128, "rgba(190,240,255,1)", "rgba(25,200,255,0)"),
    transparent: true, opacity: 0.8, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  glowInner.scale.set(3.4, 3.4, 1);
  core.add(glowInner);

  // app icon as a sprite in the centre (the folder/arrow motif)
  const loader = new THREE.TextureLoader();
  loader.load("assets/icon-256.png", (tex) => {
    tex.colorSpace = THREE.SRGBColorSpace;
    // kept semi-transparent so the headline overlay stays readable on top
    const icon = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0.6, depthWrite: false }));
    icon.scale.set(2.3, 2.3, 1);
    icon.position.z = 0.1;
    core.add(icon);
    core.userData.icon = icon;
  });

  // two thin rings around the core
  const ringMat = new THREE.MeshBasicMaterial({
    color: CONFIG.accentB, transparent: true, opacity: 0.35, side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending, depthWrite: false,
  });
  const ring1 = new THREE.Mesh(new THREE.RingGeometry(2.6, 2.64, 96), ringMat);
  const ring2 = new THREE.Mesh(new THREE.RingGeometry(3.4, 3.43, 96), ringMat.clone());
  ring2.material.opacity = 0.18;
  ring1.rotation.x = Math.PI / 2.4;
  ring2.rotation.x = -Math.PI / 2.8;
  ring2.rotation.z = 0.6;
  core.add(ring1, ring2);

  /* --- floating cards -------------------------------------------------- */
  const cards = [];
  for (let i = 0; i < CONFIG.cardCount; i++) {
    const c = buildCard(i);
    scene.add(c);
    cards.push(c);
  }

  /* --- launch burst: cards fly out from the core, then settle --------- */
  const burstStart = performance.now();
  let burstDone = false;
  // easeOutBack overshoots to ~1.1 before settling at 1; burstScale
  // amplifies that overshoot so the cards visibly fly past their orbit.
  function easeOutBack(x) { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); }
  function updateBurst(now) {
    if (burstDone) return;
    const t = Math.min(1, (now - burstStart) / (CONFIG.burstDuration * 1000));
    cards.forEach((c, i) => {
      const u = c.userData;
      const delay = (i / cards.length) * 0.25;             // slight stagger per card
      const tt = Math.max(0, Math.min(1, (t - delay) / (1 - delay)));
      u.spread = tt === 0 ? 0.001 : Math.max(0.001, 1 + (easeOutBack(tt) - 1) * CONFIG.burstScale);
      u.scale = 0.3 + 0.7 * tt;
    });
    if (t >= 1) burstDone = true;
  }

  /* --- mouse parallax --------------------------------------------------- */
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  function onPointer(e) {
    const r = mount.getBoundingClientRect();
    pointer.tx = ((e.clientX - r.left) / r.width - 0.5) * 2;
    pointer.ty = ((e.clientY - r.top) / r.height - 0.5) * 2;
  }
  if (!isTouch) window.addEventListener("pointermove", onPointer, { passive: true });

  /* --- render loop ------------------------------------------------------ */
  let running = true;        // false when tab hidden or hero scrolled away
  let rafId = 0;
  const clock = new THREE.Clock();

  function frame() {
    if (!running) return;
    rafId = requestAnimationFrame(frame);
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;

    updateBurst(performance.now());

    // cards orbit
    cards.forEach((c) => {
      const u = c.userData;
      u.phase += u.speed * dt;
      const r = u.radius * u.spread;
      const x = Math.cos(u.phase) * r;
      const z = Math.sin(u.phase) * r;
      const y = u.yOffset * u.spread + Math.sin(t * 0.8 + u.wobble) * 0.25 + z * Math.sin(u.tilt) * 0.3;
      c.position.set(x, y, z);
      // face roughly toward the camera with a gentle wobble
      c.lookAt(camera.position);
      c.rotation.z += Math.sin(t * 0.6 + u.wobble) * 0.08;
      c.rotation.y += Math.sin(t * 0.5 + u.wobble) * 0.18;
      c.scale.setScalar(u.scale);
      // cards behind the core fade a little (depth cue)
      const fade = THREE.MathUtils.clamp((z + 8) / 16, 0.25, 1);
      c.children[0].material.opacity = 0.10 * fade;
      c.children[1].material.opacity = 0.85 * fade;
    });

    // core breathing + rings
    const breathe = 1 + Math.sin(t * 1.4) * 0.05;
    glow.scale.set(9 * breathe, 9 * breathe, 1);
    glowInner.scale.set(3.4 * (2 - breathe), 3.4 * (2 - breathe), 1);
    ring1.rotation.z += dt * 0.25;
    ring2.rotation.z -= dt * 0.18;
    if (core.userData.icon) core.userData.icon.position.y = Math.sin(t * 1.1) * 0.12;

    // particle drift
    particles.rotation.y += dt * 0.015;
    particles.position.y = Math.sin(t * 0.3) * 0.3;

    // camera: subtle drift + mouse parallax
    pointer.x += (pointer.tx - pointer.x) * 0.05;
    pointer.y += (pointer.ty - pointer.y) * 0.05;
    camera.position.x = camBase.x + Math.sin(t * 0.21) * 0.6 + pointer.x * CONFIG.parallax;
    camera.position.y = camBase.y + Math.cos(t * 0.17) * 0.35 - pointer.y * CONFIG.parallax * 0.6;
    camera.lookAt(0, 0.2, 0);

    renderer.render(scene, camera);
  }

  function start() { if (!running) { running = true; clock.start(); frame(); } }
  function stop() { running = false; cancelAnimationFrame(rafId); }

  // pause when the tab is hidden
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : heroVisible && start()));
  // pause when the hero is scrolled out of view
  let heroVisible = true;
  new IntersectionObserver(([entry]) => {
    heroVisible = entry.isIntersecting;
    if (heroVisible && !document.hidden) start(); else stop();
  }, { threshold: 0.02 }).observe(mount);

  // resize - observe the mount itself so container/pane changes are caught
  // even when no window "resize" event fires. Debounced to avoid thrash.
  let resizeT = 0;
  function fitToMount() {
    const w = mount.clientWidth, h = mount.clientHeight;
    if (w < 2 || h < 2) return;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, CONFIG.maxPixelRatio));
    renderer.setSize(w, h);
  }
  const onResize = () => { clearTimeout(resizeT); resizeT = setTimeout(fitToMount, 120); };
  if ("ResizeObserver" in window) new ResizeObserver(onResize).observe(mount);
  else window.addEventListener("resize", onResize);

  frame();
}

/* ==========================================================================
   2. SCROLL ANIMATIONS (GSAP + ScrollTrigger)
   ========================================================================== */

function initScroll() {
  const gsap = window.gsap;
  if (!gsap || !window.ScrollTrigger || reduceMotion) return;
  gsap.registerPlugin(window.ScrollTrigger);

  const d = CONFIG.revealDistance;

  /* hero overlay entrance */
  gsap.from(".hero__content > *", {
    opacity: 0, y: 24, duration: 0.9, stagger: 0.09, ease: "power3.out", delay: 0.25,
  });
  gsap.from(".nav", { opacity: 0, y: -12, duration: 0.8, ease: "power2.out", delay: 0.1 });

  /* section headings */
  document.querySelectorAll(".section").forEach((sec) => {
    const head = sec.querySelectorAll(".eyebrow, .section__title, .section__lead");
    gsap.from(head, {
      opacity: 0, y: d, duration: 0.8, stagger: 0.1, ease: "power3.out",
      scrollTrigger: { trigger: sec, start: "top 78%", once: true },
    });
  });

  /* feature cards: staggered scale + lift */
  gsap.from(".feature", {
    opacity: 0, y: d, scale: 0.94, duration: 0.7, stagger: 0.08, ease: "power3.out",
    scrollTrigger: { trigger: ".features", start: "top 80%", once: true },
  });

  /* team hub diagram */
  gsap.from(".hub__svg", {
    opacity: 0, scale: 0.92, duration: 1, ease: "power3.out",
    scrollTrigger: { trigger: ".hub", start: "top 75%", once: true },
  });
  gsap.from(".hub__pc", {
    opacity: 0, y: 20, duration: 0.7, stagger: 0.15, ease: "power3.out", delay: 0.2,
    scrollTrigger: { trigger: ".hub", start: "top 75%", once: true },
  });
  gsap.from(".hub__chip", {
    opacity: 0, scale: 0.6, transformOrigin: "50% 50%", duration: 0.5, stagger: 0.1, ease: "back.out(2)", delay: 0.5,
    scrollTrigger: { trigger: ".hub", start: "top 75%", once: true },
  });
  gsap.from(".hub__caption", {
    opacity: 0, y: 16, duration: 0.8, ease: "power3.out", delay: 0.6,
    scrollTrigger: { trigger: ".hub", start: "top 75%", once: true },
  });
  // continuous pulse through the file chips while the diagram is on screen
  const pulse = gsap.timeline({ repeat: -1, repeatDelay: 1.2, paused: true, delay: 1.5 });
  pulse.to(".hub__chip rect", {
    stroke: "#19C8FF", fill: "rgba(25,200,255,.18)", duration: 0.35, stagger: { each: 0.25, yoyo: true, repeat: 1 },
  });
  window.ScrollTrigger.create({
    trigger: ".hub", start: "top 80%", end: "bottom 20%",
    onEnter: () => pulse.play(), onLeave: () => pulse.pause(),
    onEnterBack: () => pulse.play(), onLeaveBack: () => pulse.pause(),
  });

  /* roles */
  gsap.from(".role", {
    opacity: 0, x: -d, duration: 0.8, stagger: 0.12, ease: "power3.out",
    scrollTrigger: { trigger: ".roles", start: "top 80%", once: true },
  });

  /* spec strip */
  gsap.from(".specs", {
    opacity: 0, y: d, duration: 0.8, ease: "power3.out",
    scrollTrigger: { trigger: ".specs", start: "top 85%", once: true },
  });
  gsap.from(".specs li", {
    opacity: 0, x: -10, duration: 0.5, stagger: 0.07, ease: "power2.out", delay: 0.2,
    scrollTrigger: { trigger: ".specs", start: "top 85%", once: true },
  });

  /* timeline */
  gsap.from(".tl", {
    opacity: 0, y: d, duration: 0.8, stagger: 0.18, ease: "power3.out",
    scrollTrigger: { trigger: ".timeline", start: "top 80%", once: true },
  });

  /* footer */
  gsap.from(".footer__inner", {
    opacity: 0, y: 16, duration: 0.7, ease: "power2.out",
    scrollTrigger: { trigger: ".footer", start: "top 95%", once: true },
  });
}

/* ==========================================================================
   3. HOVER TILT on feature cards
   ========================================================================== */

function initTilt() {
  const gsap = window.gsap;
  if (!gsap || reduceMotion || isTouch) return;
  document.querySelectorAll("[data-tilt]").forEach((el) => {
    el.style.transformPerspective = "900px";
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      gsap.to(el, { rotateY: px * 10, rotateX: -py * 10, scale: 1.02, duration: 0.4, ease: "power2.out", transformPerspective: 900 });
    });
    el.addEventListener("pointerleave", () => {
      gsap.to(el, { rotateY: 0, rotateX: 0, scale: 1, duration: 0.6, ease: "power3.out" });
    });
  });
}

/* ==========================================================================
   boot
   ========================================================================== */

function boot() {
  initHero();
  initScroll();
  initTilt();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
