import { startBackground } from "./bg.js";
import { viewSocios as renderSocios } from "./socios.js?v=20261023-socios-r3";

const BASE = "/administracion";
const NF = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always" });   // «always»: 1.234,56 también con 4 cifras
const $ = (s, r = document) => r.querySelector(s);
const root = $("#root");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { csrf: "", user: "", mods: {}, timers: [] };
let bg = { setMode() {} };
try { bg = startBackground($("#bg")); } catch (e) { /* sin WebGL */ }

const ICONS = {
  home: '<path d="M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  cal: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18"/>',
  doc: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
  cash: '<rect x="2" y="6" width="20" height="12" rx="3"/><circle cx="12" cy="12" r="2.6"/><path d="M6 9v.01M18 15v.01"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  out: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 8l-4 4 4 4M6 12h10"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5M8 7h7M8 11h7"/>',
  plug: '<path d="M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4"/>',
  tablet: '<rect x="5" y="2" width="14" height="20" rx="3"/><path d="M11 18h2"/>',
  screen: '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  bot: '<rect x="4" y="8" width="16" height="12" rx="4"/><path d="M12 4v4M9 13v.01M15 13v.01"/>',
  dl: '<path d="M12 3v12m0 0-4-4m4 4 4-4M4 21h16"/>',
  users: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20a6 6 0 0 1 12 0M16 4.8a3.2 3.2 0 0 1 0 6.4M18 20a6 6 0 0 0-2.6-5"/>',
};
const ico = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]}</svg>`;

const ROUTES = [
  { id: "inicio", s: "Inicio", title: "Inicio", icon: "home" },
  { id: "socios", s: "Socios", title: "Buscar socios", icon: "search" },
  { id: "reservas", s: "Reservas", title: "Reservas", icon: "cal", frame: "/admin/" },
  { id: "altas", s: "Altas", title: "Altas y contratos", icon: "doc", frame: "/alta/admin/", login: "altas" },
  { id: "caja", s: "Caja", title: "Apuntes de caja", icon: "cash", frame: "/alta/caja/", login: "caja" },
  { id: "clientes", s: "Clientes", title: "Clientes (cuotas)", icon: "users", frame: "/alta/caja/?solo=1#cuotas", login: "caja" },
  { id: "diario", s: "Diario", title: "Histórico de caja", icon: "book" },
  { id: "cuentas", title: "Informes (PC)", icon: "chart", hidden: true },
  { id: "innux", s: "Innux", title: "Conexión Innux", icon: "plug" },
  { id: "bot", s: "Bot", title: "Bot de WhatsApp", icon: "bot" },
  { id: "seguridad", s: "Seguridad", title: "Seguridad", icon: "lock" },
];

// ---------- utilidades ----------
async function api(path, opts = {}) {
  const o = { method: opts.body ? "POST" : "GET", credentials: "same-origin", headers: {} };
  if (opts.body !== undefined) { o.method = "POST"; o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opts.body); }
  if (o.method === "POST") o.headers["X-CSRF-Token"] = S.csrf;
  const rt = S.rt;
  const r = await fetch(BASE + "/api/" + path, o);
  let j = {};
  try { j = await r.json(); } catch (e) { /* vacío */ }
  if (o.method === "GET" && S.rt !== rt && path !== "me") throw new Error("Cancelada");   // el usuario ya cambió de pantalla
  if (r.status === 401 && path !== "me" && path !== "login") { showLogin(); throw new Error("Sesión caducada"); }
  if (!r.ok && !opts.soft) throw Object.assign(new Error(j.error || "Error " + r.status), { data: j });
  return j;
}
function toast(msg, bad) {
  const t = document.createElement("div");
  t.className = "toast" + (bad ? " err" : ""); t.textContent = msg;
  $("#toasts").append(t);
  if (window.gsap && !reduce) gsap.from(t, { x: 40, opacity: 0, duration: 0.4, ease: "power3.out" });
  setTimeout(() => { if (window.gsap && !reduce) gsap.to(t, { opacity: 0, y: 10, duration: 0.3, onComplete: () => t.remove() }); else t.remove(); }, 4200);
}
const fmtDate = (ts) => ts ? new Date(ts * 1000).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
const ago = (ts) => { if (!ts) return "nunca"; const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 1 ? "ahora mismo" : m < 60 ? `hace ${m} min` : m < 1440 ? `hace ${Math.round(m / 60)} h` : `hace ${Math.round(m / 1440)} d`; };
const MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
const periodLabel = (p) => { const [y, m] = p.split("-"); return `${MESES[+m]} ${y}`; };
function countUp(el, to, dec = 0, suffix = "") {
  if (reduce || !window.gsap) { el.textContent = to.toFixed(dec) + suffix; return; }
  const o = { v: 0 };
  gsap.to(o, { v: to, duration: 1.2, ease: "power2.out", onUpdate: () => { el.textContent = o.v.toFixed(dec) + suffix; } });
}
function stagger(sel, parent) {
  if (reduce || !window.gsap) return;
  gsap.from(sel, { y: 22, opacity: 0, duration: 0.6, stagger: 0.06, ease: "power3.out", clearProps: "all" });
}

const eventLabel = event => ({qa_peticion:'Consulta de pantalla',login_ok:'Inicio de sesión',login_fallido:'Acceso no completado',login_bloqueado:'Acceso bloqueado temporalmente',modulo_abierto:'Módulo abierto',diario_desbloqueado:'Histórico desbloqueado',diario_bloqueado:'Histórico bloqueado',qa_diario_sin_contrasena:'Acceso de pruebas al histórico',descarga_socios:'Listado de socios descargado',descarga_diario:'Histórico descargado',logout:'Sesión cerrada',socios_busqueda:'Búsqueda de socios',socio_consultado:'Ficha de socio consultada'}[event] || String(event).replaceAll('_',' '));

// ---------- login ----------
function showLogin(msg) {
  clearTimers(); bg.setMode("login");
  S.csrf = "";
  root.innerHTML = `<div class="login"><form class="login-card" id="lf" autocomplete="on">
    <div class="logo"><i>TF</i><b>TOP<span>FITNESS</span></b></div>
    <h1>Centro de control</h1><p class="sub">Accede a reservas, altas, caja y cuentas desde un único sitio.</p>
    <div class="field"><input id="u" name="username" autocomplete="username" placeholder=" " required autofocus><label for="u">Usuario</label></div>
    <div class="field"><input id="p" name="password" type="password" autocomplete="current-password" placeholder=" " required><label for="p">Contraseña</label></div>
    <div class="field hidden" id="cf"><input id="c" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder=" "><label for="c">Código de tu app de verificación (6 cifras)</label></div>
    <p class="err" id="le" role="alert">${esc(msg || "")}</p>
    <button class="btn block" id="lb"><span>Entrar</span></button></form></div>`;
  fetch(BASE + "/api/me", { credentials: "same-origin" }).then((r) => r.json()).then((j) => { if (j.mfa) $("#cf")?.classList.remove("hidden"); }).catch(() => {});
  if (!reduce && window.gsap) {
    gsap.from(".login-card", { y: 40, opacity: 0, scale: 0.96, duration: 0.9, ease: "power3.out" });
    gsap.from(".login-card > *", { y: 14, opacity: 0, duration: 0.5, stagger: 0.07, delay: 0.25, ease: "power2.out" });
  }
  $("#lf").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const b = $("#lb"); b.disabled = true; b.innerHTML = '<i class="spin"></i>'; $("#le").textContent = "";
    try {
      const j = await api("login", { body: { user: $("#u").value.trim(), pw: $("#p").value, code: $("#c").value }, soft: true });
      if (!j.ok) throw new Error(j.error || "No se pudo entrar");
      S.csrf = j.csrf; S.user = j.user;
      if (!reduce && window.gsap) await gsap.to(".login-card", { y: -30, opacity: 0, scale: 0.97, duration: 0.45, ease: "power2.in" });
      showApp();
    } catch (e) {
      $("#le").textContent = e.message; b.disabled = false; b.innerHTML = "<span>Entrar</span>";
      if (!reduce && window.gsap) gsap.fromTo(".login-card", { x: -10 }, { x: 0, duration: 0.6, ease: "elastic.out(1,.3)" });
    }
  });
}

// ---------- shell ----------
function clearTimers() { S.timers.forEach(clearInterval); S.timers = []; }
function showApp() {
  bg.setMode("app");
  const collapsed = localStorage.getItem("tf_side") === "1";
  root.innerHTML = `<div class="app ${collapsed ? "collapsed" : ""}" id="app">
    <aside class="side"><div class="logo"><i>TF</i><b>TOP<span>FITNESS</span></b></div>
      <nav class="nav" id="nav">${ROUTES.filter((r) => !r.hidden).map((r) => `<a href="#/${r.id}" data-r="${r.id}">${ico(r.icon)}<span><span class="lg">${r.title}</span><span class="sh">${r.s || r.title}</span></span></a>`).join("")}
        <div class="sep"></div>
        <a href="/alta/" target="_blank" rel="noopener">${ico("tablet")}<span>Tablet de altas ↗</span></a>
        <a href="/reservas/" target="_blank" rel="noopener">${ico("screen")}<span>Pantalla de reservas ↗</span></a></nav>
      <div class="foot"><div class="userchip"><em>${esc(S.user[0] || "?")}</em><span>${esc(S.user)}</span></div>
        <button class="btn ghost sm" id="out">${ico("out")}<span>Salir</span></button></div></aside>
    <section class="main"><header class="top"><button class="icon-btn" id="tg" aria-label="Menú">${ico("menu")}</button><h2 id="ttl"></h2><span class="grow"></span>
      <button class="search-chip" id="sc">${ico("search")}<span>Buscar socios</span><kbd>Ctrl K</kbd></button></header>
      <div class="view" id="view"></div></section></div>`;
  $("#tg").onclick = () => { const a = $("#app"); a.classList.toggle("collapsed"); localStorage.setItem("tf_side", a.classList.contains("collapsed") ? "1" : "0"); };
  $("#sc").onclick = () => { if (location.hash === "#/socios") $("#member-query")?.focus(); else location.hash = "#/socios"; };
  $("#out").onclick = async () => { try { const r = await api("salir", { body: {} }); S.mods = {}; location.hash = ""; showLogin(r.warning || ""); } catch (e) { toast("No se ha podido cerrar la sesión. Vuelve a intentarlo.", true); } };
  if (!reduce && window.gsap) { gsap.from(".side", { x: -40, opacity: 0, duration: 0.6, ease: "power3.out" }); gsap.from(".nav a", { x: -16, opacity: 0, duration: 0.4, stagger: 0.05, delay: 0.2 }); }
  route();
}
addEventListener("hashchange", () => { if (S.csrf) route(); });
addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && S.csrf) { e.preventDefault(); $("#sc")?.click(); } });

async function route() {
  const [id, arg, arg2] = (location.hash.replace(/^#\//, "") || "inicio").split("/");
  const r = {...(ROUTES.find((x) => x.id === id) || ROUTES[0])};
  if (r.id === "altas" && /^[a-f0-9]{32}$/.test(arg || "")) r.frame += "?contract=" + arg;
  if (r.id === "clientes" && /^[1-9][0-9]{0,19}$/.test(arg || "") && /^[1-9][0-9]{0,19}$/.test(arg2 || "")) r.frame = "/alta/caja/?solo=1&client=" + arg + "&number=" + arg2 + "#cuotas";
  clearTimers();
  document.querySelectorAll("#nav a[data-r]").forEach((a) => a.classList.toggle("on", a.dataset.r === r.id));
  $("#ttl").textContent = r.title;
  document.title = r.title + " · Top Fitness";
  const v = $("#view");
  v.classList.toggle("flush", !!r.frame);
  v.scrollTop = 0;
  if (r.frame) return mountFrame(v, r);
  const render = { socios: v => renderSocios(v, {api, esc}), inicio: viewInicio, cuentas: viewCuentas, seguridad: viewSeguridad, innux: viewInnux, bot: viewBot, diario: viewDiario }[r.id];
  const box = document.createElement("div");   // cada ruta pinta en su propio contenedor: una respuesta tardía de otra ruta no pisa la actual
  box.innerHTML = '<div class="loader" style="position:static;height:50vh"><div class="bars"><i></i><i></i><i></i><i></i></div></div>';
  v.replaceChildren(box);
  const token = (S.rt = (S.rt || 0) + 1);
  try {
    if (r.id === "diario") {
      const access = await api("diario/acceso");
      if (!access.unlocked) { viewDiarioLocked(box); return; }
      const lock = document.createElement("button");
      lock.className = "btn ghost sm"; lock.innerHTML = ico("out") + "<span>Cerrar sesión del diario</span>";
      lock.onclick = async () => { try { await api("diario/bloquear", { body: {} }); route(); } catch (e) { toast(e.message, true); } };
      if (!access.qa_bypass) box.before(lock);
      const timer = setInterval(async () => {
        try { const a = await api("diario/acceso"); if (!a.unlocked && token === S.rt) route(); } catch (e) { /* la sesión se comprueba en cada consulta */ }
      }, 15000);
      S.timers.push(timer);
    }
    await render(box, arg, arg2);
  } catch (e) { if (e.data?.diario_locked && token === S.rt) { viewDiarioLocked(box); return; } if (e.message !== "Sesión caducada" && token === S.rt) box.innerHTML = `<div class="card"><h3>Error</h3>${esc(e.message)}</div>`; }
}

// ---------- módulos en iframe (se mantienen vivos al cambiar de pestaña) ----------
async function mountFrame(v, r) {
  const keep = S.mods[r.id];
  v.innerHTML = "";
  const wrap = document.createElement("div"); wrap.className = "frame-wrap";
  wrap.innerHTML = `<div class="frame-bar"><span class="pill">${esc(r.title)}</span><span class="grow"></span>
    <button class="btn ghost sm" data-a="re">${ico("refresh")}<span>Recargar</span></button>
    <a class="btn ghost sm" href="${r.frame}" target="_blank" rel="noopener">${ico("ext")}<span>Pestaña nueva</span></a></div>
    <div class="loader"><div class="bars"><i></i><i></i><i></i><i></i></div></div><iframe title="${esc(r.title)}"></iframe>`;
  v.append(wrap);
  const fr = $("iframe", wrap), ld = $(".loader", wrap);
  const load = async (force) => {
    fr.classList.remove("ready"); ld.style.opacity = 1;
    const stale = !keep || force || Date.now() - (keep.t || 0) > 8 * 60 * 1000;
    if (r.login && stale) {
      try { await api("modulo/" + r.login, { body: {} }); } catch (e) { toast("No se pudo abrir sesión automática en " + r.title, true); }
    }
    S.mods[r.id] = { t: Date.now() };
    fr.onload = () => { tidyFrame(fr, r); fr.classList.add("ready"); ld.style.opacity = 0; if (!reduce && window.gsap) gsap.from(fr, { y: 12, duration: 0.5, ease: "power3.out" }); };
    fr.src = r.frame;
  };
  $('[data-a="re"]', wrap).onclick = () => load(true);
  load(false);
}

const HINTS = {
  "activar tablet": "Genera un código de 15 minutos para autorizar la tablet de recepción, donde los clientes rellenan y firman su alta.",
  "apuntar a varias clases": "Apunta a una misma persona a varias clases de golpe: eliges los días y las horas y la inscribes en todas.",
  "cancelar esta clase": "Cancela la clase seleccionada y avisa a los inscritos según la configuración del centro.",
};
// Los módulos incrustados traen su propio «Salir»: se ocultan (se sale desde el menú del centro) y se explican los botones poco claros.
function tidyFrame(fr) {
  let doc; try { doc = fr.contentDocument; } catch (e) { return; }
  if (!doc || !doc.body) return;
  const run = () => doc.querySelectorAll("button, a").forEach((el) => {
    const t = (el.textContent || "").trim().toLowerCase();
    if (/^(salir|cerrar sesión)$/.test(t)) el.style.display = "none";
    else if (HINTS[t] && !el.title) el.title = HINTS[t];
    else if (/^centro de control$/.test(t)) el.style.display = "none";
  });
  run();
  new MutationObserver(run).observe(doc.body, { childList: true, subtree: true });
}

// ---------- Inicio ----------
async function viewInicio(v) {
  const d = await api("estado");
  let dm = null; try { const dd = await api("diario"); dm = dd.meses[dd.meses.length - 1]; } catch (e) { /* sin diario */ }
  const sv = d.servicios, sy = d.sistema;
  const nombres = [["/admin/", "Reservas · admin"], ["/alta/admin/", "Altas · admin"], ["/alta/caja/", "Caja"], ["/reservas/", "Pantalla de reservas"], ["/alta/", "Tablet de altas"], ["bot", "Bot de WhatsApp"]];
  const online = nombres.filter(([k]) => sv[k]).length;
  const hora = new Date().getHours();
  const saludo = hora < 6 ? "Buenas noches" : hora < 14 ? "Buenos días" : hora < 21 ? "Buenas tardes" : "Buenas noches";
  const stale = d.ultima_subida && Date.now() / 1000 - d.ultima_subida > 36 * 3600;
  const cn = d.conector || {};
  const ring = (val, label) => `<div class="ring"><svg viewBox="0 0 100 100"><circle class="bgc" cx="50" cy="50" r="42"/><circle class="fg" cx="50" cy="50" r="42" stroke-dasharray="263.9" stroke-dashoffset="263.9" data-v="${val}"/></svg><div class="n"><span data-n="${val}">0</span>%</div><small>${label}</small></div>`;
  const mod = (id, t, desc, ic, ok) => `<button class="card mod" data-go="${id}"><span class="st"><i class="dot ${ok ? "ok" : "ko"}"></i></span><span class="ic">${ico(ic)}</span><b>${t}</b><span class="d">${desc}</span></button>`;
  v.innerHTML = `<div class="hello"><div><div class="muted">${saludo}</div><h1>Bienvenido, <em>${esc(S.user)}</em></h1></div>
      <span class="pill ${online === nombres.length ? "" : "warn"}">${online}/${nombres.length} servicios en línea</span></div>
    ${cn.online === false || cn.error ? `<div class="banner">⚠ El PC del mostrador no está conectado con Innux${cn.error ? " (" + esc(cn.error) + ")" : ""}. La caja no puede leer ni escribir en Innux hasta que se reconecte. <a href="#/innux">Ver detalle</a></div>` : ""}
    <div class="grid g4" style="margin-bottom:16px">
      ${mod("socios", "Buscar socios", "Una ficha con cuotas, contratos y reservas", "search", true)}
      ${mod("reservas", "Reservas", "Clases, horarios, inscripciones y esperas", "cal", sv["/admin/"])}
      ${mod("altas", "Altas y contratos", "Contratos, socios en Innux, mandatos y recibos", "doc", sv["/alta/admin/"])}
      ${mod("caja", "Apuntes de caja", "Apuntar cobros y salidas como en el Excel, turnos y cierre del día", "cash", sv["/alta/caja/"])}
      ${mod("clientes", "Clientes", "Cuotas de los socios en Innux", "users", sv["/alta/caja/"])}
      ${mod("diario", "Histórico de caja", "Histórico de cobros desde 2023, buscador y Excel", "book", true)}</div>
    <div class="grid g3">
      <div class="card kpi" style="cursor:pointer" data-go="innux"><h3>Conexión con Innux</h3><div class="v"><i class="dot ${cn.online ? "ok" : "ko"}"></i> ${cn.online ? "Conectado" : "Sin conexión"}</div><div class="s">${cn.last_seen ? "Visto " + ago(Date.parse(cn.last_seen) / 1000) : "PC del mostrador"}</div></div>
      <div class="card kpi" style="cursor:pointer" data-go="diario"><h3>Caja de ${dm ? periodLabel(dm.period).toLowerCase() : "este mes"}</h3><div class="v" id="kpi-mes">0 €</div><div class="s">${dm ? dm.n + " movimientos · " + dm.dias + " días" : "Acceso exclusivo para dueños"}</div></div>
      <div class="card"><h3>Servidor</h3><div class="rings">${ring(sy.disk, "Disco")}${ring(sy.mem, "Memoria")}${ring(Math.min(100, Math.round(sy.load * 25)), "Carga")}</div><div class="muted" style="margin-top:10px;font-size:.85rem">Encendido ${sy.uptime_days} días</div></div>
      <div class="card"><h3>Servicios</h3><ul class="list">${nombres.map(([k, n]) => `<li><i class="dot ${sv[k] ? "ok" : "ko"}"></i>${n}<span class="t">${sv[k] ? "En línea" : "No responde"}</span></li>`).join("")}</ul></div>
      <div class="card"><h3>Actividad reciente</h3><ul class="list">${d.eventos.length ? d.eventos.map((e) => `<li>${esc(e.who || "—")} · ${esc(eventLabel(e.event))}<span class="t">${ago(e.t)}</span></li>`).join("") : '<li class="muted">Sin actividad</li>'}</ul></div></div>`;
  v.querySelectorAll("[data-go]").forEach((b) => (b.onclick = () => (location.hash = "#/" + b.dataset.go)));
  if (dm) countMoney($("#kpi-mes"), dm.neto); else $("#kpi-mes").textContent = "Protegido";
  stagger(".view .card, .view .hello");
  v.querySelectorAll(".ring").forEach((rg) => {
    const c = $(".fg", rg), n = $("[data-n]", rg), val = +c.dataset.v, off = 263.9 * (1 - val / 100);
    countUp(n, val);
    if (reduce || !window.gsap) c.setAttribute("stroke-dashoffset", off); else gsap.to(c, { attr: { "stroke-dashoffset": off }, duration: 1.4, ease: "power3.out" });
  });
  S.timers.push(setInterval(async () => { if (location.hash && !/^#\/inicio/.test(location.hash)) return; if (document.hidden) return; try { const n = await api("estado"); S.last = n; } catch (e) { /* silencioso */ } }, 60000));
}

// ---------- Cuentas ----------
async function viewCuentas(v, period) {
  if (period) return viewMes(v, period);
  const d = await api("cuentas");
  if (!d.meses.length) { v.innerHTML = '<div class="card"><h3>Cuentas</h3>Todavía no se ha recibido ningún informe. Cuando el PC del mostrador suba el Excel del mes, aparecerá aquí.</div>'; return; }
  v.innerHTML = `<div class="hello"><div><h1>Cuentas del <em>gimnasio</em></h1><div class="muted">Informes mensuales de Caja Gimnasio · solo lectura</div></div></div>
    <div class="months">${d.meses.map((m) => `<button class="card mod month" data-p="${m.period}"><span class="ic">${ico("chart")}</span><b>${periodLabel(m.period)}</b><span class="d">Actualizado ${ago(m.uploaded)}</span></button>`).join("")}</div>`;
  v.querySelectorAll("[data-p]").forEach((b) => (b.onclick = () => (location.hash = "#/cuentas/" + b.dataset.p)));
  stagger(".month");
}
const num = (x) => typeof x === "number";
const money = (x) => NF.format(x);
async function viewMes(v, period) {
  const d = await api("cuentas/" + encodeURIComponent(period));
  let cur = 0, q = "", sortCol = -1, sortDir = 1;
  v.innerHTML = `<div class="hello"><div><a href="#/cuentas" class="muted">← Meses</a><h1>${periodLabel(period)}</h1><div class="muted">Copia recibida ${fmtDate(d.uploaded)}</div></div>
    <a class="btn" href="${BASE}/descargar/${period}">${ico("dl")}<span>Descargar Excel</span></a></div>
    <div class="tabs">${d.hojas.map((h, i) => `<button class="tab ${i ? "" : "on"}" data-i="${i}">${esc(h.title)}</button>`).join("")}</div>
    <div class="tools"><input id="q" type="search" placeholder="Filtrar filas…"><span class="muted" id="cnt"></span></div><div class="tw" id="tw"></div>`;
  const draw = () => {
    const h = d.hojas[cur];
    if (!h.rows.length) { $("#tw").innerHTML = '<div style="padding:20px" class="muted">Hoja vacía.</div>'; $("#cnt").textContent = ""; return; }
    const head = h.rows[0]; let body = h.rows.slice(1);
    if (q) body = body.filter((r) => r.some((c) => String(c ?? "").toLowerCase().includes(q)));
    if (sortCol >= 0) body = [...body].sort((a, b) => { const x = a[sortCol], y = b[sortCol]; return (num(x) && num(y) ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "es", { numeric: true })) * sortDir; });
    const w = head.length, sums = new Array(w).fill(null);
    body.forEach((r) => r.forEach((c, i) => { if (num(c)) sums[i] = (sums[i] || 0) + c; }));
    const shown = body.slice(0, 1500);
    $("#tw").innerHTML = `<table><thead><tr>${head.map((c, i) => `<th data-c="${i}">${esc(c ?? "")}${sortCol === i ? (sortDir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
      <tbody>${shown.map((r) => `<tr>${Array.from({ length: w }, (_, i) => `<td class="${num(r[i]) ? "n" : ""}">${num(r[i]) ? money(r[i]) : esc(r[i] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody>
      ${sums.some((s) => s !== null) ? `<tfoot><tr>${sums.map((s, i) => `<td class="${s !== null ? "n" : ""}">${s !== null ? money(s) : i === 0 ? "Suma" : ""}</td>`).join("")}</tr></tfoot>` : ""}</table>`;
    $("#cnt").textContent = `${body.length} fila(s)${h.truncated ? " · hoja recortada, descarga el Excel" : ""}${body.length > 1500 ? " · mostrando 1500" : ""}`;
    $("#tw").querySelectorAll("th").forEach((th) => (th.onclick = () => { const c = +th.dataset.c; sortDir = sortCol === c ? -sortDir : 1; sortCol = c; draw(); }));
  };
  v.querySelectorAll(".tab").forEach((t) => (t.onclick = () => { v.querySelectorAll(".tab").forEach((x) => x.classList.remove("on")); t.classList.add("on"); cur = +t.dataset.i; sortCol = -1; draw(); if (!reduce && window.gsap) gsap.from("#tw tbody tr", { opacity: 0, y: 8, duration: 0.3, stagger: 0.008, clearProps: "all" }); }));
  $("#q").oninput = (e) => { q = e.target.value.toLowerCase(); draw(); };
  draw(); stagger(".hello, .tabs, .tools");
}

// ---------- Histórico de caja (histórico del Excel + Caja web) ----------
const eur = (c) => (c == null ? "" : NF.format(c / 100) + " €");
const eurN = (c) => NF.format(c / 100);
function countMoney(el, cents) {
  if (reduce || !window.gsap) { el.textContent = eur(cents); return; }
  const o = { v: 0 };
  gsap.to(o, { v: cents, duration: 1.2, ease: "power2.out", onUpdate: () => { el.textContent = eur(Math.round(o.v)); } });
}
const dmy = (iso) => (iso ? iso.slice(8, 10).replace(/^0/, "") + "-" + iso.slice(5, 7).replace(/^0/, "") + "-" + iso.slice(2, 4) : "");
const MES_CORTO = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

function viewDiarioLocked(v) {
  v.innerHTML = `<div class="lockscreen"><form class="lock-card" id="diario-unlock" autocomplete="off">
      <div class="lock-ic">${ico("lock")}</div>
      <h2>Histórico de caja</h2>
      <p class="sub">Acceso exclusivo para los dueños del gimnasio.<br>Introduce la contraseña del diario; el acceso caduca a los 15 minutos.</p>
      <div class="field"><input id="diario-password" name="password" type="password" autocomplete="current-password" placeholder=" " required maxlength="200" autofocus><label for="diario-password">Contraseña del diario</label></div>
      <p class="err" id="diario-error" role="alert"></p>
      <button class="btn block" type="submit"><span>Desbloquear diario</span></button></form></div>`;
  setTimeout(() => $("#diario-password", v)?.focus(), 50);
  $("#diario-unlock", v).onsubmit = async (e) => {
    e.preventDefault(); const btn = $("button", e.target); btn.disabled = true;
    try {
      await api("diario/desbloquear", { body: { password: $("#diario-password", v).value } });
      $("#diario-password", v).value = ""; route();
    } catch (err) { $("#diario-error", v).textContent = err.message; }
    finally { btn.disabled = false; }
  };
}

async function viewDiario(v, arg, arg2) {
  if (arg === "buscar") return viewDiarioBuscar(v, decodeURIComponent(arg2 || ""));
  if (arg && /^\d{4}-\d{2}$/.test(arg)) return viewDiarioMes(v, arg);
  const d = await api("diario");
  const ms = d.meses;
  const years = [...new Set(ms.map((m) => m.period.slice(0, 4)))];
  const tot = ms.reduce((a, m) => ({ ing: a.ing + m.ingresos, gas: a.gas + m.gastos, n: a.n + m.n }), { ing: 0, gas: 0, n: 0 });
  const max = Math.max(...ms.map((m) => Math.max(m.neto, 1)));
  const W = 920, H = 210, bw = W / ms.length;
  const bars = ms.map((m, i) => { const h = Math.max(2, (Math.max(m.neto, 0) / max) * (H - 30)); const x = i * bw + 2;
    return `<g class="bar" data-p="${m.period}"><rect class="hit" x="${i * bw}" y="0" width="${bw}" height="${H}" fill="transparent"/><rect class="b y${years.indexOf(m.period.slice(0, 4)) % 4}" x="${x}" y="${H - h}" width="${bw - 4}" height="${h}" rx="3"/></g>`; }).join("");
  const labels = years.map((y) => { const i = ms.findIndex((m) => m.period.startsWith(y)); return `<text x="${i * bw + 2}" y="${H + 16}" class="yl">${y}</text>`; }).join("");
  v.innerHTML = `<div class="hello"><div><h1>Diario de <em>caja</em></h1><div class="muted">Histórico de cobros desde ${periodLabel(ms[0].period)} · Excel hasta el ${dmy(d.hasta)} y Caja web a partir de ahí</div></div>
      <div class="row"><a class="btn" href="${BASE}/descargar/diario">${ico("dl")}<span>Excel completo</span></a>
      <a class="btn ghost" href="${BASE}/descargar/socios" title="Todos los socios dados de alta, en el formato de la plantilla de socios">${ico("dl")}<span>Exportar socios</span></a>
      </div></div>
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card kpi"><h3>Ingresos totales</h3><div class="v" id="k1">0 €</div><div class="s">${tot.n.toLocaleString("es-ES")} movimientos</div></div>
      <div class="card kpi"><h3>Gastos y retiradas</h3><div class="v" id="k2">0 €</div></div>
      <div class="card kpi"><h3>Neto acumulado</h3><div class="v" id="k3">0 €</div></div>
      <div class="card kpi"><h3>Meses registrados</h3><div class="v" id="k4">0</div></div></div>
    <div class="card" style="margin-bottom:16px"><h3>Neto por mes</h3><svg viewBox="0 0 ${W} ${H + 22}" class="chart" id="chart">${bars}${labels}</svg><div class="muted" id="tip" style="min-height:1.4em;font-size:.88rem">Pasa el ratón por una barra · pulsa para abrir el mes</div></div>
    <div class="tools"><input id="gq" type="search" placeholder="Buscar en todo el histórico: nombre, nº de socio, concepto…" style="min-width:min(520px,100%)"><button class="btn" id="gb">Buscar</button></div>
    <details class="adv"><summary>Opciones avanzadas</summary><div class="card" style="margin-top:10px"><h3>Actualizar el histórico desde un Excel</h3>
      <p class="muted" style="margin:0 0 12px">Solo si siguen usando el Excel «Diario de Caja» y quieren traer una versión más reciente. <b>Sustituye todo el histórico</b> por el contenido del archivo; antes se guarda automáticamente una copia de seguridad del anterior.</p>
      <label class="btn ghost">${ico("refresh")}<span>Elegir Excel y actualizar…</span><input type="file" id="upx" accept=".xlsx" hidden></label></div></details>
    ${years.slice().reverse().map((y) => `<h3 style="margin:18px 0 8px;color:var(--mut);letter-spacing:.1em">${y}</h3><div class="months">${ms.filter((m) => m.period.startsWith(y)).map((m) => `<button class="card mod month" data-p="${m.period}"><b>${periodLabel(m.period).split(" ")[0]}</b><span class="d">${eur(m.neto)} · ${m.n} mov.</span>${m.fuente !== "excel" ? '<span class="pill" title="Incluye cobros registrados en la Caja web después del último día del Excel">incluye Caja web</span>' : ""}</button>`).join("")}</div>`).join("")}`;
  countMoney($("#k1"), tot.ing); countMoney($("#k2"), tot.gas); countMoney($("#k3"), tot.ing - tot.gas); countUp($("#k4"), ms.length);
  v.querySelectorAll("[data-p]").forEach((b) => (b.onclick = () => (location.hash = "#/diario/" + b.dataset.p)));
  const go = () => { const q = $("#gq").value.trim(); if (q.length >= 2) location.hash = "#/diario/buscar/" + encodeURIComponent(q); };
  $("#gb").onclick = go; $("#gq").onkeydown = (e) => { if (e.key === "Enter") go(); };
  const ch = $("#chart");
  ch.addEventListener("pointerover", (e) => { const g = e.target.closest(".bar"); if (!g) return; const m = ms.find((x) => x.period === g.dataset.p);
    $("#tip").textContent = `${periodLabel(m.period)}: neto ${eur(m.neto)} · ingresos ${eur(m.ingresos)} · gastos ${eur(m.gastos)} · ${m.n} movimientos`; });
  ch.addEventListener("click", (e) => { const g = e.target.closest(".bar"); if (g) location.hash = "#/diario/" + g.dataset.p; });
  $("#upx").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    if (!confirm("ATENCIÓN: vas a SUSTITUIR todo el histórico del diario por el contenido de «" + f.name + "».\n\nSe guardará una copia del histórico actual, pero los cambios se verán al momento para todos.\n\n¿Seguro que quieres continuar?")) { e.target.value = ""; return; }
    toast("Importando Excel…");
    try {
      const r = await fetch(BASE + "/api/diario/base", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": S.csrf }, body: f });
      const j = await r.json(); if (!j.ok) throw new Error(j.error || "Error");
      toast(`Importado: ${j.meses} meses, ${j.filas} filas, hasta el ${dmy(j.hasta)}`); route();
    } catch (err) { toast(err.message, true); }
  };
  if (!reduce && window.gsap) { gsap.from("#chart .b", { scaleY: 0, transformOrigin: "bottom", duration: 0.9, stagger: 0.012, ease: "power3.out" }); }
  stagger(".hello, .view .grid .card, .months .card");
}

async function viewDiarioMes(v, period) {
  const [d, all] = await Promise.all([api("diario/" + period), api("diario")]);
  const idx = all.meses.findIndex((m) => m.period === period);
  const prev = all.meses[idx - 1], next = all.meses[idx + 1];
  const r = d.resumen, rows = d.filas;
  const maxc = Math.max(...d.conceptos.map((c) => Math.abs(c[2])), 1);
  let q = "", onlyTot = false;
  v.innerHTML = `<div class="hello"><div><a href="#/diario" class="muted">← Histórico de caja</a><h1>${periodLabel(period)}</h1>
      <div class="row">${prev ? `<a class="btn ghost sm" href="#/diario/${prev.period}">← ${periodLabel(prev.period)}</a>` : ""}${next ? `<a class="btn ghost sm" href="#/diario/${next.period}">${periodLabel(next.period)} →</a>` : ""}</div></div>
      <a class="btn" href="${BASE}/descargar/diario/${period}">${ico("dl")}<span>Excel del mes</span></a></div>
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card kpi"><h3>Ingresos</h3><div class="v" id="a1">0 €</div></div><div class="card kpi"><h3>Gastos y retiradas</h3><div class="v" id="a2">0 €</div></div>
      <div class="card kpi"><h3>Neto</h3><div class="v" id="a3">0 €</div></div><div class="card kpi"><h3>Movimientos</h3><div class="v"><span id="a4">0</span></div><div class="s">${r.dias} días con actividad</div></div></div>
    <div class="grid g3" style="margin-bottom:16px"><div class="card"><h3>Por concepto</h3><div class="cbars">${d.conceptos.map((c) => `<div class="cb"><span>${esc(c[0])} <small>×${c[1]}</small></span><i style="--w:${Math.max(3, Math.abs(c[2]) / maxc * 100)}%" class="${c[2] < 0 ? "neg" : ""}"></i><b>${eur(c[2])}</b></div>`).join("")}</div></div></div>
    <div class="tools"><input id="q" type="search" placeholder="Filtrar filas…"><label class="chk"><input type="checkbox" id="ot"> Solo totales</label><span class="muted" id="cnt"></span></div>
    <div class="tw xl" id="tw"></div>`;
  countMoney($("#a1"), r.ingresos); countMoney($("#a2"), r.gastos); countMoney($("#a3"), r.neto); countUp($("#a4"), r.n);
  const draw = () => {
    let list = rows.filter((x) => x.kind !== "nota" || x.notes);
    if (onlyTot) list = list.filter((x) => x.kind === "total");
    if (q) list = list.filter((x) => x.kind !== "total" && [x.concept, x.name, x.socio, x.staff, x.notes, dmy(x.day)].some((t) => String(t ?? "").toLowerCase().includes(q)));
    $("#tw").innerHTML = `<table><thead><tr><th></th><th>efectivo</th><th>concepto</th><th>nombre</th><th>nº socio</th><th>gestionado por</th><th>NOTAS</th></tr></thead><tbody>${
      list.slice(0, 2500).map((x) => x.kind === "total"
        ? `<tr class="tot"><td>total</td><td class="n">${eurN(x.cents ?? 0)}</td><td></td><td></td><td></td><td class="c">${esc(x.staff ?? "")}</td><td class="c">${x.notes ? `<span class="${/cierre/i.test(x.notes) ? "ok" : ""}">${esc(x.notes)}</span>` : ""}</td></tr>`
        : `<tr><td>${dmy(x.day)}</td><td class="n ${x.cents < 0 ? "neg" : ""}">${x.cents == null ? "" : eurN(x.cents)}</td><td>${esc(x.concept ?? "")}</td><td>${esc(x.name ?? "")}</td><td class="c">${esc(x.socio ?? "")}</td><td class="c">${esc(x.staff ?? "")}</td><td class="c">${esc(x.notes ?? "")}</td></tr>`).join("")}</tbody></table>`;
    $("#cnt").textContent = list.length + " fila(s)";
  };
  $("#q").oninput = (e) => { q = e.target.value.toLowerCase(); draw(); };
  $("#ot").onchange = (e) => { onlyTot = e.target.checked; draw(); };
  draw(); stagger(".hello, .view .grid .card");
}

async function viewDiarioBuscar(v, q) {
  const d = await api("diario-buscar?q=" + encodeURIComponent(q));
  const tot = d.resultados.reduce((a, x) => a + (x.cents || 0), 0);
  v.innerHTML = `<div class="hello"><div><a href="#/diario" class="muted">← Histórico de caja</a><h1>Resultados para «${esc(q)}»</h1>
      <div class="muted">${d.resultados.length}${d.resultados.length >= 300 ? "+" : ""} movimientos · suma ${eur(tot)}</div></div></div>
    <div class="tools"><input id="gq" type="search" value="${esc(q)}" placeholder="Nombre, nº de socio, concepto…"><button class="btn" id="gb">Buscar</button></div>
    <div class="tw xl"><table><thead><tr><th>día</th><th>efectivo</th><th>concepto</th><th>nombre</th><th>nº socio</th><th>gestionado por</th><th>NOTAS</th></tr></thead><tbody>${d.resultados.map((x) =>
      `<tr class="lnk" data-p="${x.period}"><td>${dmy(x.day)}</td><td class="n ${x.cents < 0 ? "neg" : ""}">${eurN(x.cents)}</td><td>${esc(x.concept ?? "")}</td><td>${esc(x.name ?? "")}</td><td class="c">${esc(x.socio ?? "")}</td><td class="c">${esc(x.staff ?? "")}</td><td class="c">${esc(x.notes ?? "")}</td></tr>`).join("") || '<tr><td colspan="7" class="muted" style="padding:20px">Sin resultados.</td></tr>'}</tbody></table></div>`;
  const go = () => { const t = $("#gq").value.trim(); if (t.length >= 2) location.hash = "#/diario/buscar/" + encodeURIComponent(t); };
  $("#gb").onclick = go; $("#gq").onkeydown = (e) => { if (e.key === "Enter") go(); };
  v.querySelectorAll("tr.lnk").forEach((tr) => (tr.onclick = () => (location.hash = "#/diario/" + tr.dataset.p)));
  stagger(".hello, .tools");
}

// ---------- Conexión Innux ----------
// ---------- Bot de WhatsApp ----------
async function viewBot(v) {
  const pillc = (cls, txt) => `<span class="pill ${cls}">${txt}</span>`;
  const row = (k, val) => `<li>${k}<span class="t" style="color:var(--txt)">${val}</span></li>`;
  const yn = (b, y = "Sí", n = "No") => (b ? `<i class="dot ok"></i> ${y}` : `<i class="dot ko"></i> ${n}`);
  const when = (ts) => (ts ? `${ago(ts)} · ${new Date(ts * 1000).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}` : "—");
  const CAL = { GREEN: "Alta", YELLOW: "Media (vigilar)", RED: "Baja (riesgo)", UNKNOWN: "Sin datos" };
  const EST = { CONNECTED: "Conectado", DISCONNECTED: "Desconectado", PENDING: "Pendiente", FLAGGED: "Marcado por Meta", RESTRICTED: "Restringido", UNAVAILABLE: "No disponible" };

  v.innerHTML = `<div class="hello"><div><h1>Bot de <em>WhatsApp</em></h1><div class="muted">Salud, conexión con Meta y control del asistente de reservas</div></div>
      <div class="row"><span id="bot-pill"></span><button class="btn ghost" id="bot-rf">${ico("refresh")}<span>Actualizar</span></button></div></div>
    <div id="bot-alerts"></div>
    <div class="grid g3" id="bot-live"><div class="card"><h3>Cargando…</h3></div></div>
    <div class="card" style="margin-top:16px" id="bot-ctl"><h3>Control</h3>
      <div class="bot-actions">
        <div class="bot-act"><div><b>Pausar o reanudar el bot</b><p class="muted" id="bot-pause-txt"></p></div><button class="btn" id="bot-pause"><span>…</span></button></div>
        <div class="bot-act"><div><b>Reiniciar el bot</b><p class="muted">Tarda unos 10 segundos. Úsalo si deja de responder.</p></div><button class="btn ghost" id="bot-restart"><span>Reiniciar</span></button></div>
        <div class="bot-act"><div><b>Responder a números no vinculados</b><p class="muted">Si está activo, quien escriba sin estar en el directorio recibe el enlace a la web de reservas. Si no, no se le responde.</p></div><button class="btn ghost" id="bot-unknown"><span>…</span></button></div>
        <div class="bot-act"><div><b>Cambiar la imagen del horario</b><p class="muted" id="bot-hor-txt">Es la imagen que envía el botón «Ver horario». PNG de hasta 6 MB. Se guarda copia de la anterior.</p></div>
          <div class="row"><input type="file" id="bot-file" accept="image/png" hidden><button class="btn ghost" id="bot-hor"><span>Subir PNG…</span></button></div></div>
      </div></div>`;
  let cur = null, busy = false;

  const paint = (d) => {
    const s = d.status; cur = s;
    const alerts = [], stale = !s || d.age > 180;
    if (!s) alerts.push(["ko", "El monitor del bot todavía no ha enviado datos."]);
    else if (stale) alerts.push(["ko", `El monitor no se actualiza desde ${ago(s.t)}. Los datos pueden no ser actuales.`]);
    if (s) {
      if (!s.service.active || !s.port) alerts.push(["ko", "El bot está caído o no responde en el puerto local. Prueba «Reiniciar»."]);
      if (s.paused) alerts.push(["warn", "El bot está en pausa: no contesta a nadie. Pulsa «Reanudar» para activarlo."]);
      if (!s.graph_ok) alerts.push(["warn", "No se pudo consultar a Meta. Puede ser un fallo de internet o del token."]);
      else if (!s.token.valid) alerts.push(["ko", "El token de acceso a WhatsApp no es válido o ha caducado: el bot no puede enviar mensajes."]);
      else if (s.token.expires && s.token.expires * 1000 - Date.now() < 3 * 86400e3) alerts.push(["warn", "El token de WhatsApp caduca en menos de 3 días."]);
      if (s.phone && s.phone.status && s.phone.status !== "CONNECTED") alerts.push(["ko", "El número de WhatsApp no está conectado a la API (estado: " + esc(EST[s.phone.status] || s.phone.status) + ")."]);
      if (s.phone && (s.phone.quality_rating === "RED" || s.phone.quality_rating === "YELLOW")) alerts.push(["warn", "La calidad del número en Meta es " + esc((CAL[s.phone.quality_rating] || "").toLowerCase()) + ": evita enviar mensajes no solicitados."]);
      if (!s.backend) alerts.push(["ko", "El sistema de reservas no responde: el bot no podrá reservar."]);
      if (s.queue.review > 0) alerts.push(["warn", `${s.queue.review} evento(s) quedaron pendientes de revisión (no se respondieron). Si son antiguos puedes ignorarlos.`]);
      if (s.last24.errors > 0) alerts.push(["warn", `${s.last24.errors} error(es) de arranque o credenciales en las últimas 24 h.`]);
    }
    const bad = alerts.some((a) => a[0] === "ko");
    $("#bot-pill", v).innerHTML = !s || bad ? pillc("ko", "Con problemas") : s.paused ? pillc("warn", "En pausa") : pillc("", "En línea");
    $("#bot-alerts", v).innerHTML = alerts.length ? `<div class="card" style="margin-bottom:16px"><ul class="list">${alerts.map(([c, t]) => `<li>${pillc(c, c === "ko" ? "Importante" : "Aviso")}<span style="margin-left:6px">${t}</span></li>`).join("")}</ul></div>` : `<div class="card" style="margin-bottom:16px"><ul class="list"><li>${pillc("", "Todo correcto")}<span style="margin-left:6px">El bot está activo y conectado con WhatsApp.</span></li></ul></div>`;
    if (!s) { $("#bot-live", v).innerHTML = ""; return; }
    const ph = s.phone || {}, q = s.queue, l = s.last24, r = q.receipts24 || {};
    const exp = s.token.valid ? (s.token.expires ? new Date(s.token.expires * 1000).toLocaleDateString("es-ES") : "Nunca (permanente)") : "—";
    $("#bot-live", v).innerHTML = `
      <div class="card"><h3>Servicio</h3><ul class="list">
        ${row("Bot", yn(s.service.active && s.port, "Funcionando", "Caído"))}
        ${row("Activo desde", s.service.since ? when(s.service.since) : "—")}
        ${row("Reinicios automáticos", s.service.restarts)}
        ${row("Sistema de reservas", yn(s.backend, "Responde", "No responde"))}
        ${row("Estado del bot", s.paused ? "En pausa" : "Activo")}
        ${row("Datos actualizados", ago(s.t))}</ul></div>
      <div class="card"><h3>Conexión con WhatsApp (Meta)</h3><ul class="list">
        ${row("Número", esc(ph.display_phone_number || "—"))}
        ${row("Nombre verificado", esc(ph.verified_name || "—"))}
        ${row("Estado del número", ph.status ? yn(ph.status === "CONNECTED", esc(EST[ph.status] || ph.status), esc(EST[ph.status] || ph.status)) : "—")}
        ${row("Calidad", esc(CAL[ph.quality_rating] || ph.quality_rating || "—"))}
        ${row("Modo", s.mode === "oficial" ? "Número oficial" : "Número de PRUEBA")}
        ${row("Token de acceso", yn(s.token.valid, "Válido", "No válido"))}
        ${row("Caduca", exp)}
        ${row("Números autorizados", s.directory ?? "—")}</ul></div>
      <div class="card"><h3>Actividad (últimas 24 h)</h3><ul class="list">
        ${row("Eventos procesados", l.processed)}
        ${row("Pendientes de revisión", l.review)}
        ${row("Último evento", when(l.last_event || q.last_receipt))}
        ${row("Mensajes enviados / entregados", `${r.sent || 0} / ${r.delivered || 0}`)}
        ${row("Mensajes leídos / fallidos", `${r.read || 0} / ${r.failed || 0}`)}
        ${row("En cola ahora", q.pending + q.processing)}
        ${row("Revisión pendiente (histórico)", q.review)}</ul></div>`;
    $("#bot-pause-txt", v).textContent = s.paused ? "Ahora está en pausa: no responde a ningún mensaje." : "Ahora está activo. En pausa no responde a nadie (los mensajes recibidos se descartan).";
    $("#bot-pause span", v).textContent = s.paused ? "Reanudar" : "Pausar";
    $("#bot-pause", v).className = "btn" + (s.paused ? "" : " ghost");
    $("#bot-unknown span", v).textContent = s.unknown_reply ? "Activado · Desactivar" : "Desactivado · Activar";
    $("#bot-hor-txt", v).textContent = "Es la imagen que envía el botón «Ver horario». PNG de hasta 6 MB. Se guarda copia de la anterior." + (s.horario ? " Última actualización: " + when(s.horario) + "." : "");
  };
  const load = async () => { try { paint(await api("bot")); } catch (e) { if (e.message !== "Sesión caducada") toast(e.message, true); } };

  const act = async (btn, body, ask) => {
    if (busy || (ask && !confirm(ask))) return;
    busy = true; const label = btn.querySelector("span").textContent; btn.disabled = true; btn.querySelector("span").textContent = "Aplicando…";
    try { const r = await api("bot/accion", { body }); toast(r.message || "Hecho"); await load(); }
    catch (e) { toast(e.message, true); }
    finally { busy = false; btn.disabled = false; btn.querySelector("span").textContent = label; load(); }
  };
  $("#bot-rf", v).onclick = () => act($("#bot-rf", v), { verb: "refresh" });
  $("#bot-pause", v).onclick = (e) => act(e.currentTarget, { verb: cur?.paused ? "resume" : "pause" }, cur?.paused ? null : "¿Pausar el bot? Dejará de responder a todos los clientes hasta que lo reanudes.");
  $("#bot-restart", v).onclick = (e) => act(e.currentTarget, { verb: "restart" }, "¿Reiniciar el bot ahora? Durante unos segundos no responderá.");
  $("#bot-unknown", v).onclick = (e) => act(e.currentTarget, { verb: "unknown_reply", value: cur?.unknown_reply ? "0" : "1" }, "Este cambio reinicia el bot unos segundos. ¿Continuar?");
  $("#bot-hor", v).onclick = () => $("#bot-file", v).click();
  $("#bot-file", v).onchange = async (e) => {
    const f = e.target.files[0]; e.target.value = ""; if (!f || busy) return;
    if (f.type !== "image/png" || f.size > 6 * 1024 * 1024) { toast("Debe ser un PNG de menos de 6 MB.", true); return; }
    if (!confirm("¿Sustituir la imagen del horario por «" + f.name + "»?")) return;
    busy = true; const b = $("#bot-hor", v); b.disabled = true;
    try {
      const r = await fetch(BASE + "/api/bot/horario", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": S.csrf, "Content-Type": "image/png" }, body: f });
      const j = await r.json(); if (!j.ok) throw new Error(j.error || "No se pudo subir"); toast(j.message || "Horario actualizado");
    } catch (err) { toast(err.message, true); } finally { busy = false; b.disabled = false; load(); }
  };
  await load();
  S.timers.push(setInterval(() => { if (!document.hidden && !busy && location.hash === "#/bot") load(); }, 15000));
}

async function viewInnux(v) {
  const load = async () => {
    const d = await api("conector");
    const c = d.conectores.caja || {}, a = d.conectores.altas || {};
    const ok = (b) => `<span class="pill ${b ? "" : "ko"}">${b ? "Correcto" : "Revisar"}</span>`;
    const t = (iso) => (iso ? ago(Date.parse(iso) / 1000) : "—");
    const row = (k, val) => `<li>${k}<span class="t" style="color:var(--txt)">${val}</span></li>`;
    const hl = c.health || {};
    v.innerHTML = `<div class="hello"><div><h1>Conexión con <em>Innux</em></h1><div class="muted">Estado del conector del PC del mostrador (la base de datos nunca se expone a Internet)</div></div>
      <button class="btn ghost" id="rf">${ico("refresh")}<span>Actualizar</span></button></div>
      <div class="grid g3">
      <div class="card"><h3>Caja ↔ Innux ${c.error ? ok(false) : ok(c.pc_online && !c.sql_error)}</h3>${c.error ? `<p class="muted">${esc(c.error)}</p>` : `<ul class="list">
        ${row("PC del mostrador", c.pc_online ? '<i class="dot ok"></i> En línea' : '<i class="dot ko"></i> Sin conexión')}
        ${row("Última señal", t(c.last_seen))}
        ${row("Última consulta SQL correcta", t(c.last_sql_ok))}
        ${row("Error SQL", c.sql_error ? esc(c.sql_error) : "Ninguno")}
        ${row("Operaciones de escritura en cola", c.pending_writes ?? "—")}
        </ul><details class="adv"><summary>Detalles técnicos</summary><ul class="list" style="margin-top:8px">
        ${row("Versión del conector", esc(c.agent_version || "—"))}
        ${row("Base de datos", esc(hl.database || "—"))}
        ${row("Servidor SQL", esc(hl.server || "—"))}
        ${row("Usuario de Windows", esc(hl.identity || "—"))}</ul></details>`}</div>
      <div class="card"><h3>Altas ↔ Innux ${a.error ? ok(false) : ok(a.configured && !a.pendientes_innux)}</h3>${a.error ? `<p class="muted">${esc(a.error)}</p>` : `<ul class="list">
        ${row("Conector configurado", a.configured ? "Sí" : "No")}
        ${row("Última señal", t(a.last_seen))}
        ${row("Próximo nº de socio", a.next_number ?? "—")}
        ${row("Tarifas / grupos leídos de Innux", (a.planes ?? "—") + " / " + (a.grupos ?? "—"))}
        ${row("Altas pendientes de completar en Innux", a.pendientes_innux ?? "—")}
        ${row("Trabajo en curso", a.trabajo_en_curso ? "Sí" : "No")}
        ${row("Socios en el portal", a.socios ?? "—")}</ul>`}</div>
      <div class="card"><h3>Qué hace cada conector</h3><ul class="list">
        <li>Caja: lee cobros en efectivo y socios de Innux, y activa o cobra cuotas desde la web.</li>
        <li>Altas: crea el socio, la foto, la tarjeta y la cuota tras aceptar un contrato.</li>
        <li class="muted">Si el PC está apagado, la web sigue funcionando y las operaciones esperan en cola hasta que vuelva.</li></ul></div></div>`;
    $("#rf").onclick = () => { _l(); };
    stagger(".view .card, .view .hello");
  };
  const _l = () => load().catch((e) => toast(e.message, true));
  await load();
  S.timers.push(setInterval(() => { if (!document.hidden && location.hash === "#/innux") load().catch(() => {}); }, 20000));
}

// ---------- Seguridad ----------
async function viewSeguridad(v) {
  const d = await api("seguridad");
  v.innerHTML = `<div class="hello"><div><h1>Seguridad</h1><div class="muted">Sesiones y actividad de tu cuenta</div></div></div>
    <div class="grid g3"><div class="card kpi"><h3>Sesiones abiertas</h3><div class="v"><span id="ns">0</span></div><div class="s">con tu usuario</div><br><button class="btn ghost sm" id="co">Cerrar las demás</button></div>
    <div class="card kpi"><h3>Verificación en dos pasos</h3><div class="v">${d.mfa ? "Activa" : "Desactivada"}</div><div class="s">${d.mfa ? "Se pide código en cada acceso" : "Temporal: reactívala cuando termines las pruebas"}</div></div></div>
    <div class="card" style="margin-top:16px"><h3>Actividad reciente</h3><ul class="list">${d.eventos.map((e) => `<li>${esc(eventLabel(e.event))} <span class="muted">${esc(e.event === "qa_peticion" ? "Consulta de pantalla" : e.detail || "")}</span><span class="t">${esc(e.ip || "")}${e.own ? " (este servidor)" : ""} · ${fmtDate(e.t)}</span></li>`).join("") || '<li class="muted">Sin actividad</li>'}</ul></div>`;
  countUp($("#ns"), d.sesiones); stagger(".view .card, .view .hello");
  $("#co").onclick = async () => { await api("cerrar-otras", { body: {} }); toast("Otras sesiones cerradas"); route(); };
}

// ---------- paleta de comandos ----------
function openPalette() {
  if ($(".pal-bg")) return;
  const items = [...ROUTES.map((r) => ({ t: r.title, go: "#/" + r.id })), { t: "Tablet de altas (nueva pestaña)", url: "/alta/" }, { t: "Pantalla de reservas (nueva pestaña)", url: "/reservas/" }];
  const bgEl = document.createElement("div"); bgEl.className = "pal-bg";
  bgEl.innerHTML = '<div class="pal"><input placeholder="Ir a una sección…" autofocus><ul></ul></div>';
  document.body.append(bgEl);
  const inp = $("input", bgEl), ul = $("ul", bgEl); let sel = 0, list = items;
  const close = () => bgEl.remove();
  const paint = () => { ul.innerHTML = list.map((it, i) => `<li class="${i === sel ? "on" : ""}" data-i="${i}">${esc(it.t)}</li>`).join(""); ul.querySelectorAll("li").forEach((li) => (li.onclick = () => run(list[+li.dataset.i]))); };
  const run = (it) => { if (!it) return; close(); if (it.url) open(it.url, "_blank", "noopener"); else location.hash = it.go; };
  inp.oninput = () => { const q = inp.value.toLowerCase(); list = items.filter((i) => i.t.toLowerCase().includes(q)); sel = 0; paint(); };
  inp.onkeydown = (e) => { if (e.key === "Escape") close(); else if (e.key === "ArrowDown") { sel = Math.min(sel + 1, list.length - 1); paint(); } else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); paint(); } else if (e.key === "Enter") run(list[sel]); };
  bgEl.onclick = (e) => { if (e.target === bgEl) close(); };
  paint(); inp.focus();
  if (!reduce && window.gsap) gsap.from(".pal", { y: -20, opacity: 0, scale: 0.97, duration: 0.3, ease: "power3.out" });
}

// ---------- arranque ----------
(async () => {
  try {
    const j = await api("me", { soft: true });
    if (j.ok) { S.csrf = j.csrf; S.user = j.user; showApp(); } else showLogin();
  } catch (e) { showLogin(); }
})();
