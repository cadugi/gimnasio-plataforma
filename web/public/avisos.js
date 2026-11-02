'use strict';
/* Asistente «Avisos de mis clases». Sin frameworks. Las confirmaciones y los errores no desaparecen solos. */
(() => {
  const $ = id => document.getElementById(id);
  const ua = navigator.userAgent || '';
  const store = { get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }, del(k) { try { localStorage.removeItem(k); } catch (_) {} } };

  /* Pantalla compartida: se indica de forma EXPLÍCITA (?modo=compartido una vez en esa pantalla; ?modo=personal lo quita). Nunca por el tamaño. */
  const q = new URLSearchParams(location.search).get('modo');
  if (q === 'compartido') store.set('tf_modo', 'compartido'); else if (q === 'personal') store.del('tf_modo');
  const compartida = store.get('tf_modo') === 'compartido';

  const isIOS = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/.test(ua);
  const platform = isIOS ? 'ios' : isAndroid ? 'android' : 'other';
  const iosVer = (m => m ? [+m[1], +m[2]] : [0, 0])(ua.match(/OS (\d+)[_.](\d+)/));
  const iosOld = isIOS && (iosVer[0] < 16 || (iosVer[0] === 16 && iosVer[1] < 4)) && iosVer[0] !== 0;
  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const inAppBrowser = /FBAN|FBAV|Instagram|Line\/|MicroMessenger|; wv\)/.test(ua);
  const iosNotSafari = isIOS && /CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
  const pushOK = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

  let csrf = '', info = null, avisos = null, vapid = '', envioActivo = false, installEvt = null, probando = false;

  const say = (t) => { const e = $('msg'); e.textContent = t; e.hidden = !t; };
  const fail = (t) => { const e = $('err'); e.textContent = t; e.hidden = !t; if (t) e.scrollIntoView({ block: 'nearest' }); };
  const ERR = {
    INVALID_DATA: 'Revisa el nombre y el teléfono. El teléfono tiene 9 cifras.', TOO_MANY_ATTEMPTS: 'Has probado muchas veces. Espera unos minutos y vuelve a intentarlo.',
    ACCESS_DENIED: 'Este móvil ya no está vinculado. Escribe tus datos otra vez.', INVALID_SUBSCRIPTION: 'Este móvil no admite los avisos. Prueba desde otro navegador.',
    PUSH_NOT_ACTIVE: 'Primero activa los avisos.', TEST_NOT_SENT: 'Todavía no hemos podido enviar el aviso de prueba.', CSRF_REQUIRED: 'La página ha caducado. Recárgala e inténtalo otra vez.'
  };
  const errText = c => ERR[c] || 'Ahora mismo no podemos hacerlo. Inténtalo de nuevo en un momento.';

  async function api(url, body) {
    const o = { credentials: 'same-origin', headers: {} };
    if (body) { o.method = 'POST'; o.body = JSON.stringify(body); Object.assign(o.headers, { 'Content-Type': 'application/json', 'X-TopFitness-Request': '1', 'X-CSRF-Token': csrf, 'X-TF-Modo': compartida ? 'compartido' : 'personal' }); }
    let r; try { r = await fetch(url, o); } catch (_) { throw new Error('OFFLINE'); }
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw new Error(j.error || j.code || 'TEMPORARY_FAILURE');
    return j;
  }
  const guard = async (btn, fn) => { btn.disabled = true; fail(''); try { await fn(); } catch (e) { fail(e.message === 'OFFLINE' ? 'No hay conexión a internet. Inténtalo cuando vuelva.' : errText(e.message)); } finally { btn.disabled = false; } };
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text) e.textContent = text; if (cls) e.className = cls; return e; };
  const btn = (text, cls, fn) => { const b = el('button', text, cls); b.type = 'button'; b.addEventListener('click', () => guard(b, fn)); return b; };
  const clear = n => { while (n.firstChild) n.removeChild(n.firstChild); };

  function guia(items) {
    const ol = el('ol', '', 'guia');
    items.forEach(([img, alt, cap]) => { const li = el('li'), fig = el('figure'), im = el('img'); im.src = 'img/guia/' + img + '.svg'; im.alt = alt; im.width = 280; im.height = 368; fig.append(im, el('figcaption', cap)); li.append(fig); ol.append(li); });
    return ol;
  }
  const IOS = [['ios-1-safari', 'Icono azul de Safari', 'Abre esta página con Safari, la brújula azul.'], ['ios-2-compartir', 'Botón Compartir, abajo en el centro', 'Pulsa el botón Compartir: un cuadrado con una flecha hacia arriba.'],
    ['ios-3-anadir', 'Opción Añadir a pantalla de inicio', 'Desliza hacia arriba y pulsa «Añadir a pantalla de inicio». Luego pulsa «Añadir».'], ['ios-4-icono', 'Icono de Top Fitness en la pantalla de inicio', 'Cierra Safari y abre Top Fitness desde el icono nuevo.']];
  const AND = [['android-1-menu', 'Los tres puntos del menú, arriba a la derecha', 'Pulsa los tres puntitos de arriba a la derecha.'], ['android-2-instalar', 'Opción Instalar aplicación', 'Pulsa «Instalar aplicación» o «Añadir a pantalla de inicio».'],
    ['android-3-icono', 'Icono de Top Fitness en la pantalla de inicio', 'Abre Top Fitness desde el icono nuevo.']];

  /* ---------- paso 1 ---------- */
  function paso1(done) {
    const b = $('b1'); clear(b);
    if (done) { b.append(el('p', standalone ? 'Top Fitness ya está en tu móvil.' : 'Marcado como hecho.')); return; }
    if (isIOS) {
      if (iosOld) { b.append(el('p', 'Para recibir avisos, tu iPhone necesita la versión 16.4 de iOS o una más nueva. Actualízalo en Ajustes → General → Actualización de software.')); return; }
      if (inAppBrowser || iosNotSafari) b.append(el('p', 'Primero copia la dirección de esta página y ábrela con Safari, la brújula azul.', 'msg'));
      b.append(el('p', 'Sigue estos pasos. Es solo una vez.'), guia(IOS), el('p', 'Después, abre Top Fitness desde el icono. Allí te pediremos tus datos otra vez: es normal.'));
      return;
    }
    if (installEvt) b.append(btn('Añadir Top Fitness al móvil', 'primary', async () => { installEvt.prompt(); const c = await installEvt.userChoice; installEvt = null; if (c.outcome === 'accepted') { store.set('tf_instalado', '1'); say('Listo. Busca el icono de Top Fitness en tu pantalla de inicio.'); render(); } else say('De acuerdo. Puedes añadirlo más tarde.'); }));
    else { b.append(el('p', platform === 'android' ? 'Sigue estos pasos:' : 'En tu navegador, busca la opción «Instalar» o «Añadir a pantalla de inicio» del menú.'), platform === 'android' ? guia(AND) : el('span')); }
    b.append(btn('Ya lo he hecho, o prefiero seguir sin añadirlo', 'secondary', async () => { store.set('tf_instalado', '1'); render(); }));
  }

  /* ---------- paso 2 ---------- */
  function ayudaPermisos() {
    const b = $('b2'); b.append(el('p', 'Los avisos están bloqueados en este móvil. Para activarlos:', 'msg error'));
    b.append(el('p', isIOS ? 'Abre Ajustes del iPhone → Notificaciones → Top Fitness → activa «Permitir notificaciones».' : 'Pulsa el candado junto a la dirección de la web → Permisos → Notificaciones → Permitir.'));
    b.append(btn('Ya lo he cambiado, comprobar', 'secondary', async () => render()));
  }
  function paso2(done) {
    const b = $('b2'); clear(b);
    if (done) { b.append(el('p', 'Los avisos están activados en este móvil.')); return; }
    if (!pushOK || (isIOS && !standalone)) {
      b.append(el('p', isIOS && !standalone ? 'En iPhone, los avisos solo funcionan desde el icono de Top Fitness. Haz primero el paso 1 y abre la web desde el icono.' : 'Este navegador no puede recibir avisos. Prueba con Chrome, o desde el icono de Top Fitness.', 'msg error'));
      return;
    }
    if (Notification.permission === 'denied') { ayudaPermisos(); return; }
    b.append(el('p', 'Te avisaremos 2 horas antes de tu clase y cuando haya una plaza libre. Cuando pulses el botón, el móvil te preguntará si permites los avisos: elige «Permitir».'),
      el('img', '', ''), btn('Activar avisos', 'primary', activar));
    const im = b.querySelector('img'); im.src = 'img/guia/permisos.svg'; im.alt = 'Ventana del móvil que pregunta si permites los avisos: hay que pulsar Permitir'; im.width = 240; im.height = 316; im.style.cssText = 'display:block;margin:12px auto;border-radius:14px;max-width:70%;height:auto';
  }
  const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const fromB64u = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), c => c.charCodeAt(0));
  async function activar() {
    const perm = await Notification.requestPermission();            // solo como respuesta a la pulsación
    if (perm !== 'granted') { render(); return; }
    if (!vapid) throw new Error('TEMPORARY_FAILURE');
    const reg = await navigator.serviceWorker.register('sw.js', { scope: '/reservas/' });
    await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: fromB64u(vapid) });
    const r = await api('avisos.php', { action: 'suscribir', endpoint: sub.endpoint, keys: { p256dh: b64u(sub.getKey('p256dh')), auth: b64u(sub.getKey('auth')) } });
    avisos = r.avisos; say('Avisos activados. Falta comprobar que te llegan: haz el paso 3.'); render();
  }

  /* ---------- paso 3 ---------- */
  function paso3(done) {
    const b = $('b3'); clear(b);
    if (done) { b.append(el('p', 'Hemos comprobado que recibes los avisos. Esto confirma solo esta prueba; si un día dejas de recibirlos, vuelve aquí.')); return; }
    if (!avisos || !avisos.subscribed) { b.append(el('p', 'Disponible cuando actives los avisos.')); return; }
    if (!envioActivo) { b.append(el('p', 'El envío de avisos todavía no está abierto para todos. Lo activaremos pronto; no tienes que hacer nada más ahora.', 'msg')); return; }
    if (avisos.test_sent) {
      b.append(el('p', 'Te hemos enviado un aviso de prueba. ¿Lo has recibido en el móvil?', 'msg'),
        btn('Sí, lo he recibido', 'primary', async () => { const r = await api('avisos.php', { action: 'confirmar_prueba' }); avisos = r.avisos; say('Perfecto. Avisos activados.'); render(); }),
        btn('No lo he recibido', 'secondary', async () => { fail('Comprueba que el móvil no está en silencio ni en «No molestar» y que Top Fitness tiene permiso de avisos. Luego envía otro aviso de prueba.'); }),
        btn('Enviar otro aviso de prueba', 'secondary', enviarPrueba));
      return;
    }
    b.append(el('p', probando ? 'Enviando el aviso de prueba. Puede tardar unos segundos…' : 'Pulsa el botón. Te llegará un aviso al móvil.'));
    if (!probando) b.append(btn('Enviar aviso de prueba', 'primary', enviarPrueba));
  }
  async function enviarPrueba() {
    const r = await api('avisos.php', { action: 'probar' }); avisos = r.avisos; probando = true; render();
    for (let i = 0; i < 20 && !avisos.test_sent; i++) { await new Promise(res => setTimeout(res, 3000)); const g = await api('avisos.php'); avisos = g.avisos; }
    probando = false; if (!avisos.test_sent) fail('El aviso de prueba todavía no ha salido. Espera un minuto y pulsa «Enviar aviso de prueba» otra vez.'); render();
  }

  /* ---------- pantalla ---------- */
  function render() {
    $('compartida').hidden = !compartida;
    $('s-ident').hidden = !!info || compartida; $('s-wiz').hidden = !info || compartida;
    if (compartida || !info) return;
    $('quien').textContent = info.nombre;
    const instalado = standalone || store.get('tf_instalado') === '1';
    const permiso = pushOK && Notification.permission === 'granted';
    const d1 = instalado, d2 = !!(avisos && avisos.subscribed && permiso), d3 = !!(avisos && avisos.test_confirmed);
    const cur = !d1 ? 1 : !d2 ? 2 : !d3 ? 3 : 0;
    [[1, d1], [2, d2], [3, d3]].forEach(([n, d]) => { const s = $('p' + n); s.className = 'step' + (d ? ' done' : n === cur ? ' current' : ' later'); });
    paso1(d1); paso2(d2); paso3(d3);
    const chip = $('chip'), ok = d2 && d3;
    chip.textContent = ok ? 'Avisos activados' : (!avisos || avisos.state === 'NONE') ? 'Activar avisos' : 'Revisar avisos';
    chip.className = 'chip ' + (ok ? 'ok' : 'warn');
    $('b-desact').hidden = !(avisos && avisos.subscribed);
  }
  function lista(items) {
    const ul = $('lista'); clear(ul); const T = { REMINDER: 'Recordatorio', OFFER: 'Plaza libre', OFFER_ACCEPTED: 'Plaza confirmada', CLASS_CANCELLED: 'Clase cancelada', SCHEDULE_CHANGED: 'Cambio de horario', RECEPTION_BOOKING: 'Reserva en recepción' };
    const S = { ENVIADO: 'Enviado a tu móvil', NO_ENVIADO: 'No se pudo enviar', CADUCADO: 'Caducó antes de enviarse', PENDIENTE: 'Pendiente de enviar' };
    (items || []).forEach(i => ul.append(el('li', `${T[i.kind] || 'Aviso'}${i.clase ? ' · ' + i.clase : ''}${i.fecha ? ' · ' + i.fecha.split('-').reverse().join('/') : ''}${i.hora ? ' ' + i.hora : ''} — ${S[i.estado] || ''}`)));
    $('mis').hidden = !items || !items.length;
  }
  async function cargar() {
    if (compartida) { render(); return; }
    const e = await api('movil.php');
    if (!e.linked) { info = null; render(); return; }
    info = e; csrf = e.csrf;
    const a = await api('avisos.php'); avisos = a.avisos; vapid = a.vapid_public; envioActivo = !!a.envio_activo; lista(a.mis_avisos);
    render();
  }

  $('f-ident').addEventListener('submit', ev => { ev.preventDefault(); guard($('b-ident'), async () => {
    const r = await api('movil.php', { action: 'identificar', nombre: $('nombre').value, telefono: $('telefono').value, plataforma: platform });
    if (!r.linked) throw new Error('INVALID_DATA');
    if ($('recordar').checked) store.set('tf_recordar', '1'); else store.del('tf_recordar');
    say('Datos guardados en este móvil.'); await cargar();
  }); });
  $('b-salir').addEventListener('click', e => guard(e.currentTarget, async () => { await api('movil.php', { action: 'olvidar' }); info = null; avisos = null; store.del('tf_recordar'); say('Has cerrado la sesión en este móvil.'); render(); }));
  $('b-desact').addEventListener('click', e => guard(e.currentTarget, async () => {
    try { const reg = await navigator.serviceWorker.getRegistration('/reservas/'); const s = reg && await reg.pushManager.getSubscription(); if (s) await s.unsubscribe(); } catch (_) {}
    const r = await api('avisos.php', { action: 'desactivar' }); avisos = r.avisos; say('Avisos desactivados.'); render();
  }));
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installEvt = e; if (info) render(); });
  if (pushOK && !compartida) navigator.serviceWorker.register('sw.js', { scope: '/reservas/' }).catch(() => {});
  cargar().catch(e => { fail(e.message === 'OFFLINE' ? 'No hay conexión a internet.' : errText(e.message)); render(); });
})();
