'use strict';
/* Caja Top Fitness — interfaz. Todo el texto de datos entra por textContent (sin innerHTML). */
const BASE = location.pathname.replace(/\/[^/]*$/, '').replace(/\/$/, '') || '/alta/caja';
const API = BASE + '/api';
const S = {user: null, csrf: '', staff: [], prices: {}, flags: {}, day: null, today: null, view: 'hoja', snap: null,
           timer: null, lastRefreshAsk: 0};
const root = document.getElementById('app');

// ---------------------------------------------------------------- utilidades
// Atributos booleanos HTML: presentes = activos. Un 0 / '0' / '' que llegue de la API (SQLite devuelve 0/1) NO debe activarlos.
const BOOL_ATTRS = new Set(['disabled', 'readonly', 'hidden', 'required', 'checked', 'selected', 'multiple', 'open', 'autofocus']);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (BOOL_ATTRS.has(k)) { if (v && v !== '0') el.setAttribute(k, ''); continue; }
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'value') el.value = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const uuid = () => crypto.randomUUID();
const fmtDay = d => d ? d.split('-').reverse().join('/') : '';
function fmtInstant(iso) {
  if (!iso) return 'nunca';
  const d = new Date(iso);
  return isNaN(d) ? String(iso) : d.toLocaleString('es-ES', {timeZone: 'Europe/Madrid', dateStyle: 'short', timeStyle: 'short'});
}
function ago(iso) {
  if (!iso) return null;
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return s < 90 ? s + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : s < 172800 ? Math.round(s / 3600) + ' h' : Math.round(s / 86400) + ' d';
}
function euros(c) {
  if (c == null) return '—';
  const neg = c < 0, a = Math.abs(c);
  return (neg ? '−' : '') + Math.floor(a / 100).toLocaleString('es-ES') + ',' + String(a % 100).padStart(2, '0') + ' €';
}
// Texto -> céntimos sin coma flotante; redondeo ROUND_HALF_UP decimal.
function parseCents(text) {
  if (text == null) return null;
  let t = String(text).trim().replace(/€/g, '').replace(/\s/g, '');
  if (!t) return null;
  t = t.replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(t)) throw new Error('Importe no válido: usa números con coma o punto.');
  let [i, f = ''] = t.split('.');
  f = (f + '000').slice(0, 3);
  let c = BigInt(i) * 100n + BigInt(f.slice(0, 2)) + (f[2] >= '5' ? 1n : 0n);
  if (c > 9999999900n) throw new Error('Importe fuera de rango.');
  return Number(c);
}
const centsText = c => c == null ? '' : (c / 100).toFixed(2).replace('.', ',');
async function api(method, path, body) {
  const opts = {method, headers: {'Accept': 'application/json'}, credentials: 'same-origin'};
  if (method === 'POST') { opts.headers['Content-Type'] = 'application/json'; opts.headers['X-CSRF-Token'] = S.csrf; opts.body = JSON.stringify(body || {}); }
  const r = await fetch(API + path, opts);
  const data = await r.json().catch(() => ({ok: false, error: 'Respuesta no válida'}));
  if (r.status === 401 && path !== '/login' && path !== '/password') { S.user = null; render(); }
  if (!data.ok) { const e = new Error(data.error || 'Error'); e.status = r.status; e.data = data; throw e; }
  return data;
}
function toast(msg, bad) {
  const t = h('div', {class: 'toast' + (bad ? ' bad' : ''), role: 'status'}, msg);
  document.body.append(t); setTimeout(() => t.remove(), bad ? 7000 : 3500);
}
async function waitJob(id, ms = 45000, onTick) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const {job} = await api('GET', '/jobs/' + id);
    if (onTick) onTick(job);
    if (['succeeded', 'rejected', 'review_required', 'expired'].includes(job.status)) return job;
    await new Promise(r => setTimeout(r, 800));
  }
  return null;   // sigue en cola: NO significa que haya fallado ni que se haya cobrado
}
function modal(title, body, buttons, onClose) {
  const close = () => { ov.remove(); if (onClose) onClose(); };
  const ov = h('div', {class: 'overlay', role: 'dialog', 'aria-modal': 'true'},
    h('div', {class: 'modal'},
      h('div', {class: 'head'}, h('h2', {}, title), h('button', {onclick: close, 'aria-label': 'Cerrar'}, '✕')),
      h('div', {class: 'body'}, body), h('div', {class: 'foot'}, buttons(close))));
  document.body.append(ov);
  const first = ov.querySelector('.body input:not([type=checkbox]):not([hidden]),.body select,.body textarea'); if (first) setTimeout(() => first.focus(), 30);
  return {close, el: ov};
}
const field = (label, input) => h('div', {}, h('label', {}, label), input);
function employeeSelect(selected) {
  const sel = h('select', {}, h('option', {value: ''}, 'Elige…'), S.staff.map(n => h('option', {value: n}, n)));
  const other = h('input', {placeholder: 'Nombre (Otro)', class: 'hidden-field'});
  other.hidden = true;
  sel.addEventListener('change', () => { other.hidden = sel.value !== 'Otro'; });
  if (selected && S.staff.includes(selected)) sel.value = selected;
  const wrap = h('div', {}, sel, other);
  wrap.get = () => sel.value === 'Otro' ? other.value.trim() : sel.value;
  wrap.set = v => { if (S.staff.includes(v)) { sel.value = v; other.hidden = v !== 'Otro'; } else if (v) { sel.value = 'Otro'; other.hidden = false; other.value = v; } };
  return wrap;
}
const can = p => S.user && S.user.perms.includes(p);

// ---------------------------------------------------------------- sesión
function renderLogin() {
  const u = h('input', {autocomplete: 'username', autocapitalize: 'none'}), p = h('input', {type: 'password', autocomplete: 'current-password'});
  const err = h('p', {class: 'err'});
  const go = async () => {
    try { const r = await api('POST', '/login', {username: u.value, password: p.value}); S.csrf = r.csrf; await boot(true); }
    catch (e) { err.textContent = e.message; }
  };
  p.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
  root.replaceChildren(h('div', {class: 'login panel'}, h('div', {class: 'brand'}, h('img', {src: '/alta/assets/logo.jpg', alt: ''}), h('span', {class: 'brand-name'}, 'TOP FITNESS', h('small', {}, 'CAJA'))), h('p', {class: 'muted'}, 'Acceso del personal'),
    field('Usuario', u), field('Contraseña', p), err, h('p', {}, h('button', {class: 'primary', onclick: go}, 'Entrar'))));
}
function renderChangePassword() {
  const o = h('input', {type: 'password'}), n = h('input', {type: 'password'}), err = h('p', {class: 'err'});
  root.replaceChildren(h('div', {class: 'login panel'}, h('h1', {}, 'Cambia tu contraseña'), h('p', {class: 'muted'}, 'Mínimo 12 caracteres.'),
    field('Contraseña actual', o), field('Nueva contraseña', n), err,
    h('button', {class: 'primary', onclick: async () => {
      try { await api('POST', '/password', {old: o.value, new: n.value}); await boot(); } catch (e) { err.textContent = e.message; } }}, 'Guardar')));
}
async function boot(strict) {
  try {
    const r = await api('GET', CLIENTS_ONLY ? '/me?clients=1' : '/me');
    Object.assign(S, {user: r.user, csrf: r.csrf, staff: r.staff, prices: r.prices, flags: r.flags, today: r.today, lastEmployee: r.last_employee,
                      openingPending: r.opening_pending, lastCounted: r.last_counted, build: r.build, openingHour: r.opening_hour});
    if (!S.day) S.day = S.today;
    const wanted = location.hash.slice(1);   // p. ej. /alta/caja/#hoja abre directamente el Diario
    if (S.view === 'hoja' && VIEWS.includes(wanted)) S.view = wanted;
    render();
  } catch (e) { S.user = null; if (strict) throw e; render(); }
}

// ---------------------------------------------------------------- estructura
const TABS = [['hoja', 'Apuntes del día'], ['historico', 'Consultar histórico'], ['mas', 'Más']];
const VIEWS = ['hoja', 'historico', 'mas', 'cuotas'];   // cuotas no tiene pestaña: se abre desde Clientes (Administración)
const CLIENTS_ONLY = /[?&]solo=1/.test(location.search) && location.hash === '#cuotas';
const SOLO = /[?&]solo=1/.test(location.search);       // incrustado sin pestañas
if (SOLO) document.documentElement.classList.add('solo');
function go(view) {
  S.view = view; history.replaceState(null, '', '#' + view);
  document.querySelectorAll('nav.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === view));
  const side = document.getElementById('side'); if (side) side.classList.remove('open');
  draw(); window.scrollTo({top: 0}); askOpening();
}
function render() {
  if (!S.user) return renderLogin();
  if (S.user.must_change) return renderChangePassword();
  clearInterval(S.timer);
  const header = h('header', {class: 'top'},
    h('div', {class: 'topbar'},
      h('a', {class: 'brand', href: BASE + '/'}, h('img', {src: '/alta/assets/logo.jpg', alt: ''}), h('span', {class: 'brand-name'}, 'TOP FITNESS', h('small', {}, 'CAJA'))),
      h('div', {class: 'daynav'},
        h('button', {onclick: () => shiftDay(-1), 'aria-label': 'Día anterior', title: 'Día anterior'}, '‹'),
        h('input', {type: 'date', value: S.day, 'data-daynav': 'date', onchange: e => { if (e.target.value) { S.day = e.target.value; load(); } }}),
        h('button', {onclick: () => shiftDay(1), 'aria-label': 'Día siguiente', title: 'Día siguiente'}, '›'),
        h('button', {class: S.day === S.today ? 'active' : '', 'data-daynav': 'today', onclick: () => { S.day = S.today; load(); }}, 'Hoy')),
      h('div', {class: 'who'}, h('span', {class: 'muted small'}, S.user.name),
        h('button', {class: 'small', onclick: async () => { await api('POST', '/logout'); S.user = null; render(); }}, 'Salir'))),
    h('div', {id: 'chips', class: 'chips'}),
    h('nav', {class: 'tabs', 'aria-label': 'Secciones'}, TABS.map(([k, t]) => h('button', {class: S.view === k ? 'active' : '', 'data-tab': k, onclick: () => go(k)}, t))));
  const side = h('aside', {id: 'side', class: 'side', 'aria-label': 'Calculadora'}, calculatorPanel());
  root.replaceChildren(header, h('div', {class: 'layout'}, h('main', {id: 'main'}, h('div', {class: 'skeleton'})), side),
    h('button', {class: 'fab', onclick: () => side.classList.toggle('open')}, 'Calculadora'));
  if (CLIENTS_ONLY) {
    viewCuotas(document.getElementById('main'));
    document.querySelector('.daynav').hidden = true;
    document.getElementById('chips').textContent = 'Consulta de socios · no abre la caja del día';
    return;
  }
  load();
  S.timer = setInterval(() => { load(true); recheckToday(); }, 20000);   // refresco periódico de datos ya en servidor
  askOpening();
}

// ---------------------------------------------------------------- dinero inicial de cada día (antes que nada, también tras las 00:00)
async function recheckToday() {
  if (!S.user || CLIENTS_ONLY) return;
  try {
    const r = await api('GET', '/me');
    // versión nueva en el servidor: la página se recarga sola cuando no hay nada sin guardar ni ventanas abiertas
    if (S.build && r.build && r.build !== S.build && !HJ.unsaved && !hjRows().some(x => x.retry) && !document.querySelector('.overlay')) { location.reload(); return; }
    Object.assign(S, {today: r.today, openingPending: r.opening_pending, lastCounted: r.last_counted, openingHour: r.opening_hour});
    askOpening();
  } catch (e) { /* sin conexión: se vuelve a comprobar en el siguiente ciclo */ }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) recheckToday(); });
function askOpening() {
  if (!S.user || S.user.must_change || SOLO || S.view !== 'hoja' || S.day !== S.today || !S.openingPending || S.openingOverlay || !(S.user.perms || []).includes('register')) return;
  const input = h('input', {inputmode: 'decimal', placeholder: 'Escribe lo que hay en caja (0 es válido)', autocomplete: 'off', 'aria-label': 'Dinero que hay en caja'});
  const msg = h('p', {class: 'err'});
  const last = S.lastCounted && S.lastCounted.counted != null
    ? h('p', {class: 'muted small'}, 'En el último cierre (' + fmtDay(S.lastCounted.day) + ') se contaron ' + euros(S.lastCounted.counted) + '.') : null;
  const btn = h('button', {class: 'primary'}, 'Guardar y empezar el día');
  const ov = h('div', {class: 'overlay', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Dinero inicial de caja'},
    h('div', {class: 'modal'},
      h('div', {class: 'head'}, h('h2', {}, 'Nuevo día · dinero que hay en caja'), h('button', {'aria-label': 'Consultar sin abrir caja', onclick: () => { done(); go('historico'); }}, '✕')),
      h('div', {class: 'body'},
        h('p', {}, 'Hoy es ' + fmtDay(S.today) + '. Cuenta el dinero que hay ahora mismo en la caja y escríbelo: será el dinero inicial de hoy y hará que la caja cuadre al cerrar.'),
        field('Dinero que hay en caja ahora (€)', input), last, msg),
      h('div', {class: 'foot'}, h('button', {onclick: () => { done(); go('historico'); }}, 'Solo consultar'), btn)));
  S.openingOverlay = ov;
  const done = () => { ov.remove(); S.openingOverlay = null; };
  async function save() {
    btn.disabled = true; msg.textContent = '';
    try {
      const c = parseCents(input.value);
      if (c == null) throw new Error('Escribe el dinero que hay en caja; escribe 0 si no hay.');
      await api('POST', '/day/' + S.today + '/opening', {opening: c});
      S.openingPending = false; done(); S.day = S.today;
      toast('Dinero inicial de hoy guardado: ' + euros(c)); render();
    } catch (e) {
      msg.textContent = e.message; btn.disabled = false;
      if (/Ya se indicó/.test(e.message)) { await recheckToday(); if (!S.openingPending) { done(); S.day = S.today; render(); } }
    }
  }
  btn.addEventListener('click', save);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') save(); });
  document.body.append(ov);
  setTimeout(() => input.focus(), 30);
}
function shiftDay(n) { const d = new Date(S.day + 'T12:00:00'); d.setDate(d.getDate() + n); S.day = d.toISOString().slice(0, 10); load(); }
// El selector de fecha y el botón «Hoy» se crean una sola vez en render(): hay que mantenerlos al día en cada cambio de día.
function syncDayNav() {
  const di = document.querySelector('[data-daynav="date"]'); if (di && di.value !== S.day) di.value = S.day;
  const tb = document.querySelector('[data-daynav="today"]'); if (tb) tb.classList.toggle('active', S.day === S.today);
}
async function load(quiet) {
  if (CLIENTS_ONLY) return;
  syncDayNav();
  try {
    const {day} = await api('GET', '/day/' + S.day);
    S.snap = day;
    drawChips();
    if (!quiet) draw();
    const stale = !day.refresh.updated || day.refresh.stale;
    if (!day.details.closed && day.bridge.pc_online && stale && Date.now() - S.lastRefreshAsk > 60000) {
      S.lastRefreshAsk = Date.now();
      api('POST', '/day/' + S.day + '/refresh', {}).then(r => waitJob(r.job_id, 60000)).then(() => load(true)).catch(() => {});
    }
  } catch (e) { if (!quiet) toast(e.message, true); }
}
function drawChips() {
  const b = S.snap.bridge, r = S.snap.refresh, el = document.getElementById('chips');
  if (!el) return;
  const pc = !b.paired ? ['PC sin vincular', 'bad'] : b.pc_online ? ['PC conectado', 'good'] : ['PC sin conexión · visto ' + (ago(b.last_seen) ? 'hace ' + ago(b.last_seen) : 'nunca'), 'bad'];
  const sql = b.last_sql_ok ? ['Última consulta SQL correcta: ' + fmtInstant(b.last_sql_ok), (Date.now() - new Date(b.last_sql_ok)) > 300000 ? 'old' : 'good'] : ['Sin consulta SQL correcta todavía', 'old'];
  const data = r.updated ? ['Datos del día: ' + fmtInstant(r.fetched || r.updated) + (r.stale ? ' (antiguos)' : ''), r.stale ? 'old' : 'good'] : ['Datos del día sin consultar', 'old'];
  const items = [pc, sql, data];
  if (r.error) items.push(['Última consulta con error: ' + r.error, 'bad']);
  el.replaceChildren(...items.map(([t, c]) => h('span', {class: 'chip ' + c}, t)));
}
function draw() {
  const main = document.getElementById('main');
  if (!main || !S.snap) return;
  if (S.view !== 'hoja') { clearInterval(HJ.timer); hjHideAc(); }
  ({hoja: viewHoja, historico: viewHistorico, cuotas: viewCuotas, mas: viewMas})[S.view](main);
}

// ---------------------------------------------------------------- calculadora (barra derecha) y atajos
function calculatorPanel() {
  const input = h('input', {class: 'calc-input', inputmode: 'decimal', placeholder: '0', autocomplete: 'off', 'aria-label': 'Operación'});
  const out = h('div', {class: 'calc-out', 'aria-live': 'polite'}, '0');
  const hist = h('div', {class: 'calc-hist'});
  const history = [];
  let timer, last = null;
  async function compute(commit) {
    const expr = input.value.trim();
    if (!expr) { out.textContent = '0'; last = null; return; }
    try {
      const r = await api('POST', '/calc', {expression: expr});
      last = r.result; out.textContent = last;
      if (commit) {
        history.unshift([expr, last]); history.splice(8);
        hist.replaceChildren(...history.map(([e, v]) => h('div', {onclick: () => { input.value = v; compute(false); }}, h('span', {}, e), h('b', {}, '= ' + v))));
        input.value = last;
      }
    } catch (e) { last = null; out.textContent = '…'; }
  }
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => compute(false), 220); });
  input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); compute(true); } });
  const press = k => {
    if (k === 'C') { input.value = ''; out.textContent = '0'; last = null; }
    else if (k === '⌫') { input.value = input.value.slice(0, -1); compute(false); }
    else if (k === '=') compute(true);
    else { input.value += k; compute(false); }
    input.focus();
  };
  const layout = [['7', '8', '9', '÷'], ['4', '5', '6', '×'], ['1', '2', '3', '−'], ['0', ',', '(', ')'], ['C', '⌫', '+', '=']];
  const keys = h('div', {class: 'keys'}, layout.flat().map(k => h('button', {class: /[÷×−+]/.test(k) ? 'op' : k === '=' ? 'eq' : '', onclick: () => press(k), 'aria-label': k}, k)));
  const useIt = () => {
    const t = S.amountTarget;
    if (!last) return toast('Calcula primero un resultado', true);
    if (!t || !document.body.contains(t)) { navigator.clipboard && navigator.clipboard.writeText(last).catch(() => {}); return toast('Copiado: ' + last + ' (no hay ningún importe abierto)'); }
    t.value = last; t.dispatchEvent(new Event('input', {bubbles: true})); toast('Pasado al importe: ' + last);
  };
  // Proporcional auxiliar: precio × días / días del mes (solo propone, editable)
  const price = h('input', {inputmode: 'decimal', placeholder: 'Precio mensual (€)'}), days = h('input', {inputmode: 'numeric', placeholder: 'Días restantes'});
  const dim = h('input', {inputmode: 'numeric', value: String(new Date(new Date(S.day + 'T12:00:00').getFullYear(), new Date(S.day + 'T12:00:00').getMonth() + 1, 0).getDate())});
  const prop = h('div', {class: 'ok'});
  const calcProp = () => {
    try { const p = parseCents(price.value), d = parseInt(days.value, 10), m = parseInt(dim.value, 10);
      if (p && d && m) { const c = Number((BigInt(p) * BigInt(d) * 2n + BigInt(m)) / (BigInt(m) * 2n)); prop.textContent = 'Propuesta: ' + euros(c); last = centsText(c); out.textContent = last; } else prop.textContent = '';
    } catch (e) { prop.textContent = e.message; }
  };
  [price, days, dim].forEach(i => i.addEventListener('input', calcProp));
  return h('div', {class: 'calc'}, h('h3', {}, 'Calculadora'), input, out, keys,
    h('div', {class: 'row2'}, h('button', {class: 'small', onclick: useIt}, '↳ Pasar al importe'), h('button', {class: 'small', onclick: () => { navigator.clipboard && navigator.clipboard.writeText(last || '').catch(() => {}); toast('Copiado'); }}, 'Copiar')),
    h('div', {class: 'calc-hist'}, hist),
    h('details', {}, h('summary', {}, 'Proporcional (propuesta)'), h('div', {class: 'row2'}, price, days), h('label', {}, 'Días del mes'), dim, prop),
    h('p', {class: 'hint'}, h('kbd', {}, 'C'), ' calculadora · ', h('kbd', {}, 'Esc'), ' cerrar · ', h('kbd', {}, 'Ctrl+Intro'), ' guardar'));
}
if (!window.__atajos) {
  window.__atajos = true;
  document.addEventListener('keydown', e => {
    const t = e.target, typing = t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName);
    if (e.key === 'Escape') { const ov = [...document.querySelectorAll('.overlay')].pop(); if (ov && !ov.classList.contains('locked')) ov.querySelector('.head button').click(); return; }
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { const b = document.querySelector('.overlay:last-of-type .foot .primary'); if (b && !b.disabled) { e.preventDefault(); b.click(); } return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey || !S.user || !S.snap || document.querySelector('.overlay')) return;
    const k = e.key.toLowerCase();

    if (k === 'c') { e.preventDefault(); const side = document.getElementById('side'); side.classList.add('open'); side.querySelector('.calc-input').focus(); }
    else if (k >= '1' && k <= String(TABS.length)) go(TABS[Number(k) - 1][0]);
  });
}

const WEEK = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
function madridTime(iso) { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleTimeString('es-ES', {timeZone: 'Europe/Madrid', hour: '2-digit', minute: '2-digit'}); }
// ---------------------------------------------------------------- billetes y monedas
const DEN = ['500', '200', '100', '50', '20', '10', '5', '2', '1', '0.50', '0.20', '0.10', '0.05', '0.02', '0.01'];
// ---------------------------------------------------------------- 4 · Cuotas (sin caja)
const Q = {client: null, info: null, history: null, limit: 100, seq: 0};
function viewCuotas(main) {
  const search = h('input', {placeholder: 'Buscar socio (mín. 2 letras o nº)', autocomplete: 'off'}), results = h('div', {class: 'list'}); results.hidden = true;
  let timer;
  search.addEventListener('input', () => {
    clearTimeout(timer);
    if (search.value.trim().length < 2) { results.hidden = true; return; }
    timer = setTimeout(async () => {
      const seq = ++Q.seq;
      try {
        const r = await api('POST', '/clients/search', {query: search.value.trim()}), job = await waitJob(r.job_id, 30000);
        if (seq !== Q.seq) return;
        results.hidden = false;
        results.replaceChildren(...(job && job.status === 'succeeded' ? job.result.clients.map(c => h('button', {onclick: () => pick(c)}, `${c.name} · nº ${c.number}`)) : [h('p', {class: 'warn small'}, 'Innux no responde ahora.')]));
      } catch (e) { toast(e.message, true); }
    }, 350);
  });
  main.replaceChildren(h('h1', {}, '4 · Administración de cuotas'), h('div', {class: 'note'}, 'Esto administra el derecho de acceso SIN CAJA: no crea ingresos, no cobra, no emite facturas.'),
    field('Socio', search), results, h('div', {id: 'qbody'}), h('h2', {}, 'Operaciones recientes'), h('div', {id: 'qops'}));
  if (Q.client) drawQuota();
  else {
    const p = new URLSearchParams(location.search), id = p.get('client'), number = p.get('number');
    if (/^[1-9][0-9]{0,19}$/.test(id || '') && /^[1-9][0-9]{0,19}$/.test(number || '')) pick({id, number, name: 'Socio nº ' + number});
  }
  api('GET', '/quotas/ops').then(r => { const el = document.getElementById('qops'); if (el) el.replaceChildren(h('table', {}, r.ops.map(o => h('tr', {}, h('td', {}, fmtInstant(o.created)), h('td', {}, o.action === 'activate' ? 'Activar' : 'Quitar'), h('td', {}, ({done:'Completado',succeeded:'Completado',failed:'No completado',queued:'Pendiente',running:'En curso',pending:'Pendiente',cancelled:'Cancelado'}[o.status] || 'En revisión')), h('td', {}, o.employee || ''), h('td', {class: 'err small'}, o.error || ''))))); }).catch(() => {});
}
async function pick(c) {
  const seq = ++Q.seq;
  Q.client = {client_id: String(c.id), number: String(c.number), name: c.name}; Q.info = null; Q.history = null; Q.limit = 100;
  drawQuota();
  try {
    const r = await api('POST', '/clients/get', {client_id: Q.client.client_id, number: Q.client.number}), job = await waitJob(r.job_id, 30000);
    if (seq !== Q.seq || !Q.client || Q.client.client_id !== String(c.id)) return;   // cambió de socio durante la lectura
    Q.info = job && job.status === 'succeeded' ? job.result : {error: job ? (job.error || {}).message : 'Innux no responde'};
    drawQuota();
  } catch (e) { toast(e.message, true); }
}
function drawQuota() {
  const el = document.getElementById('qbody'); if (!el || !Q.client) return;
  const info = Q.info;
  if (!info) return el.replaceChildren(h('p', {class: 'muted'}, `Cargando ficha de ${Q.client.name}…`));
  if (info.error) return el.replaceChildren(h('p', {class: 'err'}, info.error));
  el.replaceChildren(h('div', {class: 'panel'}, h('h2', {}, `${info.client.Nome} · nº ${info.client.Numero}`), h('p', {class: 'muted'}, info.client.Activo ? 'Ficha activa' : 'Ficha inactiva'),
    h('p', {}, `${info.cards.length} tarjeta(s), ${info.plans.length} tarifa(s).`),
    h('div', {class: 'row2'}, can('quotas') ? h('button', {class: 'primary', onclick: () => activateForm(info)}, 'Activar cuota (sin caja)') : null, h('button', {onclick: loadHistory}, 'Ver o quitar cuotas')),
    h('div', {id: 'qhist'})));
  if (Q.history) drawHistory();
}
async function loadHistory() {
  const seq = ++Q.seq, id = Q.client.client_id;
  const r = await api('POST', '/clients/history', {client_id: Q.client.client_id, number: Q.client.number, limit: Q.limit}), job = await waitJob(r.job_id, 40000);
  if (seq !== Q.seq || !Q.client || Q.client.client_id !== id) return;
  if (!job || job.status !== 'succeeded') return toast('No se pudo leer el historial ahora.', true);
  Q.history = job.result; drawHistory();
}
function drawHistory() {
  const el = document.getElementById('qhist'); if (!el) return;
  const q = Q.history.quotas;
  el.replaceChildren(h('div', {class: 'scroll'}, h('table', {}, h('thead', {}, h('tr', {}, ['Desde', 'Hasta', 'Plan', 'Valor', 'Pagada', ''].map(t => h('th', {}, t)))), h('tbody', {}, q.map(r => h('tr', {},
    h('td', {}, fmtDay(String(r.ValidadeInicio || '').slice(0, 10))), h('td', {}, fmtDay(String(r.ValidadeFim || '').slice(0, 10))), h('td', {}, r.PlanDescripcion || ''), h('td', {}, r.Valor != null ? euros(parseCents(r.Valor)) : ''), h('td', {}, r.Pago ? 'Sí' : 'No'),
    h('td', {}, can('quotas_delete') && r.removable ? h('button', {class: 'danger', onclick: () => removeForm(r)}, 'Quitar') : null)))))),
    Q.history.has_more ? h('button', {onclick: async () => { Q.limit = Math.min(1000, Q.limit * 2); await loadHistory(); }}, 'Cargar anteriores') : null);
}
function activateForm(info) {
  const card = h('select', {}, info.cards.map(c => h('option', {value: String(c.IDCartao)}, `Tarjeta ${c.IDCartao} · ${c.PlanDescripcion || 'sin plan'}${c.Activo ? '' : ' (inactiva)'}`)));
  const plan = h('select', {}, info.plans.map(p => h('option', {value: String(p.IDPlanoPagamento)}, `${p.Descricao} · ${p.FixoValorQuota} €`)));
  const method = h('select', {}, h('option', {value: 'EFECTIVO'}, 'EFECTIVO'), h('option', {value: 'DOMICILIACIÓN BANCARIA'}, 'DOMICILIACIÓN BANCARIA'));
  const [a, b] = monthRange(S.today);
  const amount = h('input', {value: '0,00', inputmode: 'decimal'}), vf = h('input', {type: 'date', value: a}), vu = h('input', {type: 'date', value: b});
  const emp = employeeSelect(S.lastEmployee), ok = h('input', {type: 'checkbox'}), msg = h('p', {class: 'err'});
  const rid = uuid();
  plan.addEventListener('change', () => { const p = info.plans.find(x => String(x.IDPlanoPagamento) === plan.value); if (p) amount.value = String(p.FixoValorQuota).replace('.', ','); });
  if (info.plans[0]) amount.value = String(info.plans[0].FixoValorQuota).replace('.', ',');
  modal('Activar cuota SIN CAJA', h('div', {}, field('Tarjeta', card), field('Tarifa', plan), field('Método', method), field('Importe (€, puede ser 0)', amount), h('div', {class: 'row2'}, field('Inicio', vf), field('Fin', vu)), field('Empleado', emp),
    h('label', {class: 'check'}, ok, 'Confirmo: activar la cuota SIN CAJA (no cobra, no crea ingreso ni factura)'), msg),
    close => [h('button', {onclick: close}, 'Cancelar'), h('button', {class: 'primary', onclick: async ev => {
      const btn = ev.currentTarget; btn.disabled = true;
      try {
        const r = await api('POST', '/quotas/activate', {request_id: rid, client_id: Q.client.client_id, number: Q.client.number, card_id: card.value, plan_id: plan.value, quota_cents: parseCents(amount.value),
          valid_from: vf.value, valid_until: vu.value, employee: emp.get(), payment_method: method.value, confirm: ok.checked});
        close(); toast('Enviado al PC…'); const job = await waitJob(r.request_id, 45000);
        toast(!job ? 'Sigue pendiente en el PC; no se repite.' : job.status === 'succeeded' ? 'Cuota activada' : 'No se completó: ' + ((job.error || {}).message || job.status), !job || job.status !== 'succeeded'); viewCuotas(document.getElementById('main'));
      } catch (e) { msg.textContent = e.message; btn.disabled = false; } }}, 'Activar')]);
}
function removeForm(row) {
  const emp = employeeSelect(S.lastEmployee), ok = h('input', {type: 'checkbox'}), msg = h('p', {class: 'err'}), rid = uuid();
  modal('Quitar cuota', h('div', {}, h('p', {class: 'warn'}, `Se borra SOLO la fila de cuota (${fmtDay(String(row.ValidadeInicio).slice(0, 10))} → ${fmtDay(String(row.ValidadeFim).slice(0, 10))}). No anula facturas ni devuelve dinero; el cobro ya registrado en caja se conserva.`),
    field('Empleado', emp), h('label', {class: 'check'}, ok, 'Confirmo quitar esta cuota'), msg),
    close => [h('button', {onclick: close}, 'Cancelar'), h('button', {class: 'danger', onclick: async ev => {
      const btn = ev.currentTarget; btn.disabled = true;
      try {
        const r = await api('POST', '/quotas/remove', {request_id: rid, client_id: Q.client.client_id, number: Q.client.number, card_id: String(row.IDCartao), quota_id: String(row.IDCartaoQuota), signature: row.signature, employee: emp.get(), confirm: ok.checked, row});
        close(); toast('Enviado al PC…'); const job = await waitJob(r.request_id, 45000);
        toast(!job ? 'Sigue pendiente en el PC.' : job.status === 'succeeded' ? 'Cuota quitada' : 'No se completó: ' + ((job.error || {}).message || job.status) + ' (recarga el historial)', !job || job.status !== 'succeeded');
        Q.history = null; loadHistory();
      } catch (e) { msg.textContent = e.message; btn.disabled = false; } }}, 'Quitar')]);
}

// ---------------------------------------------------------------- Diario (rejilla como el Excel «Diario de Caja»)
// Una fila por apunte, importe con signo, se guarda celda a celda. Es un registro propio: no cambia Caja ni los cierres.
const HJ = {day: null, data: null, q: Promise.resolve(), unsaved: 0, timer: null, lastRefresh: 0, live: {total: 0, expected: 0}, seq: 0, tabbing: false, keep: false, ac: null, bar: null, tbody: null, stateEl: null, hintsEl: null};
const HJ_COLS = ['cents', 'concept', 'name', 'number', 'employee', 'notes'];
const HJ_TITLES = ['efectivo', 'concepto', 'nombre', 'nº socio', 'gestionado por', 'NOTAS'];
const normTxt = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
function lev(a, b) {
  const d = Array.from({length: a.length + 1}, (_, i) => [i]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
}
// Importe con signo: «39,9», «-30», «+5». Sumas y restas se hacen en la calculadora.
function parseSigned(text) {
  let t = String(text == null ? '' : text).trim().replace(/[€\s]/g, '').replace('−', '-');
  if (!t) return null;
  if (/[*\/x×÷]|.[+-]/.test(t)) throw new Error('Para sumar o restar importes usa la calculadora y apunta aquí solo el resultado.');
  const neg = t[0] === '-';
  if (neg || t[0] === '+') t = t.slice(1);
  const c = parseCents(t);
  return c == null ? null : (neg ? -c : c);
}
const hjShift = () => { try { return localStorage.getItem('hoja_turno') || ''; } catch (e) { return ''; } };
const hjIsOut = text => { const q = normTxt(text), c = HJ.data.concepts.find(c => normTxt(c.text) === q); return !!(c && c.out); };
// Lo que se va proponiendo al escribir el concepto. Todo lo que empieza por «ren» es siempre renovación.
function hjMatches(text) {
  const q0 = normTxt(text); if (!q0) return [];
  const q = /^ren[a-zñ]*$/.test(q0) ? 'renovacion' : q0, list = HJ.data.concepts;
  const starts = list.filter(c => normTxt(c.text).startsWith(q));
  return starts.concat(list.filter(c => !starts.includes(c) && normTxt(c.text).includes(q))).slice(0, 8);
}
// Al salir de la celda: corrige a la forma de siempre («reno», «renoevacion», «pase dia»…) y propone precio.
function hjResolve(text) {
  const raw = String(text || '').replace(/\s+/g, ' ').trim(); if (!raw) return null;
  const q = normTxt(raw), list = HJ.data.concepts, find = t => list.find(c => normTxt(c.text) === normTxt(t));
  let hit = find(raw), m;
  if (!hit && (m = q.match(/^ren[a-zñ]*\s*(?:\+|y|mas)?\s*(\d)\s*mant\w*$/))) hit = find('renovacion + ' + m[1] + ' mant');
  if (!hit && /^ren[a-zñ]*$/.test(q)) hit = find('renovacion');
  if (!hit && /^pase(\s+(de\s+)?dia(rio)?)?$/.test(q)) hit = find('pase de dia');
  if (!hit && /^ren[a-zñ]*\W/.test(q + ' ')) return {text: raw.replace(/^ren[a-zñ]*/i, 'renovacion'), cents: null, out: false};
  if (!hit) { const s = list.filter(c => normTxt(c.text).startsWith(q)); if (s.length === 1) hit = s[0]; }
  if (!hit && q.length >= 4 && !q.includes(' ')) { const s = list.filter(c => !c.text.includes(' ') && lev(q, c.text) <= 1); if (s.length === 1) hit = s[0]; }
  return hit ? {text: hit.text, cents: hit.cents, out: hit.out} : {text: raw, cents: null, out: false};
}
const hjRows = () => HJ.tbody ? [...HJ.tbody.children].map(tr => tr._r).filter(Boolean) : [];
const hjHasData = r => ['cents', 'concept', 'name', 'number', 'notes'].some(c => r.inputs[c].value.trim());
function hjLive(r) {   // importe tal como está escrito ahora mismo (para el total en directo)
  try { let c = parseSigned(r.inputs.cents.value); if (c != null && c > 0 && hjIsOut(r.inputs.concept.value)) c = -c; return c; } catch (e) { return null; }
}
function hjPaint(r) {
  const c = hjLive(r), el = r.inputs.cents;
  el.classList.toggle('pos', c != null && c > 0); el.classList.toggle('neg', c != null && c < 0);
}
function hjState() {
  if (!HJ.stateEl) return;
  const failed = hjRows().some(r => r.retry);
  HJ.stateEl.className = 'small linklike ' + (failed ? 'err' : HJ.unsaved ? 'warn' : 'ok');
  HJ.stateEl.textContent = failed ? '⚠ Hay cambios sin guardar · pulsa para reintentar' : HJ.unsaved ? 'Guardando…' : '✓ Todo guardado';
}
function hjRenumber() {
  hjRows().forEach((r, i) => { r.num.textContent = String(i + 1) + (r.hint ? ' ⚠' : ''); r.num.title = r.hint || ''; r.num.classList.toggle('warn', !!r.hint); });
  if (!HJ.hintsEl) return;
  const hints = hjRows().map((r, i) => r.hint ? h('li', {}, 'Fila ' + (i + 1) + ': ' + r.hint) : null).filter(Boolean);
  HJ.hintsEl.replaceChildren(...hints); HJ.hintsEl.hidden = !hints.length;
}
function hjUpdateBar() {
  const b = HJ.bar; if (!b) return;
  let entries = 0, exits = 0, n = 0;
  for (const r of hjRows()) { const c = hjLive(r); if (c == null) continue; n++; if (c > 0) entries += c; else exits -= c; }
  const total = entries - exits, expected = (HJ.data.opening || 0) + total;
  b.total.textContent = euros(total); b.total.classList.toggle('err', total < 0);
  b.entries.textContent = euros(entries); b.exits.textContent = euros(-exits); b.count.textContent = String(n);
  b.opening.textContent = HJ.data.opening_confirmed ? euros(HJ.data.opening || 0) : 'sin indicar'; b.expected.textContent = euros(expected);
  HJ.live = {total, entries, expected};
}
function hjAddRow(src, before) {
  const ed = HJ.data.editable, r = {id: src ? src.id : uuid(), pos: src ? src.pos : null, saved: !!src, dirty: 0, retry: null, hint: src ? src.hint : null, srv: {}, vals: {}, inputs: {}};
  r.tr = h('tr', {class: 'hrow' + (src && src.source ? ' innux' : '')}); r.tr._r = r;
  r.num = h('td', {class: 'hn'}); r.time = h('td', {class: 'ht muted small'}, src ? madridTime(src.created) : '');
  r.tr.append(r.num);
  HJ_COLS.forEach((col, ci) => {
    const el = h('input', {class: 'cell c-' + col, 'data-col': col, autocomplete: 'off', spellcheck: 'false', 'aria-label': HJ_TITLES[ci], inputmode: col === 'cents' ? 'decimal' : false, readonly: !ed, list: col === 'employee' ? 'hoja-emp' : false});
    const v = src ? src[col] : (col === 'employee' ? hjShift() : null);
    r.vals[col] = col === 'cents' ? (v == null ? null : v) : (v || '');
    if (src) r.srv[col] = col === 'cents' ? v : (v || '');
    el.value = col === 'cents' ? centsText(v) : (v || '');
    el.addEventListener('keydown', e => hjKey(e, r, col, ci));
    el.addEventListener('input', () => hjInput(r, col));
    el.addEventListener('focus', () => {
      if (!HJ.tabbing && !HJ.keep) HJ.seq = ci;
      HJ.tabbing = false;
      if (col === 'cents') S.amountTarget = el;   // «↳ Pasar al importe» de la calculadora escribe aquí
    });
    el.addEventListener('focusout', () => hjCommit(r, col));
    r.inputs[col] = el; r.tr.append(h('td', {class: 'hc c-' + col}, el));
  });
  r.tr.append(r.time, h('td', {class: 'hx'}, ed ? h('button', {class: 'small', tabindex: '-1', title: 'Eliminar fila', 'aria-label': 'Eliminar fila', onclick: () => hjDelete(r)}, '✕') : null));
  if (before) HJ.tbody.insertBefore(r.tr, before); else HJ.tbody.append(r.tr);
  hjPaint(r); hjRenumber();
  return r;
}
function hjEnsureBlank() {
  if (!HJ.data.editable) return;
  const rows = hjRows(), last = rows[rows.length - 1];
  if (!last || hjHasData(last)) hjAddRow(null);
}
function hjFocus(ri, ci, keep) {
  let rows = hjRows();
  if (ri < 0) return;
  if (ri >= rows.length) { hjEnsureBlank(); rows = hjRows(); if (ri >= rows.length) return; }
  const el = rows[ri].inputs[HJ_COLS[ci]];
  HJ.keep = !!keep; el.focus(); HJ.keep = false; el.select();
}
function hjKey(e, r, col, ci) {
  const el = e.target, ac = HJ.ac;
  if (col === 'concept' && ac && ac.el === el && ac.items.length) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { ac.i = (ac.i + (e.key === 'ArrowDown' ? 1 : ac.items.length - 1)) % ac.items.length; hjPaintAc(); return e.preventDefault(); }
    if (e.key === 'Escape') { hjHideAc(); return e.preventDefault(); }
    if ((e.key === 'Enter' || e.key === 'Tab') && !e.shiftKey) el.value = ac.items[ac.i].text;   // acepta la sugerencia marcada
  }
  const ri = hjRows().indexOf(r);
  if (e.key === 'Enter') { e.preventDefault(); hjCommit(r, col); hjFocus(ri + 1, HJ.seq, true); }
  else if (e.key === 'Tab' && !e.shiftKey) { if (ci === HJ_COLS.length - 1) { e.preventDefault(); hjCommit(r, col); hjFocus(ri + 1, 0, true); } else HJ.tabbing = true; }
  else if (e.key === 'Tab' && ci === 0 && ri > 0) { e.preventDefault(); hjFocus(ri - 1, HJ_COLS.length - 1); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); hjFocus(ri + 1, ci); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); hjFocus(ri - 1, ci); }
  else if (e.key === 'ArrowLeft' && ci > 0 && el.selectionStart === 0 && el.selectionEnd === 0) { e.preventDefault(); hjFocus(ri, ci - 1); }
  else if (e.key === 'ArrowRight' && ci < HJ_COLS.length - 1 && el.selectionStart === el.value.length && el.selectionEnd === el.value.length) { e.preventDefault(); hjFocus(ri, ci + 1); }
}
function hjInput(r, col) {
  if (col === 'cents' || col === 'concept') hjPaint(r);
  if (col === 'concept') hjShowAc(r);
  if (col === 'cents') { r.inputs.cents.classList.remove('bad'); hjUpdateBar(); if (document.activeElement !== r.inputs.cents) hjCommit(r, 'cents'); }   // p. ej. desde la calculadora
  hjEnsureBlank();
}
function hjCommit(r, col) {
  const el = r.inputs[col], fields = {};
  if (col === 'concept') hjHideAc();
  const setAmount = c => { r.inputs.cents.value = centsText(c); r.inputs.cents.classList.remove('bad'); if (r.vals.cents !== c) { r.vals.cents = c; fields.cents = c; } };
  let value;
  if (col === 'cents') {
    try { value = parseSigned(el.value); } catch (e) { el.classList.add('bad'); toast(e.message, true); return; }
    if (value != null && value > 0 && hjIsOut(r.inputs.concept.value)) value = -value;   // yoga, ciclo… son salidas
    el.value = centsText(value); el.classList.remove('bad');
  } else if (col === 'concept') {
    const res = hjResolve(el.value); value = res ? res.text : ''; el.value = value;
    if (res && res.cents != null && !r.inputs.cents.value.trim()) setAmount(res.out ? -res.cents : res.cents);   // propone el precio habitual
    else if (res && res.out && r.vals.cents > 0) setAmount(-r.vals.cents);
  } else { value = col === 'notes' ? el.value.trim() : el.value.replace(/\s+/g, ' ').trim(); el.value = value; }
  if (r.vals[col] !== value) { r.vals[col] = value; fields[col] = value; }
  hjPaint(r); hjUpdateBar();
  if (Object.keys(fields).length && HJ.data.editable) hjSave(r, fields);
  hjEnsureBlank();
}
function hjSave(r, fields) {
  if (!r.saved) fields = Object.assign(Object.fromEntries(HJ_COLS.filter(c => r.vals[c] != null && r.vals[c] !== '').map(c => [c, r.vals[c]])), fields);
  if (r.retry) { fields = Object.assign({}, r.retry, fields); r.retry = null; }
  const day = HJ.day;
  r.dirty++; HJ.unsaved++; hjState();
  HJ.q = HJ.q.then(async () => {
    try {
      const res = await api('POST', '/hoja/' + day + '/row', {id: r.id, fields});
      r.saved = true; r.pos = res.row.pos; Object.assign(r.srv, fields); r.hint = res.row.hint;
      r.time.textContent = madridTime(res.row.created); r.tr.classList.remove('unsaved', 'badrow'); hjRenumber();
    } catch (e) {
      if (!e.status || e.status >= 500) { r.retry = Object.assign(r.retry || {}, fields); r.tr.classList.add('unsaved'); toast('No se pudo guardar (se reintentará): ' + e.message, true); }
      else { r.tr.classList.add('badrow'); toast(e.message, true); }
    } finally { r.dirty--; HJ.unsaved--; hjState(); }
  });
}
function hjRetryAll() { hjRows().filter(r => r.retry).forEach(r => hjSave(r, {})); }
function hjDelete(r) {
  if (!hjHasData(r) && !r.saved) return;
  const what = [r.inputs.cents.value, r.inputs.concept.value, r.inputs.name.value].filter(Boolean).join(' · ') || 'fila vacía';
  modal('Eliminar fila', h('p', {}, '¿Eliminar «' + what + '»? Queda anotado en el registro de cambios.'), close => [
    h('button', {onclick: close}, 'Cancelar'),
    h('button', {class: 'danger', onclick: async () => {
      try { await HJ.q; if (r.saved) await api('POST', '/hoja/' + HJ.day + '/row/' + r.id + '/void', {}); r.tr.remove(); hjEnsureBlank(); hjRenumber(); hjUpdateBar(); close(); }
      catch (e) { toast(e.message, true); }
    }}, 'Eliminar')]);
}
// ---- autocompletado del concepto
function hjHideAc() { if (HJ.ac) { HJ.ac.box.remove(); HJ.ac = null; } }
function hjShowAc(r) {
  const el = r.inputs.concept, items = hjMatches(el.value);
  if (!items.length || document.activeElement !== el) return hjHideAc();
  if (!HJ.ac || HJ.ac.el !== el) { hjHideAc(); const box = h('div', {class: 'ac', role: 'listbox'}); document.body.append(box); HJ.ac = {el, r, box, items, i: 0}; }
  HJ.ac.items = items; HJ.ac.i = 0;
  const b = el.getBoundingClientRect(), box = HJ.ac.box;
  box.style.left = b.left + 'px'; box.style.minWidth = Math.max(240, b.width) + 'px';
  if (b.bottom + 270 > innerHeight && b.top > 270) { box.style.top = 'auto'; box.style.bottom = (innerHeight - b.top) + 'px'; } else { box.style.bottom = 'auto'; box.style.top = b.bottom + 'px'; }
  hjPaintAc();
}
function hjPaintAc() {
  const ac = HJ.ac; if (!ac) return;
  ac.box.replaceChildren(...ac.items.map((c, i) => h('div', {class: i === ac.i ? 'on' : '', role: 'option', onmousedown: e => {
    e.preventDefault(); ac.el.value = c.text; hjCommit(ac.r, 'concept'); hjFocus(hjRows().indexOf(ac.r), 2, true);
  }}, h('span', {}, c.text), h('b', {}, c.cents != null ? euros(c.out ? -c.cents : c.cents) : ''))));
}
window.addEventListener('scroll', () => hjHideAc(), true);
window.addEventListener('beforeunload', e => { if (HJ.unsaved || hjRows().some(r => r.retry)) { e.preventDefault(); e.returnValue = ''; } });

// ---- sincronización con otros ordenadores y con Innux (cada pocos segundos, sin pisar lo que se está escribiendo)
function hjSync(d) {
  const before = HJ.data, changedState = d.closed !== before.closed || d.editable !== before.editable;
  Object.assign(before, {shifts: d.shifts, unclosed: d.unclosed, closed: d.closed, closure: d.closure, opening: d.opening, opening_confirmed: d.opening_confirmed,
                         editable: d.editable, concepts: d.concepts, employees: d.employees, can_close: d.can_close, can_reopen: d.can_reopen});
  if (changedState) return viewHoja(document.getElementById('main'));   // otro ordenador cerró o reabrió el día
  const byId = new Map(hjRows().map(r => [r.id, r])), busy = r => r.dirty || r.retry || r.tr.contains(document.activeElement);
  d.rows.forEach(src => {
    const r = byId.get(src.id);
    if (!r) {
      const next = hjRows().find(x => !x.saved || (x.pos != null && x.pos > src.pos));
      hjAddRow(src, next ? next.tr : null); return;
    }
    if (busy(r)) return;
    HJ_COLS.forEach(col => {
      const v = col === 'cents' ? src[col] : (src[col] || '');
      if (r.srv[col] !== v) { r.srv[col] = v; r.vals[col] = v; r.inputs[col].value = col === 'cents' ? centsText(v) : v; }
    });
    r.hint = src.hint; r.pos = src.pos; hjPaint(r);
  });
  const ids = new Set(d.rows.map(s => s.id));
  hjRows().filter(r => r.saved && !ids.has(r.id) && !busy(r)).forEach(r => r.tr.remove());
  hjEnsureBlank(); hjRenumber(); hjDrawShifts(); hjUpdateBar(); hjDrawActions();
}
async function hjPoll() {
  if (document.hidden || S.view !== 'hoja' || HJ.day !== S.day || HJ.unsaved || !HJ.data) return;
  if (HJ.day === S.today && !HJ.data.closed && Date.now() - HJ.lastRefresh > 60000 && S.snap && S.snap.bridge && S.snap.bridge.pc_online) {
    HJ.lastRefresh = Date.now();   // pide a Innux los cobros de hoy una vez por minuto; entran solos en la rejilla
    api('POST', '/day/' + HJ.day + '/refresh', {}).catch(() => {});
  }
  try {
    const d = (await api('GET', '/hoja/' + HJ.day)).hoja;
    if (S.view === 'hoja' && HJ.day === d.day && !HJ.unsaved) hjSync(d);
  } catch (e) { /* sin conexión: se vuelve a intentar */ }
}
async function hjFlush() { await HJ.q; hjRetryAll(); await HJ.q; }
async function hjReload() { const d = (await api('GET', '/hoja/' + HJ.day)).hoja; hjSync(d); }

// ---- cierres de turno: una marca en la rejilla donde terminó cada turno
function hjDrawShifts() {
  HJ.tbody.querySelectorAll('tr.shiftrow').forEach(tr => tr.remove());
  const rows = hjRows(), tail = new Map();
  for (const s of HJ.data.shifts) {
    const after = rows.filter(r => r.saved && r.pos != null && r.pos <= s.after_pos).pop(), key = after ? after.id : 'top', diff = s.counted - s.expected;
    const tr = h('tr', {class: 'shiftrow ' + (s.status === 'ok' ? 'good' : 'bad')}, h('td', {colspan: '9'},
      h('b', {}, s.status === 'ok' ? '✔ Cierre de turno OK' : '✖ Turno: no cuadra'), ' · ' + s.employee + ' · ' + madridTime(s.created) + ' · contado ' + euros(s.counted) + ' · esperado ' + euros(s.expected) +
      (diff ? ' · diferencia ' + (diff > 0 ? '+' : '') + euros(diff) : '') + (s.note ? ' · ' + s.note : '')));
    const anchor = tail.get(key) || (after ? after.tr : null);
    if (anchor) anchor.after(tr); else HJ.tbody.prepend(tr);
    tail.set(key, tr);
  }
}
function hjEmployeeInput(selected) {
  return h('input', {list: 'hoja-emp', value: selected || '', placeholder: 'Quién eres', autocomplete: 'off', 'aria-label': 'Quién cierra'});
}
function hjDrawActions() {
  const b = HJ.bar, d = HJ.data; if (!b) return;
  const last = d.shifts[d.shifts.length - 1], ed = d.editable;
  const parts = [];
  if (d.closed) parts.push(h('span', {class: 'warn'}, '🔒 Día cerrado' + (d.closure ? ' por ' + d.closure.actor + ' · ' + fmtInstant(d.closure.created) + (d.closure.version > 1 ? ' (versión ' + d.closure.version + ')' : '') : '') + '. Para cambiar algo hay que reabrirlo.'));
  if (d.closure_history && d.closure_history.length > (d.closed ? 1 : 0))
    parts.push(h('span', {class: 'muted small', 'data-closure-history': ''}, 'Cierres anteriores: ' + d.closure_history.slice(0, d.closed ? -1 : undefined).map(c => 'v' + c.version + ' ' + fmtInstant(c.created) + ' (' + c.actor + ')').join(' · ')));
  else if (!last) parts.push(h('span', {class: 'muted'}, 'Ningún turno cerrado todavía. Al acabar tu turno pulsa «Cerrar turno».'));
  else {
    parts.push(h('span', {class: last.status === 'ok' ? 'ok' : 'err'}, (last.status === 'ok' ? '✔ Último turno cerrado' : '✖ Último turno: no cuadra') + ' · ' + last.employee + ' · ' + madridTime(last.created)));
    if (d.unclosed) parts.push(h('div', {class: 'warn small'}, 'Hay apuntes nuevos o cambiados desde el último cierre de turno.'));
  }
  b.status.replaceChildren(...parts);
  b.shift.hidden = d.closed; b.shift.disabled = !ed;
  b.undo.hidden = d.closed || !last; b.undo.disabled = !ed;
  b.close.hidden = d.closed || !d.can_close;
  b.close.disabled = !ed || !last || d.unclosed;
  b.close.title = !last ? 'Antes hay que cerrar el turno' : d.unclosed ? 'Hay apuntes después del último cierre de turno: cierra el turno otra vez' : '';
  b.reopen.hidden = !d.closed || !d.can_reopen;
}
function hjShiftModal() {
  const d = HJ.data, expected = HJ.live.expected;
  const emp = hjEmployeeInput(hjShift() || S.lastEmployee);
  const counted = h('input', {inputmode: 'decimal', placeholder: '0,00', 'aria-label': 'Efectivo contado en caja'});
  const note = h('textarea', {placeholder: 'Solo si no cuadra: qué falta o qué sobra', maxlength: '1000'});
  const info = h('p', {class: 'muted'}), warn = h('p', {class: 'warn'});
  const coins = DEN.map(x => h('input', {inputmode: 'numeric', 'data-d': x, placeholder: '0', 'aria-label': x + ' €'}));
  const coinMap = () => Object.fromEntries(coins.map(i => [i.dataset.d, parseInt(i.value || '0', 10) || 0]).filter(([, n]) => n > 0));
  let confirmed = false;
  const value = () => { try { return parseCents(counted.value); } catch (e) { return null; } };
  const refresh = () => {
    confirmed = false; warn.textContent = '';
    const c = value();
    info.textContent = 'Debería haber ' + euros(expected) + ' (fondo ' + (d.opening_confirmed ? euros(d.opening) : 'sin indicar') + ' + total ' + euros(HJ.live.total) + ')' +
      (c == null ? '' : ' · contado ' + euros(c) + ' · ' + (c === expected ? 'cuadra ✓' : 'diferencia ' + (c > expected ? '+' : '') + euros(c - expected)));
  };
  counted.addEventListener('input', refresh);
  coins.forEach(i => i.addEventListener('input', () => {
    counted.value = centsText(coins.reduce((a, x) => a + Math.round(parseFloat(x.dataset.d) * 100) * (parseInt(x.value || '0', 10) || 0), 0)); refresh();
  }));
  refresh();
  const send = async (status, close) => {
    const c = value(), who = emp.value.trim();
    if (!who) return toast('Indica quién cierra el turno', true);
    if (c == null) return toast('Escribe el efectivo contado (0 si no hay)', true);
    if (status === 'revisar' && !note.value.trim()) return toast('Explica qué no cuadra', true);
    if (status === 'ok' && c !== expected && !confirmed) { confirmed = true; warn.textContent = 'No coincide con lo esperado. Si es correcto, pulsa «Cierre OK» otra vez.'; return; }
    try {
      await hjFlush();
      await api('POST', '/hoja/' + HJ.day + '/shift', {employee: who, status, counted: c, note: note.value.trim(), coins: coinMap()});
      try { localStorage.setItem('hoja_turno', who); } catch (e) { /* sin almacenamiento */ }
      close(); toast(status === 'ok' ? 'Turno cerrado: OK' : 'Turno marcado: no cuadra'); await hjReload();
    } catch (e) { toast(e.message, true); }
  };
  modal('Cerrar turno', h('div', {}, field('Quién cierra', emp), field('Efectivo contado en caja (€)', counted), info,
    h('details', {}, h('summary', {class: 'muted'}, 'Contar billetes y monedas'), h('div', {class: 'denoms'}, DEN.map((x, i) => h('div', {}, h('label', {}, x + ' €'), coins[i])))),
    field('Nota', note), warn),
  close => [h('button', {onclick: close}, 'Cancelar'), h('button', {class: 'danger', onclick: () => send('revisar', close)}, '✖ No cuadra'), h('button', {class: 'primary', onclick: () => send('ok', close)}, '✔ Cierre OK')]);
}
function hjUndoShift() {
  const last = HJ.data.shifts[HJ.data.shifts.length - 1]; if (!last) return;
  modal('Deshacer el último cierre de turno', h('p', {}, 'Se quita la marca de ' + last.employee + ' (' + madridTime(last.created) + '). Queda anotado en el registro de cambios.'), close => [
    h('button', {onclick: close}, 'Cancelar'),
    h('button', {class: 'danger', onclick: async () => { try { await api('POST', '/hoja/' + HJ.day + '/shift/' + last.id + '/undo', {}); close(); await hjReload(); } catch (e) { toast(e.message, true); } }}, 'Deshacer')]);
}

// ---- cierre definitivo del día (exige el último turno cerrado)
function hjCloseModal() {
  const d = HJ.data, last = d.shifts[d.shifts.length - 1];
  const emp = hjEmployeeInput(hjShift() || S.lastEmployee), note = h('textarea', {placeholder: 'Opcional', maxlength: '1000'});
  const opening = d.opening_confirmed ? null : h('input', {inputmode: 'decimal', placeholder: '0,00', 'aria-label': 'Dinero inicial'});
  modal('Cerrar la caja del día', h('div', {}, h('p', {}, 'Se guarda una copia que ya no se puede cambiar y el día queda bloqueado. Solo un responsable puede reabrirlo.'),
    h('div', {class: 'grid'}, h('div', {class: 'stat key'}, h('span', {}, 'Total del día'), h('b', {}, euros(HJ.live.total))), h('div', {class: 'stat'}, h('span', {}, 'Turnos cerrados'), h('b', {}, String(d.shifts.length)))),
    last && last.status === 'revisar' ? h('div', {class: 'note bad'}, 'El último turno está marcado «no cuadra»: ' + last.note) : null,
    opening ? field('Dinero que había en caja al empezar el día (€)', opening) : null, field('Quién cierra', emp), field('Nota', note)),
  close => [h('button', {onclick: close}, 'Cancelar'), h('button', {class: 'primary', onclick: async () => {
    const who = emp.value.trim(); if (!who) return toast('Indica quién cierra', true);
    let o = null; try { o = opening ? parseCents(opening.value) : null; } catch (e) { return toast(e.message, true); }
    if (opening && o == null) return toast('Indica el dinero inicial (0 si no había)', true);
    try {
      await hjFlush();
      const r = await api('POST', '/hoja/' + HJ.day + '/close', {employee: who, note: note.value.trim(), opening: o});
      close(); toast(r.report_error ? 'Caja cerrada (el Excel del mes no se pudo generar)' : 'Caja del día cerrada'); await hjReload();
    } catch (e) { toast(e.message, true); }
  }}, 'Cerrar caja')]);
}
function hjReopenModal() {
  const emp = hjEmployeeInput(hjShift() || S.lastEmployee), reason = h('textarea', {placeholder: 'Por qué se reabre', maxlength: '500'});
  modal('Reabrir el día', h('div', {}, field('Quién reabre', emp), field('Motivo', reason)), close => [
    h('button', {onclick: close}, 'Cancelar'),
    h('button', {class: 'danger', onclick: async () => {
      if (!emp.value.trim() || !reason.value.trim()) return toast('Indica quién reabre y el motivo', true);
      try { await api('POST', '/hoja/' + HJ.day + '/reopen', {employee: emp.value.trim(), reason: reason.value.trim()}); close(); toast('Día reabierto'); await hjReload(); }
      catch (e) { toast(e.message, true); }
    }}, 'Reabrir')]);
}

// ---- la pantalla
async function viewHoja(main) {
  clearInterval(HJ.timer); hjHideAc();
  const day = S.day;
  main.replaceChildren(h('div', {class: 'skeleton'}));
  let data;
  try { data = (await api('GET', '/hoja/' + day)).hoja; } catch (e) { return main.replaceChildren(h('p', {class: 'err'}, e.message)); }
  if (S.view !== 'hoja' || S.day !== day) return;
  HJ.day = day; HJ.data = data; HJ.live = {total: 0, expected: 0};
  HJ.tbody = h('tbody', {}); HJ.seq = 0; HJ.lastRefresh = Date.now();
  HJ.stateEl = h('button', {class: 'small linklike ok', onclick: hjRetryAll}, '✓ Todo guardado');
  HJ.hintsEl = h('ul', {class: 'note hints', hidden: true});
  const ed = data.editable;
  const turno = h('select', {'aria-label': 'Turno: quién apunta', onchange: e => {
    try { localStorage.setItem('hoja_turno', e.target.value); } catch (x) { /* sin almacenamiento */ }
    const last = hjRows().slice(-1)[0]; if (last && last.saved === false && !hjHasData(last)) { last.vals.employee = e.target.value; last.inputs.employee.value = e.target.value; }
  }}, h('option', {value: ''}, 'Elige…'), data.employees.map(n => h('option', {value: n}, n)));
  const mine = hjShift() || S.lastEmployee || ''; if (data.employees.includes(mine)) turno.value = mine;
  const table = h('table', {class: 'hoja'}, h('thead', {}, h('tr', {}, h('th', {class: 'hn'}, '#'), HJ_TITLES.map((t, i) => h('th', {class: 'c-' + HJ_COLS[i]}, t)), h('th', {}, 'hora'), h('th', {}))), HJ.tbody);
  const bar = {};
  bar.total = h('b', {class: 'big-total'}); bar.entries = h('b', {class: 'ok'}); bar.exits = h('b', {class: 'err'}); bar.count = h('b', {});
  bar.opening = h('b', {}); bar.expected = h('b', {});
  bar.status = h('div', {class: 'hstatus'});
  bar.shift = h('button', {class: 'primary', onclick: hjShiftModal}, 'Cerrar turno');
  bar.undo = h('button', {class: 'small', onclick: hjUndoShift}, 'Deshacer último cierre');
  bar.close = h('button', {onclick: hjCloseModal}, '🔒 Cerrar caja del día');
  bar.reopen = h('button', {class: 'danger', onclick: hjReopenModal}, 'Reabrir día');
  HJ.bar = bar;
  const kids = [
    h('div', {class: 'pagehead'}, h('div', {}, h('h1', {}, 'Apuntar caja · ' + fmtDay(day)), h('p', {class: 'muted'}, WEEK[new Date(day + 'T12:00:00').getDay()] + ' · ', HJ.stateEl)),
      h('div', {class: 'actions'}, ed ? h('label', {class: 'inline'}, 'Turno ', turno) : null))];
  if (!ed && !data.closed) kids.push(h('div', {class: 'note'}, can('register') ? 'Este día ya es antiguo: solo un responsable puede modificarlo.' : 'Solo lectura.'));
  kids.push(h('div', {class: 'panel scroll hoja-wrap'}, table), HJ.hintsEl,
    h('p', {class: 'hint'}, h('kbd', {}, 'Tab'), ' siguiente celda · ', h('kbd', {}, 'Intro'), ' siguiente fila · ', h('kbd', {}, '↑'), h('kbd', {}, '↓'), ' cambiar de fila · en concepto escribe «reno» y pulsa ', h('kbd', {}, 'Tab'), ' · las salidas (yoga, ciclo…) se ponen solas en negativo · las filas «INNUX» entran solas desde Innux y se pueden corregir.'),
    h('div', {class: 'hoja-bar'},
      h('div', {class: 'hb-main'}, h('div', {}, h('span', {class: 'hb-l'}, 'Total del día'), bar.total),
        h('div', {class: 'hb-sub'}, h('span', {}, 'Entradas ', bar.entries), h('span', {}, 'Salidas ', bar.exits), h('span', {}, 'Apuntes ', bar.count))),
      h('div', {class: 'hb-cash'}, h('span', {}, 'Fondo inicial ', bar.opening), h('span', {}, 'Debería haber en caja ', bar.expected)),
      h('div', {class: 'hb-act'}, bar.shift, bar.close, bar.reopen, bar.undo, bar.status),
      h('p', {class: 'hint'}, '¿Falta algo o hay que sumar varios importes? Hazlo en la ', h('b', {}, 'calculadora'), ' (botón «Calculadora» o tecla ', h('kbd', {}, 'C'), ') y apunta aquí solo el resultado.')));
  main.replaceChildren(...kids);
  const dl = h('datalist', {id: 'hoja-emp'}, data.employees.map(n => h('option', {value: n}))); main.append(dl);
  data.rows.forEach(src => hjAddRow(src));
  hjEnsureBlank(); hjRenumber(); hjDrawShifts(); hjUpdateBar(); hjDrawActions(); hjState();
  if (ed && day === S.today) hjFocus(hjRows().length - 1, 0);
  HJ.timer = setInterval(hjPoll, 6000);
}

// ---------------------------------------------------------------- Histórico (como una hoja de Excel, sin totales)
async function viewHistorico(main) {
  const month = h('input', {type: 'month', value: S.day.slice(0, 7), 'aria-label': 'Mes'}), search = h('input', {placeholder: 'Buscar en todos los meses: nombre, concepto o nº…', 'aria-label': 'Buscar'});
  const body = h('div', {class: 'panel scroll hoja-wrap'}, h('div', {class: 'skeleton'}));
  const COLS = [['fecha', 'fecha'], ['cents', 'efectivo'], ['concept', 'concepto'], ['name', 'nombre'], ['number', 'nº socio'], ['employee', 'gestionado por']];
  let flat = [], searching = false, sort = {col: 'fecha', dir: 'desc'};   // lo más reciente arriba
  const cmp = (a, b) => {
    if (sort.col === 'fecha') return a.day.localeCompare(b.day) || a.n - b.n;
    if (sort.col === 'cents') return a.cents - b.cents;
    const x = String(a[sort.col] || ''), y = String(b[sort.col] || '');
    return sort.col === 'number' && x && y && !isNaN(x) && !isNaN(y) ? Number(x) - Number(y) : x.localeCompare(y, 'es', {sensitivity: 'base'});
  };
  const paint = () => {
    if (!flat.length) return body.replaceChildren(h('p', {class: 'muted'}, searching ? 'No hay apuntes que coincidan.' : 'No hay apuntes en este mes.'));
    const rows = flat.slice().sort((a, b) => (sort.dir === 'asc' ? 1 : -1) * cmp(a, b));
    const head = COLS.map(([k, t]) => h('th', {class: 'sortable' + (k === 'cents' ? ' num' : '') + (sort.col === k ? ' on' : ''), tabindex: '0', role: 'button', 'aria-sort': sort.col === k ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none',
      onclick: () => { sort = {col: k, dir: sort.col === k ? (sort.dir === 'asc' ? 'desc' : 'asc') : (k === 'fecha' || k === 'cents' ? 'desc' : 'asc')}; paint(); },
      onkeydown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.target.click(); } }}, t, sort.col === k ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''));
    let prev = null, dayN = 0;
    body.replaceChildren(h('table', {class: 'hoja hist'}, h('thead', {}, h('tr', {}, head)),
      h('tbody', {}, rows.flatMap(x => { const first = sort.col === 'fecha' && x.day !== prev; prev = x.day; if (first) dayN++;
        const band = first ? h('tr', {class: 'dayhead'}, h('td', {colspan: '6'}, h('b', {}, WEEK[new Date(x.day + 'T12:00:00').getDay()].replace(/^./, c => c.toUpperCase()) + ' ' + fmtDay(x.day)),
          h('span', {class: 'muted'}, ' · ' + rows.filter(y => y.day === x.day).length + ' apuntes'))) : null;
        return [band, h('tr', {class: (first ? 'newday ' : '') + 'dz' + (dayN % 2)}, h('td', {class: 'hd'}, (searching ? fmtDay(x.day) : fmtDay(x.day).slice(0, 5)) + ' ' + WEEK[new Date(x.day + 'T12:00:00').getDay()].slice(0, 3)),
          h('td', {class: 'num ' + (x.cents < 0 ? 'neg' : 'pos')}, euros(x.cents).replace(' €', '')), h('td', {}, x.concept), h('td', {}, x.name), h('td', {}, x.number), h('td', {}, x.employee))]; }))));
  };
  const draw = async () => {
    if (!month.value) return;
    searching = !!search.value.trim();
    try {
      const r = await api('GET', '/hoja/historial/' + month.value + '?q=' + encodeURIComponent(search.value.trim()));
      flat = r.days.flatMap(d => d.rows.map((x, n) => Object.assign({day: d.day, n}, x)));
      paint();
    } catch (e) { body.replaceChildren(h('p', {class: 'err'}, e.message)); }
  };
  month.addEventListener('change', draw);
  let t; search.addEventListener('input', () => { clearTimeout(t); t = setTimeout(draw, 300); });
  main.replaceChildren(h('div', {class: 'pagehead'}, h('div', {}, h('h1', {}, 'Histórico'), h('p', {class: 'muted'}, 'Todo el Excel de siempre y lo apuntado desde la rejilla. Lo más reciente arriba; pulsa el título de una columna para ordenar. Si buscas, se mira en todos los meses.')), h('div', {class: 'actions'}, month, search)), body);
  draw();
}

// ---------------------------------------------------------------- Más (ajustes poco frecuentes)
function viewMas(main) {
  const sections = [h('h1', {}, 'Más')];
  const sug = h('textarea', {placeholder: 'Escribe una sugerencia (hasta 4000 caracteres)', maxlength: '4000'});
  sections.push(h('div', {class: 'panel'}, h('h2', {}, 'Sugerencias'), sug, h('p', {}, h('button', {onclick: async () => { try { await api('POST', '/suggestions', {body: sug.value}); sug.value = ''; toast('Gracias, guardada'); } catch (e) { toast(e.message, true); } }}, 'Enviar'))));
  if (can('config')) {
    const rows = Object.entries(S.prices).map(([k, v]) => [k, h('input', {value: centsText(v), inputmode: 'decimal'})]);
    const enabled = h('input', {type: 'checkbox'}); enabled.checked = !!S.flags.payments_enabled;
    const hour = h('input', {inputmode: 'numeric', value: String(S.openingHour == null ? 12 : S.openingHour)});
    sections.push(h('div', {class: 'panel'}, h('h2', {}, 'Precios y configuración'), h('div', {class: 'row2'}, rows.map(([k, i]) => h('div', {}, h('label', {}, k.replaceAll('_', ' ')), i))),
      h('label', {class: 'check'}, enabled, 'Permitir cobros de cuota desde la web (activar solo tras el corte acordado)'),
      field('Hora a partir de la que se pide el dinero inicial de caja (0 a 23)', hour),
      h('button', {class: 'primary', onclick: async () => { try { const prices = {}; rows.forEach(([k, i]) => { prices[k] = parseCents(i.value); });
        const openingHour = parseInt(hour.value, 10); if (!(openingHour >= 0 && openingHour <= 23)) throw new Error('La hora debe estar entre 0 y 23.');
        await api('POST', '/settings', {prices, payments_enabled: enabled.checked, opening_hour: openingHour}); toast('Guardado'); boot(); } catch (e) { toast(e.message, true); } }}, 'Guardar')));
    const au = h('div', {});
    sections.push(h('div', {class: 'panel'}, h('h2', {}, 'Auditoría (últimos 300)'), h('button', {onclick: async () => { const r = await api('GET', '/audit'); au.replaceChildren(h('div', {class: 'scroll'}, h('table', {}, r.audit.map(a => h('tr', {}, h('td', {class: 'small'}, fmtInstant(a.created)), h('td', {}, a.action), h('td', {class: 'small'}, a.actor || ''))))));  }}, 'Ver'), au));
  }
  main.replaceChildren(...sections);
}



boot();
