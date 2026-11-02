'use strict';
/* Pantalla de una oferta de plaza. Consultar no cambia nada; aceptar y rechazar piden una pulsación explícita. Nada desaparece solo. */
(() => {
  const $ = id => document.getElementById(id);
  const token = (location.hash || '').replace(/^#/, '');
  const DAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const say = t => { const e = $('msg'); e.textContent = t; e.hidden = !t; };
  const fail = t => { const e = $('err'); e.textContent = t; e.hidden = !t; };
  const show = id => ['oferta', 'seguro'].forEach(x => { $(x).hidden = x !== id; });
  const FIN = {
    ACCEPTED: ['Plaza confirmada. Te esperamos en clase.', false], DECLINED: ['Has dejado la plaza. Ya no estás en la lista de espera de esta clase.', false],
    EXPIRED: ['Ha pasado el tiempo para responder. La plaza se ha ofrecido a otra persona.', true], CANCELLED: ['Esta clase se ha cancelado, o la oferta ya no está disponible.', true],
    FAILED: ['No hemos podido darte la plaza. Habla con recepción.', true], CLOSED: ['Esta oferta ya no está disponible.', true]
  };
  const final = estado => { show(''); const [t, bad] = FIN[estado] || FIN.CLOSED; (bad ? fail : say)(t); $('fin').hidden = false; $('b-ok').disabled = $('b-no').disabled = true; };
  const ERR = { OFFER_NOT_FOUND: 'Este enlace no es válido. Abre el aviso que te enviamos al móvil.', TOO_MANY_ATTEMPTS: 'Demasiados intentos. Espera unos minutos.' };
  const errText = c => ERR[c] || 'Ahora mismo no podemos hacerlo. Inténtalo de nuevo en un momento.';

  async function call(method, body) {
    const o = { method, credentials: 'same-origin', headers: {} };
    if (method === 'GET') o.headers['X-Offer-Token'] = token; else { o.body = JSON.stringify(Object.assign({ token }, body)); Object.assign(o.headers, { 'Content-Type': 'application/json', 'X-TopFitness-Request': '1' }); }
    let r; try { r = await fetch('oferta.php', o); } catch (_) { throw { code: 'OFFLINE' }; }
    const j = await r.json().catch(() => ({}));
    if (!r.ok && !j.estado) throw { code: j.error || 'TEMPORARY_FAILURE' };
    return j;
  }
  const guard = async (b, fn) => { b.disabled = true; fail(''); try { await fn(); } catch (e) { fail(e.code === 'OFFLINE' ? 'No hay conexión. No se ha confirmado nada. Inténtalo cuando vuelva internet.' : errText(e.code)); } finally { if (!b.dataset.done) b.disabled = false; } };

  $('b-ok').addEventListener('click', e => guard(e.currentTarget, async () => { const j = await call('POST', { action: 'aceptar' }); if (j.estado === 'ACCEPTED') { $('b-ok').dataset.done = '1'; final('ACCEPTED'); } else final(j.estado === 'FAILED' ? 'FAILED' : j.code === 'OFFER_EXPIRED' ? 'EXPIRED' : j.code === 'SESSION_CANCELLED' ? 'CANCELLED' : 'CLOSED'); }));
  $('b-no').addEventListener('click', () => { show('seguro'); $('b-si').focus(); });
  $('b-volver').addEventListener('click', () => { show('oferta'); $('b-ok').focus(); });
  $('b-si').addEventListener('click', e => guard(e.currentTarget, async () => { const j = await call('POST', { action: 'rechazar' }); $('b-si').dataset.done = '1'; final(j.estado === 'DECLINED' ? 'DECLINED' : 'CLOSED'); }));

  // Si llega otro aviso mientras esta pantalla sigue abierta, la dirección cambia: se vuelve a cargar con la oferta nueva.
  window.addEventListener('hashchange', () => location.reload());

  (async () => {
    if (!/^[a-f0-9]{64}$/.test(token)) { fail(ERR.OFFER_NOT_FOUND); $('fin').hidden = false; return; }
    try {
      const j = await call('GET');
      const d = new Date(j.fecha + 'T12:00:00');
      $('clase').textContent = j.clase; $('cuando').textContent = `${DAYS[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1} a las ${j.hora}`;
      $('limite').textContent = `Tienes hasta las ${j.limite} para responder.`;
      if (j.estado === 'PENDING') show('oferta'); else final(j.estado);
    } catch (e) { fail(e.code === 'OFFLINE' ? 'No hay conexión a internet. Inténtalo cuando vuelva.' : errText(e.code)); $('fin').hidden = false; }
  })();
})();
