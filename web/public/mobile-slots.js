// Capa de interfaz móvil: muestra las opciones del <select> de horarios como
// pestañas de día + botones grandes. La lógica de reservas no cambia.
(() => {
  const $ = (id) => document.getElementById(id);
  const select = $('selectHorarios'), lista = $('horarios-lista'), tabs = $('dias-tabs'), form = $('formulario'), submit = $('submit');
  if (!select || !lista) return;
  const DIAS = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };

  function etiquetaDia(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    const fecha = new Date(y, m - 1, d), hoy = new Date();
    const dif = Math.round((fecha - new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())) / 86400000);
    return dif === 0 ? 'Hoy' : dif === 1 ? 'Mañana' : DIAS[fecha.getDay()].slice(0, 3);
  }

  let pendiente = false;
  const programar = () => { if (pendiente) return; pendiente = true; requestAnimationFrame(() => { pendiente = false; pintar(); }); };

  function pintar() {
    const opciones = [...select.options];
    lista.textContent = ''; tabs.textContent = '';
    const reales = opciones.filter((o) => o.dataset.fecha);
    if (!reales.length) {
      const msg = opciones[0] && opciones[0].textContent;
      if (!opciones.length || /^Cargando/i.test(msg || '')) {
        const g = el('div', 'slot-grid');
        for (let i = 0; i < 4; i++) g.append(el('div', 'slot-skeleton'));
        lista.append(g); lista.setAttribute('aria-busy', 'true');
      } else { lista.removeAttribute('aria-busy'); lista.append(el('p', 'slots-empty', msg)); }
      estilo(); return;
    }
    lista.removeAttribute('aria-busy');
    const dias = [...new Set(reales.map((o) => o.dataset.fecha))];
    const sel = select.selectedOptions && select.selectedOptions[0];
    const diaSel = sel && sel.dataset.fecha ? sel.dataset.fecha : dias[0];
    for (const dia of dias) {
      const t = el('button', 'day-tab'); t.type = 'button';
      t.setAttribute('role', 'tab'); t.setAttribute('aria-selected', String(dia === diaSel)); t.dataset.dia = dia;
      t.append(el('span', 'd1', etiquetaDia(dia)), el('span', 'd2', String(Number(dia.split('-')[2]))));
      tabs.append(t);
    }
    const grid = el('div', 'slot-grid'); lista.append(grid);
    for (const opt of reales.filter((o) => o.dataset.fecha === diaSel)) {
      const disp = parseInt(opt.dataset.disponibles || '0', 10), cola = parseInt(opt.dataset.cola || '0', 10), completo = disp <= 0;
      const [ini, fin] = (opt.dataset.hora || '').split('-');
      const [fy, fm, fd] = (opt.dataset.fecha || '').split('-').map(Number), [hh, mm] = (ini || '0:0').split(':').map(Number);
      const empezada = !!fy && new Date(fy, fm - 1, fd, hh, mm) <= new Date();
      const b = el('button', 'slot' + (completo ? ' full' : '') + (empezada ? ' started' : '')); b.type = 'button';
      if (empezada) { b.disabled = true; b.title = 'La clase ya ha empezado'; }
      b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', String(opt.selected)); b.dataset.value = opt.value;
      const t = el('span', 't', ini || ''); if (fin) t.append(el('i', null, ` – ${fin}`));
      b.append(t, el('span', 's', empezada ? 'Ya ha empezado' : completo ? (cola > 0 ? `Completo · ${cola} en espera` : 'Completo · lista de espera') : `${disp} plaza${disp !== 1 ? 's' : ''}`));
      grid.append(b);
    }
    estilo();
  }

  function estilo() {
    const opt = select.selectedOptions && select.selectedOptions[0];
    submit.classList.toggle('waitlist', !!(opt && opt.dataset.fecha && parseInt(opt.dataset.disponibles || '0', 10) <= 0));
  }

  const cambiar = (value) => { select.value = value; select.dispatchEvent(new Event('change', { bubbles: true })); programar(); };
  tabs.addEventListener('click', (e) => {
    const t = e.target.closest('.day-tab'); if (!t) return;
    const o = [...select.options].find((x) => x.dataset.fecha === t.dataset.dia); if (o) cambiar(o.value);
  });
  lista.addEventListener('click', (e) => {
    const b = e.target.closest('.slot'); if (!b) return;
    cambiar(b.dataset.value);
    for (const x of lista.querySelectorAll('.slot')) x.setAttribute('aria-checked', String(x === b));
  });
  new MutationObserver(programar).observe(select, { childList: true });
  select.addEventListener('change', programar);
  document.body.classList.add('has-slots');

  // foto de la clase en la cabecera del panel
  new MutationObserver(() => {
    if (form.style.display !== 'block') return;
    const nombre = ($('form-titulo').querySelector('strong') || {}).textContent || '';
    const card = [...document.querySelectorAll('.card')].find((c) => c.dataset.class.toUpperCase() === nombre.toUpperCase());
    const img = card && card.querySelector('img');
    if (img) form.style.setProperty('--sheet-img', `url("${img.getAttribute('src')}")`);
    programar();
  }).observe(form, { attributes: true, attributeFilter: ['style'] });
})();
