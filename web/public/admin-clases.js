// Panel de administración: cancelar una clase un día concreto y apuntar a una persona a varias clases.
(() => {
  const $ = (id) => document.getElementById(id);
  const DIAS = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
  const DIAS_BD = ['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
  const MESES = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parse = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
  const larga = (f) => { const d = parse(f); return `${DIAS[d.getDay()]} ${d.getDate()} de ${MESES[d.getMonth()]}`; };
  const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };

  async function post(url, datos) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(datos).toString() });
    let j = null; try { j = await r.json(); } catch (_) {}
    return j || { success: false, error: 'SERVICE_ERROR' };
  }
  async function listaCanceladas() {
    try { const r = await fetch('admin_clases_canceladas.php?desde=' + iso(new Date()), { cache: 'no-store' }); const j = await r.json(); return j.ok ? j.data : []; }
    catch (_) { return []; }
  }

  function ventana(clase, contenido) {
    const modal = el('div', 'modal'); modal.setAttribute('role', 'dialog'); modal.setAttribute('aria-modal', 'true');
    const caja = el('div', 'modal-content ' + (clase || '')); caja.append(...contenido); modal.append(caja);
    document.body.append(modal);
    return { modal, caja, cerrar: () => modal.remove() };
  }

  // ---------------------------------------------------------------- cancelar clase
  let canceladas = new Map();
  const clave = (id, f) => `${id}|${f}`;

  async function recargarCanceladas() {
    canceladas = new Map((await listaCanceladas()).map((c) => [clave(c.horario_id, c.fecha), c]));
    decorar();
  }

  function cuentaPantalla() {
    return {
      inscritos: document.querySelectorAll('#inscritos .tabla-container tbody tr').length,
      espera: document.querySelectorAll('#cola-admin tbody tr').length
    };
  }

  function decorar() {
    const fecha = getFechaISO();
    for (const b of document.querySelectorAll('#menu button')) {
      const c = canceladas.get(clave(b.id, fecha));
      b.classList.toggle('cancelada', !!c);
      let tag = b.querySelector('.tag-cancelada');
      if (c && !tag) b.append(el('span', 'tag-cancelada', 'Cancelada'));
      if (!c && tag) tag.remove();
    }
    const cont = $('inscritos'), add = $('boton-inscripciones');
    if (!cont || !add || !admin.horarioId) return;
    const c = canceladas.get(clave(admin.horarioId, fecha));
    let barra = cont.querySelector('.clase-estado');
    const firma = c ? 'c|' + (c.motivo || '') : 'a';
    if (barra && barra.dataset.firma === firma) { add.disabled = !!c; return; }
    if (barra) barra.remove();
    cont.querySelector('.btn-cancelar-clase')?.remove();
    barra = el('div', c ? 'clase-estado cancelada' : 'clase-estado');
    barra.dataset.firma = firma;
    if (c) {
      const t = el('div', 'ce-texto');
      t.append(el('strong', null, 'Clase cancelada este día'));
      t.append(el('span', null, (c.motivo ? 'Motivo: ' + c.motivo + '. ' : '') + 'Ya no se puede reservar. Las personas apuntadas siguen en la lista para que puedas avisarlas.'));
      const re = el('button', 'btn', 'Reactivar clase'); re.type = 'button';
      re.addEventListener('click', () => reactivar());
      barra.append(t, re);
      add.parentNode.insertBefore(barra, add);
      add.disabled = true;
    } else {
      add.disabled = false;
      const b = el('button', 'btn-cancelar-clase', 'Cancelar esta clase'); b.type = 'button';
      b.addEventListener('click', () => pedirCancelacion());
      add.insertAdjacentElement('afterend', b);
      barra.hidden = true;
      barra.dataset.firma = firma;
      cont.append(barra);
    }
  }

  function pedirCancelacion() {
    const fecha = getFechaISO(), n = cuentaPantalla();
    const titulo = el('h2', null, 'Cancelar esta clase');
    const info = el('p', 'cc-clase'); info.textContent = `${String(admin.clase || '').toUpperCase()} · ${admin.hora || ''} · ${larga(fecha)}`;
    const expl = el('p', null, 'Solo se cancela este día: el horario no se borra y las demás semanas no cambian. La clase dejará de aparecer para reservar.');
    const aviso = el('p', 'cc-aviso', n.inscritos + n.espera > 0
      ? `Ahora hay ${n.inscritos} persona${n.inscritos !== 1 ? 's' : ''} apuntada${n.inscritos !== 1 ? 's' : ''}` + (n.espera ? ` y ${n.espera} en lista de espera` : '') + '. Seguirán en la lista para que puedas avisarlas.'
      : 'Ahora mismo no hay nadie apuntado.');
    const lab = el('label', null, 'Motivo (opcional)'); lab.setAttribute('for', 'cc-motivo');
    const inp = el('input'); inp.id = 'cc-motivo'; inp.type = 'text'; inp.maxLength = 200; inp.placeholder = 'Por ejemplo: no viene la profesora';
    const fila = el('div', 'modal-buttons');
    const ok = el('button', 'btn btn-danger', 'Sí, cancelar la clase'); ok.type = 'button';
    const no = el('button', 'btn btn-secondary', 'Volver'); no.type = 'button';
    fila.append(ok, no);
    const v = ventana('modal-delete', [titulo, info, expl, aviso, lab, inp, fila]);
    inp.focus();
    no.addEventListener('click', v.cerrar);
    v.modal.addEventListener('click', (e) => { if (e.target === v.modal) v.cerrar(); });
    ok.addEventListener('click', async () => {
      ok.disabled = true;
      const r = await post('admin_cancelar_clase.php', { accion: 'cancelar', horario_id: admin.horarioId, fecha, motivo: inp.value.trim() });
      v.cerrar();
      if (r.success) { notificarExito('Clase cancelada. Ya no se puede reservar ese día.'); await recargarCanceladas(); }
      else alert(errorAmigable(r.error));
    });
  }

  async function reactivar() {
    const r = await post('admin_cancelar_clase.php', { accion: 'reactivar', horario_id: admin.horarioId, fecha: getFechaISO() });
    if (r.success) { notificarExito('Clase reactivada. Ya se puede reservar.'); await recargarCanceladas(); }
    else alert(errorAmigable(r.error));
  }

  const menu = $('menu'), cont = $('inscritos');
  if (menu) new MutationObserver(() => decorar()).observe(menu, { childList: true });
  if (cont) new MutationObserver(() => decorar()).observe(cont, { childList: true });
  $('fecha')?.addEventListener('change', () => setTimeout(decorar, 300));
  document.addEventListener('DOMContentLoaded', recargarCanceladas);
  if (document.readyState !== 'loading') recargarCanceladas();
  setInterval(recargarCanceladas, 60000);

  // ---------------------------------------------------------------- apuntar a varias clases
  const DIAS_VISTA = 14;

  async function abrirMultiple() {
    let horarios = [], cancel = new Map();
    try { horarios = await (await fetch('obtener_horarios.php', { cache: 'no-store' })).json(); } catch (_) {}
    cancel = new Map((await listaCanceladas()).map((c) => [clave(c.horario_id, c.fecha), c]));
    if (!Array.isArray(horarios) || !horarios.length) { alert('No se han podido cargar los horarios.'); return; }

    const elegidas = new Map(); // clave -> {horario_id, fecha, clase, hora}
    const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
    const dias = Array.from({ length: DIAS_VISTA }, (_, i) => { const d = new Date(hoy); d.setDate(d.getDate() + i); return d; });

    const titulo = el('h2', null, 'Apuntar a varias clases');
    const ayuda = el('p', 'section-hint', 'Escribe los datos, marca todas las clases y días que quieras y pulsa Apuntar. Administración apunta directamente, incluso con aforo completo o inscripciones previas.');
    const campos = el('div', 'multi-campos');
    const mk = (id, txt, tipo, ph) => { const w = el('div'); const l = el('label', null, txt); l.setAttribute('for', id); const i = el('input'); i.id = id; i.type = tipo; i.placeholder = ph; i.autocomplete = 'off'; w.append(l, i); return [w, i]; };
    const [wN, iN] = mk('multi-nombre', 'Nombre y apellidos', 'text', 'Nombre completo');
    const [wT, iT] = mk('multi-telefono', 'Teléfono', 'tel', '600 000 000');
    iT.inputMode = 'tel'; iN.maxLength = 100; iT.maxLength = 15;
    campos.append(wN, wT);

    const filtroW = el('div', 'multi-filtro');
    const filtroL = el('label', null, 'Mostrar'); filtroL.setAttribute('for', 'multi-filtro');
    const filtro = el('select'); filtro.id = 'multi-filtro';
    filtro.append(new Option('Todas las clases', ''));
    [...new Set(horarios.map((h) => h.clase))].sort().forEach((c) => filtro.append(new Option(c, c)));
    filtroW.append(filtroL, filtro);

    const lista = el('div', 'multi-dias');
    const pie = el('div', 'modal-buttons multi-pie');
    const ok = el('button', 'btn btn-primary', 'Apuntar'); ok.type = 'button'; ok.disabled = true;
    const no = el('button', 'btn btn-secondary', 'Cancelar'); no.type = 'button';
    pie.append(ok, no);
    const v = ventana('modal-wide', [titulo, ayuda, campos, filtroW, lista, pie]);
    no.addEventListener('click', v.cerrar);

    function actualizar() {
      ok.textContent = elegidas.size ? `Apuntar a ${elegidas.size} clase${elegidas.size !== 1 ? 's' : ''}` : 'Apuntar';
      ok.disabled = !elegidas.size;
    }

    function pintar() {
      lista.textContent = '';
      for (const d of dias) {
        const f = iso(d), nombreBd = DIAS_BD[d.getDay()];
        const ses = horarios.filter((h) => h.dia === nombreBd && (!filtro.value || h.clase === filtro.value)).sort((a, b) => a.hora.localeCompare(b.hora));
        if (!ses.length) continue;
        const bloque = el('section', 'multi-dia');
        const cab = el('h3', null, (f === iso(hoy) ? 'Hoy · ' : '') + cap(larga(f)));
        const todas = el('button', 'multi-todas', 'Marcar todo el día'); todas.type = 'button';
        cab.append(todas);
        const grid = el('div', 'multi-grid');
        const botones = [];
        for (const h of ses) {
          const k = clave(h.id, f), c = cancel.get(k);
          const b = el('button', 'multi-sesion' + (c ? ' is-cancelada' : '')); b.type = 'button';
          b.setAttribute('aria-pressed', String(elegidas.has(k)));
          b.append(el('strong', null, h.clase), el('span', null, c ? 'Cancelada' : h.hora));
          if (c) { b.disabled = true; b.title = 'Clase cancelada: no se puede apuntar'; elegidas.delete(k); }   // las canceladas no se pueden marcar
          else {
            botones.push([b, h, k]);
            b.addEventListener('click', () => {
              if (elegidas.has(k)) elegidas.delete(k); else elegidas.set(k, { horario_id: h.id, fecha: f, clase: h.clase, hora: h.hora });
              b.setAttribute('aria-pressed', String(elegidas.has(k))); actualizar();
            });
          }
          grid.append(b);
        }
        todas.addEventListener('click', () => {
          const todosMarcados = botones.every(([, , k]) => elegidas.has(k));
          for (const [b, h, k] of botones) {
            if (todosMarcados) elegidas.delete(k); else elegidas.set(k, { horario_id: h.id, fecha: f, clase: h.clase, hora: h.hora });
            b.setAttribute('aria-pressed', String(elegidas.has(k)));
          }
          actualizar();
        });
        if (!botones.length) todas.hidden = true;
        bloque.append(cab, grid); lista.append(bloque);
      }
      if (!lista.children.length) lista.append(el('p', 'section-hint', 'No hay clases con ese filtro.'));
    }
    filtro.addEventListener('change', pintar);
    pintar(); actualizar(); iN.focus();

    ok.addEventListener('click', async () => {
      const nombre = iN.value.trim(), tel = iT.value.trim();
      if (!nombre || !tel) { alert('Escribe el nombre y el teléfono.'); (nombre ? iT : iN).focus(); return; }
      ok.disabled = true; ok.textContent = 'Apuntando…';
      const r = await post('admin_inscribir_multiple.php', { nombre, telefono: tel, sesiones: JSON.stringify([...elegidas.values()].map(({ horario_id, fecha }) => ({ horario_id, fecha }))) });
      if (!r.success) { v.cerrar(); alert(errorAmigable(r.error)); return; }
      resumen(v, nombre, r.resultados || [], elegidas);
    });
  }

  function resumen(v, nombre, resultados, elegidas) {
    const textos = { APUNTADO: ['Apuntado', 'ok'], EN_ESPERA: ['Lista de espera (clase llena)', 'espera'], YA_APUNTADO: ['Ya estaba apuntado', 'info'], YA_EN_ESPERA: ['Ya estaba en la lista de espera', 'info'], ESPERA_OTRO_DIA: ['Ya está en la espera de otro día', 'error'], CANCELADA: ['Clase cancelada: no se ha apuntado', 'error'], REQUIERE_AVISOS: ['No entra en la espera: debe activar los avisos en su móvil', 'error'], CLASE_LLENA: ['Clase completa: no se ha podido añadir a la espera', 'error'], ESPERA_OTRA_PERSONA: ['Otra persona ya está en espera con este teléfono: revisa los datos', 'error'], DIA_NO_COINCIDE: ['El día no coincide', 'error'], ERROR: ['No se pudo', 'error'] };
    const n = (e) => resultados.filter((r) => r.estado === e).length;
    v.caja.textContent = '';
    v.caja.classList.add('modal-wide');
    const t = el('h2', null, 'Resultado');
    const s = el('p', 'section-hint');
    s.textContent = `${nombre}: ${n('APUNTADO')} apuntado${n('APUNTADO') !== 1 ? 's' : ''}` + (n('EN_ESPERA') ? `, ${n('EN_ESPERA')} en lista de espera` : '') + (resultados.length - n('APUNTADO') - n('EN_ESPERA') ? `, ${resultados.length - n('APUNTADO') - n('EN_ESPERA')} sin cambios` : '') + '.' + (resultados.some((r) => r.estado === 'APUNTADO' && r.avisos === false) ? ' Esta persona no recibirá avisos en el móvil (no tiene el móvil asociado).' : '');
    const ul = el('ul', 'multi-resultados');
    for (const r of resultados) {
      const info = elegidas.get(clave(r.horario_id, r.fecha)) || {};
      const [txt, tipo] = textos[r.estado] || textos.ERROR;
      const li = el('li', 'res-' + tipo);
      li.append(el('span', 'res-clase', `${String(r.clase || info.clase || '').toUpperCase()} · ${r.hora || info.hora || ''} · ${r.fecha ? cap(larga(r.fecha)) : ''}`), el('strong', null, txt));
      ul.append(li);
    }
    const cerrar = el('button', 'btn btn-primary', 'Cerrar'); cerrar.type = 'button';
    cerrar.addEventListener('click', () => { v.cerrar(); if (typeof refreshAdminUI === 'function') refreshAdminUI(); });
    v.caja.append(t, s, ul, cerrar);
  }

  $('btn-multi')?.addEventListener('click', abrirMultiple);
})();
