'use strict';
/* Recepción: salud del servicio de avisos, ofertas pendientes, incidencias y móviles asociados. Los mensajes no desaparecen solos. */
(() => {
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined && text !== null) e.textContent = text; if (cls) e.className = cls; return e; };
  const clear = n => { while (n.firstChild) n.removeChild(n.firstChild); };
  const say = t => { const e = $('msg'); e.textContent = t; e.hidden = !t; };
  const fail = t => { const e = $('err'); e.textContent = t; e.hidden = !t; };
  const ERR = { OFFER_EXPIRED: 'La oferta ya había caducado. Se ha pasado la plaza a la siguiente persona.', SESSION_CANCELLED: 'La clase está cancelada. No se ha confirmado nada.', OFFER_CLOSED: 'Esa oferta ya no está pendiente.', NO_CAPACITY: 'La clase ya no tiene plaza libre. No se ha confirmado nada.' };
  async function api(body) {
    const o = { credentials: 'same-origin', headers: {} };
    if (body) { o.method = 'POST'; o.body = JSON.stringify(body); Object.assign(o.headers, { 'Content-Type': 'application/json', 'X-TopFitness-Request': '1' }); }
    const r = await fetch('admin_movil.php', o); const j = await r.json().catch(() => ({}));
    if (!r.ok && j.success !== true && !j.code) throw new Error(j.error || 'TEMPORARY_FAILURE'); return j;
  }
  const fecha = f => f.split('-').reverse().join('/');
  const ago = s => s === null ? 'sin señal' : s < 90 ? 'hace ' + s + ' s' : 'hace ' + Math.round(s / 60) + ' min';
  function chip(text, cls) { const c = el('span', text, 'chip ' + (cls || '')); return c; }
  function table(heads, rows, emptyText) {
    if (!rows.length) return el('p', emptyText, 'empty');
    const t = el('table'), th = el('thead'), tr = el('tr'); heads.forEach(h => tr.append(el('th', h))); th.append(tr); t.append(th);
    const tb = el('tbody'); rows.forEach(r => { const row = el('tr'); r.forEach(c => { const td = el('td'); if (c instanceof Node) td.append(c); else td.textContent = c; row.append(td); }); tb.append(row); }); t.append(tb); return t;
  }
  function twoStep(label, confirmLabel, fn) {
    const b = el('button', label, 'secondary'); b.type = 'button'; let armed = false, t = null;
    b.addEventListener('click', async () => {
      if (!armed) { armed = true; b.textContent = confirmLabel; t = setTimeout(() => { armed = false; b.textContent = label; }, 8000); return; }
      clearTimeout(t); b.disabled = true; fail('');
      try { await fn(); } catch (e) { fail('No se ha podido completar. Inténtalo de nuevo.'); b.disabled = false; armed = false; b.textContent = label; }
    });
    return b;
  }
  const INC = {
    PUSH_FAILED: d => `No se pudo entregar un aviso (${({ OFFER: 'plaza libre', REMINDER: 'recordatorio', CLASS_CANCELLED: 'clase cancelada', SCHEDULE_CHANGED: 'cambio de horario', RECEPTION_BOOKING: 'reserva', OFFER_ACCEPTED: 'confirmación', TEST: 'prueba' })[d.kind] || d.kind}). Motivo: ${d.reason || '—'}.`,
    OFFER_UNDELIVERABLE: () => 'Hay una oferta de plaza a alguien sin avisos activos. Llámale: si la quiere, confírmala arriba.',
    OFFER_BLOCKED: () => 'Una persona de la lista de espera no se ha podido identificar, así que no se le ha ofrecido la plaza. Revisa la lista.',
    OFFER_FAILED: d => 'Una oferta no se pudo completar por falta de aforo.', IDENTIFY_REVIEW: () => 'Varias fichas coinciden con los datos de una persona. Revisa las fichas.', IDENTIFY_SOURCE_DOWN: () => 'No se pudo consultar Altas al identificar a alguien (queda como sin ficha).'
  };
  async function cargar() {
    let j; try { j = await api(); } catch (_) { fail('No se pueden cargar los datos. Comprueba la conexión e inténtalo de nuevo.'); return; }
    const s = j.salud; clear($('salud'));
    $('salud').append(chip('Envío de avisos: ' + (s.envio ? 'activado' : 'apagado'), s.envio ? 'ok' : 'warn'), chip('Ofertas de plaza: ' + (s.ofertas ? 'activadas' : 'apagadas'), s.ofertas ? 'ok' : 'warn'),
      chip('Remitente: ' + ago(s.remitente_seg), s.remitente_seg !== null && s.remitente_seg < 60 ? 'ok' : 'warn'), chip('Control de ofertas: ' + ago(s.worker_ofertas_seg), s.worker_ofertas_seg !== null && s.worker_ofertas_seg < 30 ? 'ok' : 'warn'));
    const of = $('ofertas'); clear(of);
    of.append(table(['Persona', 'Clase', 'Hasta', 'Avisos', ''], j.ofertas.map(o => [o.nombre + ' (' + o.telefono + ')', `${o.clase} · ${fecha(o.fecha)} ${o.hora}`, `${o.limite} (${Math.max(0, Math.floor(o.segundos / 60))} min)`, +o.avisos ? 'Sí' : 'NO tiene avisos',
      twoStep('Confirmar plaza', 'Pulsa otra vez: la persona la pide', async () => { const r = await api({ action: 'confirmar_oferta', offer_id: +o.id }); if (r.success) say('Plaza confirmada para ' + o.nombre + '.'); else fail(ERR[r.code] || 'No se ha podido confirmar.'); await cargar(); })]), 'No hay ofertas pendientes.'));
    const inc = $('incidencias'); clear(inc);
    inc.append(table(['Cuándo', 'Persona', 'Qué ha pasado'], j.incidencias.map(i => { let d = {}; try { d = JSON.parse(i.detail_json); } catch (_) {} return [i.created_at.slice(5, 16).replace('-', '/'), i.nombre || '—', (INC[i.action] || (() => i.action))(d)]; }), 'Sin incidencias.'));
    const dv = $('devices'); clear(dv);
    dv.append(table(['Persona', 'Móvil', 'Avisos', 'Última vez', ''], j.devices.map(d => [d.nombre + ' (' + d.telefono + ')', ({ ios: 'iPhone', android: 'Android' })[d.platform] || 'Otro', +d.avisos ? 'Activados y probados' : 'Sin activar', d.last_seen_at ? d.last_seen_at.slice(0, 16) : '—',
      twoStep('Quitar móvil', 'Pulsa otra vez para quitarlo', async () => { await api({ action: 'revocar', device_id: +d.id }); say('Móvil quitado.'); await cargar(); })]), 'Todavía no hay móviles asociados.'));
  }
  $('f-innux').addEventListener('submit', async ev => {
    ev.preventDefault(); fail('');
    try { const r = await api({ action: 'asociar_innux', innux_reference: $('ref').value.trim(), nombre: $('nom').value, telefono: $('tel').value }); if (r.success) { say('Socio asociado. Ya puede identificarse desde su móvil con ese nombre y teléfono.'); $('f-innux').reset(); } else fail('Revisa los datos.'); }
    catch (_) { fail('Revisa la referencia (INNUX:número), el nombre y el teléfono.'); }
  });
  cargar(); setInterval(cargar, 20000);
})();
