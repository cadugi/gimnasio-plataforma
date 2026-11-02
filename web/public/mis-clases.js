'use strict';
/* «Mis clases»: reservas y posición en la lista de espera de la persona de este móvil. Mensajes que no desaparecen solos. */
(() => {
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined && text !== null) e.textContent = text; if (cls) e.className = cls; return e; };
  const clear = n => { while (n.firstChild) n.removeChild(n.firstChild); };
  const store = { get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }, del(k) { try { localStorage.removeItem(k); } catch (_) {} } };
  const compartida = store.get('tf_modo') === 'compartido';
  const platform = /iPhone|iPad|iPod/.test(navigator.userAgent) ? 'ios' : /Android/.test(navigator.userAgent) ? 'android' : 'other';
  const DAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  let csrf = '';
  const say = t => { const e = $('msg'); e.textContent = t; e.hidden = !t; };
  const fail = t => { const e = $('err'); e.textContent = t; e.hidden = !t; };
  const ERR = { CLASS_STARTED: 'La clase ya ha empezado y no se puede cancelar desde aquí. Habla con recepción.', SHARED_SCREEN: 'Esto no se puede hacer en una pantalla compartida.', CSRF_REQUIRED: 'La página ha caducado. Recárgala e inténtalo otra vez.', INVALID_DATA: 'Revisa el nombre y el teléfono. El teléfono tiene 9 cifras.', TOO_MANY_ATTEMPTS: 'Has probado muchas veces. Espera unos minutos.', ACCESS_DENIED: 'Escribe tus datos otra vez.' };
  const errText = c => c === 'OFFLINE' ? 'No hay conexión a internet.' : (ERR[c] || 'Ahora mismo no podemos hacerlo. Inténtalo de nuevo en un momento.');
  async function api(url, body) {
    const o = { credentials: 'same-origin', headers: {} };
    if (body) { o.method = 'POST'; o.body = JSON.stringify(body); Object.assign(o.headers, { 'Content-Type': 'application/json', 'X-TopFitness-Request': '1', 'X-CSRF-Token': csrf }); }
    let r; try { r = await fetch(url, o); } catch (_) { throw new Error('OFFLINE'); }
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw new Error(j.error || j.code || 'TEMPORARY_FAILURE');
    return j;
  }
  const guard = async (b, fn) => { b.disabled = true; fail(''); try { await fn(); } catch (e) { fail(errText(e.message)); } finally { b.disabled = false; } };
  const fecha = f => { const d = new Date(f + 'T12:00:00'); return `${DAYS[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`; };
  /* Cancelar con confirmación en dos pasos. Nada desaparece solo: el resultado queda escrito en pantalla. */
  function accion(c, tipo) {
    const wrap = el('div', null, 'accion');
    const abrir = el('button', tipo === 'cancelar' ? 'Cancelar mi reserva' : 'Salir de la lista de espera', 'secondary'); abrir.type = 'button';
    const conf = el('div'); conf.hidden = true;
    conf.append(el('p', tipo === 'cancelar' ? `¿Seguro que quieres cancelar tu plaza en ${c.clase} el ${fecha(c.fecha)} a las ${c.hora}? Otra persona podrá ocuparla.` : `¿Seguro que quieres salir de la lista de espera de ${c.clase} el ${fecha(c.fecha)}? Si cambias de idea, tendrás que apuntarte otra vez al final de la lista.`, 'msg error'));
    const si = el('button', tipo === 'cancelar' ? 'Sí, cancelar mi plaza' : 'Sí, salir de la lista', 'primary'); si.type = 'button';
    const no = el('button', tipo === 'cancelar' ? 'No, mantener mi plaza' : 'No, seguir en la lista', 'secondary'); no.type = 'button';
    conf.append(si, no); wrap.append(abrir, conf);
    abrir.addEventListener('click', () => { abrir.hidden = true; conf.hidden = false; si.focus(); });
    no.addEventListener('click', () => { conf.hidden = true; abrir.hidden = false; abrir.focus(); });
    si.addEventListener('click', () => guard(si, async () => {
      const r = await api('mis_clases.php', { action: tipo, ref: c.ref });
      say(tipo === 'cancelar' ? `Has cancelado tu plaza en ${c.clase} (${fecha(c.fecha)} ${c.hora}).` : `Has salido de la lista de espera de ${c.clase} (${fecha(c.fecha)}).`);
      render(await api('mis_clases.php'));
    }));
    return wrap;
  }
  function card(c, extra) {
    const d = el('div', null, 'clase' + (extra && extra.oferta ? ' oferta' : ''));
    d.append(el('h3', c.clase), el('div', `${fecha(c.fecha)} · ${c.hora}`, 'cuando'));
    if (c.cancelada) d.append(el('span', 'Clase cancelada', 'etq mal'));
    return d;
  }
  function render(j) {
    $('s-ident').hidden = true; $('s-lista').hidden = false; $('quien').textContent = j.nombre;
    const r = $('reservas'), w = $('espera'); clear(r); clear(w);
    if (!j.reservas.length) r.append(el('p', 'Todavía no tienes clases reservadas.', 'note'));
    j.reservas.forEach(c => { const d = card(c); if (!c.cancelada) d.append(el('span', 'Plaza confirmada', 'etq ok')); if (c.puede && c.ref) d.append(accion(c, 'cancelar')); r.append(d); });
    if (!j.espera.length) w.append(el('p', 'No estás en ninguna lista de espera.', 'note'));
    j.espera.forEach(c => {
      const d = card(c, { oferta: !!c.oferta_hasta });
      if (c.oferta_hasta) { d.append(el('span', '¡Te ofrecemos plaza!', 'etq ok'), el('p', `Responde antes de las ${c.oferta_hasta} abriendo el aviso que te hemos enviado al móvil.`)); }
      else if (!c.cancelada) d.append(el('span', `Tu posición: ${c.posicion} de ${c.total}`, 'etq'), el('p', 'Si se libera una plaza, te avisaremos al móvil.', 'note'));
      if (c.puede && c.ref) d.append(accion(c, 'salir'));
      w.append(d);
    });
    $('aviso-estado').textContent = j.avisos === 'ACTIVATED' ? 'Avisos activados en este móvil.' : 'Los avisos no están activados. Pulsa «Avisos» abajo para activarlos y que te avisemos de las plazas libres.';
  }
  async function cargar() {
    if (compartida) { $('compartida').hidden = false; return; }
    const e = await api('movil.php');
    if (!e.linked) { $('s-lista').hidden = true; $('s-ident').hidden = false; return; }
    csrf = e.csrf; render(await api('mis_clases.php'));
  }
  $('f-ident').addEventListener('submit', ev => { ev.preventDefault(); guard($('b-ident'), async () => {
    const r = await api('movil.php', { action: 'identificar', nombre: $('nombre').value, telefono: $('telefono').value, plataforma: platform });
    if (!r.linked) throw new Error('INVALID_DATA');
    if ($('recordar').checked) store.set('tf_recordar', '1'); else store.del('tf_recordar');
    await cargar();
  }); });
  $('b-salir').addEventListener('click', e => guard(e.currentTarget, async () => { await api('movil.php', { action: 'olvidar' }); store.del('tf_recordar'); $('s-lista').hidden = true; $('s-ident').hidden = false; say('Has cerrado la sesión en este móvil.'); }));
  cargar().catch(e => fail(errText(e.message)));
})();
