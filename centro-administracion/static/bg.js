// Fondo animado con Three.js: campo de partículas ondulante + malla poligonal. Se pausa si la pestaña no se ve.
import * as THREE from "./vendor/three.module.min.js";

export function startBackground(canvas) {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: "low-power" });
  } catch (e) {
    canvas.style.display = "none";
    return { setMode() {} };
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x07090a, 0.045);
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  camera.position.set(0, 3.2, 9);

  // rejilla de puntos que ondula
  const N = 70, SP = 0.42, count = N * N;
  const pos = new Float32Array(count * 3), base = new Float32Array(count * 2);
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
    const k = i * N + j;
    base[k * 2] = (i - N / 2) * SP; base[k * 2 + 1] = (j - N / 2) * SP;
    pos[k * 3] = base[k * 2]; pos[k * 3 + 2] = base[k * 2 + 1];
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({ color: 0x8bd800, size: 0.055, transparent: true, opacity: 0.85, sizeAttenuation: true, depthWrite: false });
  const pts = new THREE.Points(geo, mat);
  pts.position.y = -2.2;
  scene.add(pts);

  // figura central (se muestra en el login)
  const ico = new THREE.Mesh(new THREE.IcosahedronGeometry(2.1, 1),
    new THREE.MeshBasicMaterial({ color: 0x8bd800, wireframe: true, transparent: true, opacity: 0.35 }));
  ico.position.set(0, 2.6, -3);
  scene.add(ico);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(3.4, 0.015, 8, 120),
    new THREE.MeshBasicMaterial({ color: 0xc6ff4a, transparent: true, opacity: 0.4 }));
  ring.position.copy(ico.position); ring.rotation.x = 1.2;
  scene.add(ring);

  let mx = 0, my = 0, mode = "login", t = 0, raf = 0, k = 1;
  addEventListener("pointermove", (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; });
  function resize() {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  addEventListener("resize", resize); resize();

  function frame() {
    raf = 0;
    if (document.hidden) return;
    t += 0.012;
    const a = geo.attributes.position.array;
    for (let i = 0; i < count; i++) {
      const x = base[i * 2], z = base[i * 2 + 1];
      a[i * 3 + 1] = Math.sin(x * 0.6 + t * 1.4) * 0.45 + Math.cos(z * 0.5 + t) * 0.45;
    }
    geo.attributes.position.needsUpdate = true;
    ico.rotation.x += 0.0025; ico.rotation.y += 0.004; ring.rotation.z += 0.003;
    // transición suave entre modos (login ⇄ app)
    const target = mode === "login" ? 1 : 0;
    k += (target - k) * 0.04;
    ico.scale.setScalar(0.001 + k); ico.material.opacity = 0.35 * k; ring.material.opacity = 0.4 * k;
    mat.opacity = 0.35 + 0.5 * k;
    camera.position.x += (mx * 2.4 - camera.position.x) * 0.04;
    camera.position.y += (3.2 - my * 1.4 - camera.position.y) * 0.04;
    camera.lookAt(0, 0.6, 0);
    renderer.render(scene, camera);
    if (!reduce) raf = requestAnimationFrame(frame);
  }
  const kick = () => { if (!raf) raf = requestAnimationFrame(frame); };
  document.addEventListener("visibilitychange", kick);
  kick();
  return { setMode(m) { mode = m; if (reduce) { k = m === "login" ? 1 : 0; kick(); } } };
}
