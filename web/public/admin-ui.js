// Calendario propio para elegir el día (sustituye al del navegador).
// El <input type="date" id="fecha"> sigue existiendo, oculto, para no tocar la lógica del panel.
(() => {
  const $ = (id) => document.getElementById(id);
  const input = $('fecha'), pop = $('dp-pop'), grid = $('dp-grid'), cur = $('dp-current'), label = $('dp-label'), monthEl = $('dp-month');
  if (!input || !pop) return;
  const MESES = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  const DIAS = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parse = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
  const hoyIso = () => iso(new Date());
  let vista = new Date();
  vista.setDate(1);

  function pintarEtiqueta() {
    if (!input.value) { label.textContent = 'Elegir día'; return; }
    const d = parse(input.value);
    const rel = input.value === hoyIso() ? 'Hoy · ' : '';
    label.textContent = `${rel}${DIAS[d.getDay()]} ${d.getDate()} de ${MESES[d.getMonth()]}`;
  }

  function pintarMes() {
    monthEl.textContent = `${MESES[vista.getMonth()]} ${vista.getFullYear()}`;
    grid.textContent = '';
    const primero = new Date(vista.getFullYear(), vista.getMonth(), 1);
    const hueco = (primero.getDay() + 6) % 7; // semana empieza en lunes
    const total = new Date(vista.getFullYear(), vista.getMonth() + 1, 0).getDate();
    for (let i = 0; i < hueco; i++) grid.append(document.createElement('span'));
    const hoy = hoyIso();
    for (let d = 1; d <= total; d++) {
      const f = iso(new Date(vista.getFullYear(), vista.getMonth(), d));
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'dp-day' + (f === hoy ? ' is-today' : '') + (f === input.value ? ' is-selected' : '');
      b.textContent = String(d);
      b.dataset.fecha = f;
      b.setAttribute('aria-label', `${d} de ${MESES[vista.getMonth()]}`);
      if (f === input.value) b.setAttribute('aria-current', 'date');
      grid.append(b);
    }
  }

  function elegir(f) {
    if (input.value === f) { sincronizar(); return; }
    input.value = f;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    sincronizar();
  }

  function sincronizar() {
    if (input.value) { const d = parse(input.value); vista = new Date(d.getFullYear(), d.getMonth(), 1); }
    pintarEtiqueta();
    if (!pop.hidden) pintarMes();
  }

  function abrir() { pop.hidden = false; cur.setAttribute('aria-expanded', 'true'); pintarMes(); const s = grid.querySelector('.is-selected') || grid.querySelector('.is-today') || grid.querySelector('button'); if (s) s.focus(); }
  function cerrar() { pop.hidden = true; cur.setAttribute('aria-expanded', 'false'); }
  const mover = (dias) => { const d = input.value ? parse(input.value) : new Date(); d.setDate(d.getDate() + dias); elegir(iso(d)); };

  cur.addEventListener('click', () => (pop.hidden ? abrir() : cerrar()));
  $('dp-prev').addEventListener('click', () => mover(-1));
  $('dp-next').addEventListener('click', () => mover(1));
  $('dp-today').addEventListener('click', () => { elegir(hoyIso()); cerrar(); });
  $('dp-mprev').addEventListener('click', () => { vista = new Date(vista.getFullYear(), vista.getMonth() - 1, 1); pintarMes(); });
  $('dp-mnext').addEventListener('click', () => { vista = new Date(vista.getFullYear(), vista.getMonth() + 1, 1); pintarMes(); });
  grid.addEventListener('click', (e) => { const b = e.target.closest('.dp-day'); if (!b) return; elegir(b.dataset.fecha); cerrar(); cur.focus(); });
  document.addEventListener('click', (e) => { if (!pop.hidden && !$('datepick').contains(e.target)) cerrar(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !pop.hidden) { cerrar(); cur.focus(); } });
  input.addEventListener('change', sincronizar);

  // El panel arranca con la fecha en UTC (de madrugada marcaba el día anterior): usamos el día local.
  function iniciar() {
    if (input.value !== hoyIso()) { input.value = hoyIso(); input.dispatchEvent(new Event('change', { bubbles: true })); }
    sincronizar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
