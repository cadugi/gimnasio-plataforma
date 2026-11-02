// Pantalla grande: reserva en dos pasos (1. día y hora, 2. tus datos) con teclado propio en pantalla.
// Los campos son de solo lectura para que Windows no abra su teclado y tape la información.
(() => {
  const $ = (id) => document.getElementById(id);
  const form = $('formulario');
  if (!form) return;
  const sel = $('selectHorarios'), nombre = $('nombre'), tel = $('telefono');
  const pasoSes = form.querySelector('.paso-sesion'), pasoDat = form.querySelector('.paso-datos');
  const bCont = $('btn-continuar'), bSub = $('submit'), bVol = $('btn-volver'), bAtr = $('btn-atras');
  const kb = $('teclado'), resumen = $('resumen-sesion'), fields = form.querySelector('.fields');
  if (!pasoSes || !pasoDat || !kb) return;

  const DIAS = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
  const MESES = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  const FILAS = [['Q','W','E','R','T','Y','U','I','O','P'], ['A','S','D','F','G','H','J','K','L','Ñ'], ['Z','X','C','V','B','N','M']];
  const ACENTOS = ['Á','É','Í','Ó','Ú','Ü'];
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };

  let paso = 1, activo = 'nombre', abierto = false;
  const modoSesion = () => !!nombre.hidden; // con sesión de WhatsApp los datos ya vienen puestos
  const telDigitos = () => tel.value.replace(/\D/g, '');
  const nombreOk = () => nombre.value.trim().length >= 3;
  const telOk = () => telDigitos().length >= 1 && tel.value !== '0'; // teléfono libre: vale con unas pocas cifras

  const hint = el('p', 'kb-hint');
  if (fields) fields.insertAdjacentElement('afterend', hint);

  // ---------------- pasos ----------------
  function sesionElegida() {
    const o = sel.selectedOptions && sel.selectedOptions[0];
    return o && o.dataset.fecha ? o : null;
  }

  function renderPaso() {
    const sesion = modoSesion();
    const p2 = paso === 2 && !sesion;
    form.classList.toggle('paso-2', p2);
    pasoSes.hidden = p2;
    pasoDat.hidden = !p2;
    bCont.hidden = p2 || sesion;
    bSub.hidden = !(p2 || sesion);
    bVol.hidden = p2;
    bAtr.hidden = !p2;
    actualizarBotones();
    if (p2) { pintarResumen(); pintarTeclado(); pintarCampos(); }
  }

  function actualizarBotones() {
    bCont.disabled = !sesionElegida();
    if (paso === 2 && !modoSesion()) {
      bSub.disabled = !(nombreOk() && telOk());
      hint.textContent = !nombreOk() ? 'Escribe tu nombre y apellidos' : !telOk() ? 'Escribe tu teléfono' : 'Todo listo. Pulsa «Confirmar reserva»';
      hint.classList.toggle('ok', nombreOk() && telOk());
    }
  }

  function pintarResumen() {
    resumen.textContent = '';
    const o = sesionElegida();
    if (!o) return;
    const [, fecha, hora, clase] = o.value.split('|');
    const [y, m, d] = fecha.split('-').map(Number);
    const dia = new Date(y, m - 1, d);
    const t = el('div', 'res-texto');
    t.append(el('strong', null, String(clase || '').toUpperCase()), el('span', null, `${DIAS[dia.getDay()]} ${d} de ${MESES[m - 1]} · ${hora}`));
    const cambiar = el('button', 'res-cambiar', 'Cambiar'); cambiar.type = 'button';
    cambiar.addEventListener('click', () => { paso = 1; renderPaso(); });
    resumen.append(t, cambiar);
  }

  bCont.addEventListener('click', () => { if (!sesionElegida()) return; paso = 2; activo = nombre.value ? 'telefono' : 'nombre'; renderPaso(); });
  bAtr.addEventListener('click', () => { paso = 1; renderPaso(); });
  sel.addEventListener('change', actualizarBotones);
  new MutationObserver(actualizarBotones).observe(sel, { childList: true });

  // al abrir el panel siempre se empieza por el paso 1
  new MutationObserver(() => {
    const ahora = form.style.display === 'block';
    if (ahora && !abierto) { paso = 1; activo = 'nombre'; }
    abierto = ahora;
    if (ahora) renderPaso();
  }).observe(form, { attributes: true, attributeFilter: ['style'] });

  // ---------------- teclado ----------------
  function tecla(texto, accion, cls) {
    const b = el('button', 'kkey' + (cls ? ' ' + cls : ''), texto);
    b.type = 'button'; b.dataset.a = accion; b.tabIndex = -1;
    return b;
  }

  function pintarTeclado() {
    kb.textContent = '';
    kb.dataset.modo = activo === 'nombre' ? 'letras' : 'numeros';
    if (activo === 'nombre') {
      const acc = el('div', 'krow krow-acc');
      ACENTOS.forEach((c) => acc.append(tecla(c, 'l:' + c, 'k-acento')));
      kb.append(acc);
      FILAS.forEach((fila, i) => {
        const r = el('div', 'krow krow-letras');
        fila.forEach((c) => r.append(tecla(c, 'l:' + c)));
        if (i === 2) r.append(tecla('Borrar', 'borrar', 'k-borrar k-span3'));
        kb.append(r);
      });
      const bajo = el('div', 'krow krow-letras');
      bajo.append(tecla('Espacio', 'espacio', 'k-espacio k-span7'), tecla('Siguiente', 'siguiente', 'k-accion k-span3'));
      kb.append(bajo);
    } else {
      const grid = el('div', 'knum');
      ['1','2','3','4','5','6','7','8','9'].forEach((n) => grid.append(tecla(n, 'n:' + n)));
      grid.append(tecla('Borrar', 'borrar', 'k-borrar'), tecla('0', 'n:0'), tecla('‹ Nombre', 'nombre', 'k-sec'));
      kb.append(grid);
    }
  }

  function pintarCampos() {
    for (const f of form.querySelectorAll('.field')) {
      f.classList.toggle('is-active', f.dataset.campo === activo);
      const ok = f.dataset.campo === 'nombre' ? nombreOk() : telOk();
      f.classList.toggle('is-ok', ok);
    }
  }

  function cambiarCampo(campo) {
    activo = campo; pintarTeclado(); pintarCampos();
  }

  function cambio(input) {
    input.dispatchEvent(new Event('input', { bubbles: true }));
    actualizarBotones(); pintarCampos();
  }

  function letra(ch) {
    const v = nombre.value;
    if (v.length >= 100) return;
    const inicio = v === '' || v.endsWith(' ') || v.endsWith('-');
    nombre.value = v + (inicio ? ch.toUpperCase() : ch.toLowerCase());
    cambio(nombre);
  }

  function numero(n) {
    if (tel.value.length >= 15) return;
    tel.value += n; cambio(tel);
  }

  function borrar() {
    const inp = activo === 'nombre' ? nombre : tel;
    inp.value = inp.value.slice(0, -1); cambio(inp);
  }

  function espacio() {
    const v = nombre.value;
    if (!v || v.endsWith(' ') || v.length >= 100) return;
    nombre.value = v + ' '; cambio(nombre);
  }

  function siguiente() { if (nombre.value.trim()) cambiarCampo('telefono'); }

  kb.addEventListener('pointerdown', (e) => e.preventDefault());
  kb.addEventListener('click', (e) => {
    const b = e.target.closest('.kkey');
    if (!b) return;
    const [tipo, valor] = b.dataset.a.split(':');
    if (tipo === 'l') letra(valor);
    else if (tipo === 'n') numero(valor);
    else if (tipo === 'borrar') borrar();
    else if (tipo === 'espacio') espacio();
    else if (tipo === 'siguiente') siguiente();
    else if (tipo === 'nombre') cambiarCampo('nombre');
  });

  for (const f of form.querySelectorAll('.field')) f.addEventListener('click', () => cambiarCampo(f.dataset.campo));

  // teclado físico (por si se conecta uno)
  document.addEventListener('keydown', (e) => {
    if (!abierto || paso !== 2 || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'Backspace') { borrar(); e.preventDefault(); return; }
    if (e.key === 'Enter') { if (activo === 'nombre') siguiente(); else if (!bSub.disabled) bSub.click(); e.preventDefault(); return; }
    if (e.key === ' ' && activo === 'nombre') { espacio(); e.preventDefault(); return; }
    if (e.key.length !== 1) return;
    if (activo === 'telefono' && /\d/.test(e.key)) { numero(e.key); e.preventDefault(); }
    else if (activo === 'nombre' && /^[\p{L}'-]$/u.test(e.key)) { letra(e.key); e.preventDefault(); }
  });

  new MutationObserver(renderPaso).observe(nombre, { attributes: true, attributeFilter: ['hidden'] });
  renderPaso();
})();
