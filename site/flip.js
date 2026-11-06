/* Flip, the Flipside bot, live on the page. Same model as the film: an ivory puck with a black glass face on
 * the front, an amber back with the seal, and a dark seam where the two sides meet.
 * Flip.mount(canvas) returns an actor; actor.set({...}) changes its mood, and a render loop eases toward it.
 * Three.js r160 (MIT, site/vendor). No network, no randomness: blinks follow a fixed schedule. */
(function () {
  const T = window.THREE;
  if (!T) return;

  function rrShape(w, h, r) {
    const s = new T.Shape(), x = -w / 2, y = -h / 2;
    s.moveTo(x + r, y);
    s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
    s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
    s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
    return s;
  }

  // A soft studio: one big top softbox, a warm key strip and a cool rim strip.
  function studioEnv(renderer) {
    const scene = new T.Scene();
    const room = new T.Mesh(new T.BoxGeometry(20, 12, 20), new T.MeshBasicMaterial({ color: 0x4a4744, side: T.BackSide }));
    room.position.y = 3;
    scene.add(room);
    const strip = (w, h, c, k, pos, rot) => {
      const m = new T.Mesh(new T.PlaneGeometry(w, h), new T.MeshBasicMaterial({ color: new T.Color(c).multiplyScalar(k), side: T.DoubleSide }));
      m.position.set(...pos); m.rotation.set(...rot); scene.add(m);
    };
    strip(10, 6, 0xffffff, 3.2, [0, 8.9, 0], [Math.PI / 2, 0, 0]);
    strip(2.2, 8, 0xfff1dc, 5.0, [-9.8, 3, 2], [0, Math.PI / 2, 0]);
    strip(1.4, 8, 0xdfe8ff, 4.0, [9.8, 3, -3], [0, -Math.PI / 2, 0]);
    strip(8, 1.2, 0xffffff, 2.2, [0, 2, -9.8], [0, 0, 0]);
    strip(1.2, 6, 0xffffff, 2.4, [5.5, 5.5, 9.8], [0, Math.PI, -0.6]);
    strip(0.4, 6, 0xffffff, 1.8, [3.6, 5.5, 9.8], [0, Math.PI, -0.6]);
    strip(14, 4, 0xece6dc, 0.9, [0, -2.9, 0], [-Math.PI / 2, 0, 0]);
    const pm = new T.PMREMGenerator(renderer);
    const tex = pm.fromScene(scene, 0.035).texture;
    pm.dispose();
    return tex;
  }

  function radial(stops, size) {
    const c = document.createElement("canvas"); c.width = c.height = size;
    const g = c.getContext("2d"), h = size / 2, r = g.createRadialGradient(h, h, 0, h, h, h);
    stops.forEach(([o, col]) => r.addColorStop(o, col));
    g.fillStyle = r; g.fillRect(0, 0, size, size);
    const t = new T.CanvasTexture(c); t.colorSpace = T.SRGBColorSpace; return t;
  }

  function build(renderer) {
    const scene = new T.Scene();
    scene.environment = studioEnv(renderer);
    const key = new T.DirectionalLight(0xfff0dd, 1.4); key.position.set(-4, 5, 6); scene.add(key);
    const rim = new T.DirectionalLight(0xdbe6ff, 1.1); rim.position.set(5, 2, -5); scene.add(rim);

    // Body: two extruded halves whose bevels meet at z = 0: the flip line.
    const D = 0.26, B = 0.17;
    const halfGeo = new T.ExtrudeGeometry(rrShape(1.84, 1.84, 0.56), { depth: D, bevelEnabled: true, bevelThickness: B, bevelSize: B, bevelSegments: 10, curveSegments: 28 });
    halfGeo.translate(0, 0, B + 0.03);
    const ivory = new T.MeshPhysicalMaterial({ color: 0xfdfbf6, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.14, sheen: 0.4, sheenColor: new T.Color(0xffffff), envMapIntensity: 1.05 });
    const amber = new T.MeshPhysicalMaterial({ color: 0xf7b445, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.14, envMapIntensity: 1.05 });
    const bot = new T.Group(), flip = new T.Group(); bot.add(flip);
    flip.add(new T.Mesh(halfGeo, ivory));
    const back = new T.Mesh(halfGeo, amber); back.rotation.y = Math.PI; flip.add(back);
    const FZ = D + 2 * B + 0.03;
    const band = new T.Mesh(new T.ExtrudeGeometry(rrShape(2.12, 2.12, 0.71), { depth: 0.07, bevelEnabled: false, curveSegments: 28 }),
      new T.MeshPhysicalMaterial({ color: 0x2a2622, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.2 }));
    band.position.z = -0.035; flip.add(band);

    // Front: black glass face, two warm eyes that can open, squint, or turn into happy arcs.
    const glass = new T.MeshPhysicalMaterial({ color: 0x0b0c0f, roughness: 0.08, clearcoat: 1, clearcoatRoughness: 0.03, envMapIntensity: 1.2 });
    const face = new T.Mesh(new T.ShapeGeometry(rrShape(1.5, 1.22, 0.42), 24), glass);
    face.position.z = FZ + 0.004; flip.add(face);
    const eyeMat = new T.MeshBasicMaterial({ color: new T.Color(0xfff4e2).multiplyScalar(1.5), toneMapped: false, transparent: true, depthWrite: false });
    const glowTex = radial([[0, "rgba(255,255,255,0.5)"], [0.4, "rgba(255,255,255,0.14)"], [1, "rgba(255,255,255,0)"]], 128);
    const eyeGeo = new T.ShapeGeometry(rrShape(0.2, 0.36, 0.1), 16);
    const arcGeo = new T.TorusGeometry(0.12, 0.042, 10, 32, Math.PI);
    const eyes = [-1, 1].map((sx) => {
      const g = new T.Group(); g.position.set(sx * 0.29, 0.02, FZ + 0.01);
      const open = new T.Mesh(eyeGeo, eyeMat.clone()); g.add(open);
      const happy = new T.Mesh(arcGeo, eyeMat.clone()); happy.position.y = -0.04; g.add(happy);
      const glow = new T.Mesh(new T.PlaneGeometry(0.7, 0.9), new T.MeshBasicMaterial({ map: glowTex, color: 0xffe2b0, transparent: true, opacity: 0.55, blending: T.AdditiveBlending, depthWrite: false }));
      glow.position.z = -0.004; g.add(glow);
      flip.add(g); return { g, open, happy, glow };
    });

    // Back: the seal in ink, a ring and a check.
    const ink = new T.MeshPhysicalMaterial({ color: 0x17181b, roughness: 0.28, clearcoat: 1, clearcoatRoughness: 0.1 });
    const seal = new T.Group(); seal.position.z = -FZ - 0.005; seal.rotation.y = Math.PI; flip.add(seal);
    seal.add(new T.Mesh(new T.TorusGeometry(0.56, 0.055, 16, 96), ink));
    const P = [new T.Vector3(-0.27, 0.01, 0), new T.Vector3(-0.07, -0.19, 0), new T.Vector3(0.29, 0.2, 0)];
    [[P[0], P[1]], [P[1], P[2]]].forEach(([a, b]) => seal.add(new T.Mesh(new T.TubeGeometry(new T.LineCurve3(a, b), 8, 0.06, 16, false), ink)));
    P.forEach((p) => { const cap = new T.Mesh(new T.SphereGeometry(0.06, 20, 14), ink); cap.position.copy(p); seal.add(cap); });
    scene.add(bot);

    const shadow = new T.Mesh(new T.PlaneGeometry(3.2, 1.1), new T.MeshBasicMaterial({
      map: radial([[0, "rgba(40,32,24,0.55)"], [0.45, "rgba(40,32,24,0.22)"], [1, "rgba(40,32,24,0)"]], 256), transparent: true, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2 + 0.55; scene.add(shadow);
    return { scene, bot, flip, eyes, shadow };
  }

  // Moods map to eye shapes. "shake" is an impulse, not a mood.
  const MOODS = { neutral: [0, 0], happy: [1, 0], squint: [0, 1], wary: [0, 0.45] };
  const BLINKS = [1.9, 5.3, 5.62, 9.1, 12.8, 15.4, 19.7]; // seconds within a 21 s cycle; the double blink reads as alive
  const ease = (cur, target, rate, dt) => cur + (target - cur) * (1 - Math.exp(-rate * dt));

  // Flip's farthest reach is about 1.65 units from its centre: the top corner during a hop and tilt,
  // and the floor shadow. Its body is 2.12 units, so a fit above this clips at the canvas edge.
  // A page that wants Flip bigger gives the canvas room around its box instead.
  const MAX_FIT = 0.64;

  function mount(canvas, opts = {}) {
    const fit = Math.min(MAX_FIT, opts.fit || 0.62);
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let renderer;
    try {
      const mobile = matchMedia("(max-width: 720px)").matches;
      renderer = new T.WebGLRenderer({
        canvas, antialias: !mobile, alpha: true, powerPreference: mobile ? "low-power" : "high-performance"
      });
    } catch (e) {
      canvas.dataset.fallback = "1"; // the page shows its static image instead
      return null;
    }
    renderer.setClearColor(0x000000, 0);
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.22;
    renderer.outputColorSpace = T.SRGBColorSpace;
    const m = build(renderer);
    const camera = new T.PerspectiveCamera(26, 1, 0.1, 100);
    camera.position.set(0, 0, 11); camera.lookAt(0, 0, 0);
    const VIS = 2 * 11 * Math.tan((13 * Math.PI) / 180); // visible height at z = 0

    let w = 1, h = 1, scale = 1;
    function resize() {
      const r = canvas.getBoundingClientRect();
      w = Math.max(1, r.width); h = Math.max(1, r.height);
      renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
      renderer.setSize(w, h, false);
      camera.aspect = w / h; camera.updateProjectionMatrix();
      scale = (fit * VIS * Math.min(1, w / h)) / 2.12;
      dirty = true;
    }

    // Targets set from outside, and the eased state the renderer draws.
    const goal = { mood: "neutral", side: 0, lookX: 0, lookY: 0, lift: 0 };
    const now = { happy: 0, squint: 0, flip: 0, lookX: 0, lookY: 0, lift: 0 };
    let flipTarget = 0, shakeAt = -9, hopAt = -9, t = 0, last = 0, running = false, visible = true, dirty = true;

    function set(p) {
      if (p.mood) goal.mood = p.mood;
      if (p.look) { goal.lookX = p.look[0]; goal.lookY = p.look[1]; }
      if (p.lift != null) goal.lift = p.lift;
      if (p.side != null && p.side !== goal.side) { goal.side = p.side; flipTarget += Math.PI; } // always spins the same way
      if (p.shake) shakeAt = t;
      if (p.hop) hopAt = t;
      if (reduce) { now.flip = flipTarget; frame(0); }
      dirty = true;
      wake();
    }

    function frame(dt) {
      t += dt;
      const [hp, sq] = MOODS[goal.mood] || MOODS.neutral;
      now.happy = ease(now.happy, hp, 12, dt);
      now.squint = ease(now.squint, sq, 12, dt);
      now.lookX = ease(now.lookX, goal.lookX, 9, dt);
      now.lookY = ease(now.lookY, goal.lookY, 9, dt);
      now.lift = ease(now.lift, goal.lift, 6, dt);
      // The flip overshoots a little, like the film's back.out ease: a damped spring.
      const k = 90, c = 13;
      now.vflip = (now.vflip || 0) + ((flipTarget - now.flip) * k - (now.vflip || 0) * c) * dt;
      now.flip += now.vflip * dt;
      if (reduce) now.flip = flipTarget;

      const cyc = t % 21;
      let blink = 0;
      for (const b of BLINKS) { const u = (cyc - b) / 0.16; if (u >= 0 && u <= 1) blink = Math.sin(u * Math.PI); }
      const su = t - shakeAt, shake = su >= 0 && su < 0.6 ? 0.32 * Math.sin(su * 30) * (1 - su / 0.6) : 0;
      const hu = t - hopAt, hop = hu >= 0 && hu < 0.5 ? Math.sin((hu / 0.5) * Math.PI) * 0.22 : 0;
      const bob = reduce ? 0 : 0.035 * Math.sin(t * 2.3);
      const y = (now.lift + bob + hop) * scale;

      m.bot.position.set(0, y, 0);
      m.bot.scale.setScalar(scale);
      m.bot.rotation.set(-now.lookY * 0.12, shake + now.lookX * 0.22 + (reduce ? 0 : 0.06 * Math.sin(t * 0.9)), reduce ? 0 : 0.035 * Math.sin(t * 1.4 + 1));
      m.flip.rotation.y = now.flip;
      m.eyes.forEach((e, i) => {
        e.g.position.x = (i ? 1 : -1) * 0.29 + now.lookX * 0.16;
        e.g.position.y = 0.02 + now.lookY * 0.12;
        const sy = Math.max(0.06, (1 - blink) * (1 - now.happy) * (1 - 0.55 * now.squint));
        e.open.scale.set(1, sy, 1);
        e.open.material.opacity = 1 - now.happy;
        e.happy.material.opacity = now.happy;
        e.happy.scale.setScalar(0.6 + 0.4 * now.happy);
        e.glow.scale.copy(e.open.scale);
      });
      const floor = -1.32 * scale;
      const air = Math.max(0, y) / scale;
      m.shadow.position.set(0, floor, 0);
      m.shadow.scale.setScalar(scale * 0.8 * (1 + air * 0.18));
      m.shadow.material.opacity = 0.6 * Math.max(0.15, 1 - air * 0.35);
      renderer.render(m.scene, camera);
    }

    function loop(ms) {
      if (!running) return;
      const dt = Math.min(0.05, last ? (ms - last) / 1000 : 0);
      last = ms;
      frame(dt);
      const settled = Math.abs(flipTarget - now.flip) < 1e-3 && Math.abs(now.vflip || 0) < 1e-3;
      if (reduce && settled && !dirty) { running = false; return; }
      dirty = false;
      requestAnimationFrame(loop);
    }
    function wake() {
      if (running || !visible || document.hidden) return;
      running = true; last = 0; requestAnimationFrame(loop);
    }
    function sleep() { running = false; }

    new ResizeObserver(resize).observe(canvas);
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; visible ? wake() : sleep(); }).observe(canvas);
    document.addEventListener("visibilitychange", () => (document.hidden ? sleep() : wake()));
    resize();
    frame(0);
    wake();
    return { set, get side() { return goal.side; } };
  }

  window.Flip = { mount };
})();
