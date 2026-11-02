
(function(){
  // Esc cierra el diálogo visible más reciente: pulsa su botón de cancelar/volver si lo tiene; si no, lo retira.
  // Los diálogos fijos de la página (p. ej. #modal-exito) no se eliminan del DOM: solo se ocultan.
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || e.defaultPrevented) return;
    var pop = document.getElementById('dp-pop'); if (pop && !pop.hidden) return;      // el calendario gestiona su propio Esc
    var dialogs = [].filter.call(document.querySelectorAll('.modal'), function (m) {
      var cs = window.getComputedStyle(m); return cs.display !== 'none' && cs.visibility !== 'hidden';
    });
    if (!dialogs.length) return;
    var top = dialogs[dialogs.length - 1];
    var cancel = top.querySelector('[id^="cancelar"], #noEliminar, .btn-secondary, [data-cerrar], .modal-close');
    e.preventDefault();
    if (cancel) cancel.click();
    else if (top.id === 'modal-exito') top.style.display = 'none';
    else top.remove();
  });
  function parseFechaInput() {
    var el = document.getElementById('fecha');
    if (!el || !el.value) {
      // fallback to today yyyy-mm-dd
      var d = new Date();
      return d.toISOString().slice(0,10);
    }
    return el.value;
  }

  async function fetchJSON(url) {
    const r = await fetch(url, {cache: 'no-store'});
    if (!r.ok) throw new Error('HTTP '+r.status);
    return r.json();
  }

  async function buildIndexHorarios() {
    const hs = await fetchJSON('obtener_horarios.php');
    // index by composite key clase|dia|hora (normalized)
    const idx = {};
    hs.forEach(h => {
      const key = (h.clase+'|'+h.dia+'|'+h.hora).toLowerCase().replace(/\s+/g,'');
      idx[key] = h.id;
    });
    return idx;
  }

  function normalize(s){ return String(s||'').toLowerCase().replace(/\s+/g,''); }

  async function decorarTablaHorarios() {
    const fecha = parseFechaInput();
    let contadores = {};
    try {
      contadores = await fetchJSON('obtener_contadores_dia.php?fecha='+encodeURIComponent(fecha));
    } catch(e){ console.warn('No contadores', e); }

    let idx = {};
    try { idx = await buildIndexHorarios(); } catch(e){ console.warn('No idx horarios', e); }

    const tbody = document.querySelector('#tabla-horarios tbody');
    if (!tbody) return;
    [...tbody.querySelectorAll('tr')].forEach(tr => {
      tr.classList.remove('con-inscritos');
      const badge = tr.querySelector('.badge-inscritos');
      if (badge) badge.remove();

      const tds = tr.querySelectorAll('td');
      if (tds.length < 3) return;
      const cls = tds[0].textContent.trim();
      const dia = tds[1].textContent.trim();
      const hora = tds[2].textContent.trim();

      const id = idx[ normalize(cls)+'|'+normalize(dia)+'|'+normalize(hora) ];
      if (!id) return;
      const n = contadores[id] || 0;
      if (n > 0) {
        tr.classList.add('con-inscritos');
        // add badge on the right of Hora cell
        const badge = document.createElement('span');
        badge.className = 'badge-inscritos';
        badge.textContent = n;
        tds[2].appendChild(badge);
      }
    });
  }

  // Observe table changes to re-decorate
  const obs = new MutationObserver((muts)=>{
    let relevant = false;
    muts.forEach(m => {
      if (m.type === 'childList') relevant = true;
    });
    if (relevant) setTimeout(decorarTablaHorarios, 50);
  });
  window.addEventListener('DOMContentLoaded', ()=>{
    const tb = document.querySelector('#tabla-horarios tbody');
    if (tb) obs.observe(tb, {childList: true, subtree: true});
    setInterval(decorarTablaHorarios, 2000); // periodic refresh, lightweight
    const fecha = document.getElementById('fecha');
    if (fecha) fecha.addEventListener('change', decorarTablaHorarios);
  });
})();
