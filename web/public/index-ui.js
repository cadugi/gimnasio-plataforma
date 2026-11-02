// Capa de interfaz para la pantalla táctil. No toca la lógica de reservas (index.js):
// solo lee el <select> de horarios y muestra sus opciones como botones grandes.
(() => {
    const $ = (id) => document.getElementById(id);
    const IDLE_MS = 60000;

    // ---------- reloj ----------
    const horaEl = $('reloj-hora');
    const fechaEl = $('reloj-fecha');
    function pintarReloj() {
        const ahora = new Date();
        const opts = { timeZone: 'Europe/Madrid' };
        if (horaEl) horaEl.textContent = ahora.toLocaleTimeString('es-ES', { ...opts, hour: '2-digit', minute: '2-digit' });
        if (fechaEl) fechaEl.textContent = ahora.toLocaleDateString('es-ES', { ...opts, weekday: 'long', day: 'numeric', month: 'long' });
    }
    pintarReloj();
    setInterval(pintarReloj, 15000);

    // ---------- foto de la clase en la cabecera del panel ----------
    const formulario = $('formulario');
    document.addEventListener('click', (e) => {
        const card = e.target.closest && e.target.closest('.card');
        const img = card && card.querySelector('img');
        if (img && formulario) formulario.style.setProperty('--sheet-img', `url("${img.getAttribute('src')}")`);
    }, true);

    // ---------- sesiones como botones ----------
    const select = $('selectHorarios');
    const lista = $('horarios-lista');
    const submit = $('submit');
    if (!select || !lista) return;

    const DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

    function etiquetaDia(iso) {
        const [y, m, d] = iso.split('-').map(Number);
        const fecha = new Date(y, m - 1, d);
        const hoy = new Date();
        const base = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
        const dif = Math.round((fecha - base) / 86400000);
        const nombre = `${DIAS[fecha.getDay()]} ${d} ${MESES[m - 1]}`;
        if (dif === 0) return { rel: 'Hoy', nombre, hoy: true };
        if (dif === 1) return { rel: 'Mañana', nombre, hoy: false };
        return { rel: DIAS[fecha.getDay()], nombre: `${d} ${MESES[m - 1]}`, hoy: false };
    }

    function el(tag, cls, text) {
        const n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
    }

    let pendiente = false;
    function programar() {
        if (pendiente) return;
        pendiente = true;
        requestAnimationFrame(() => { pendiente = false; pintarSesiones(); });
    }

    const tabs = $('dias-tabs');

    function pintarSesiones() {
        const opciones = [...select.options];
        lista.textContent = '';
        if (tabs) tabs.textContent = '';

        if (!opciones.length) {
            const grid = el('div', 'slot-grid');
            for (let i = 0; i < 3; i++) grid.append(el('div', 'slot-skeleton'));
            lista.append(grid);
            lista.setAttribute('aria-busy', 'true');
            actualizarBoton();
            return;
        }
        lista.removeAttribute('aria-busy');

        const reales = opciones.filter((o) => o.dataset.fecha);
        if (!reales.length) {
            lista.append(el('p', 'slots-empty', 'Esta clase no tiene sesiones en los próximos 5 días. Prueba con otra clase.'));
            actualizarBoton();
            return;
        }

        const dias = [...new Set(reales.map((o) => o.dataset.fecha))];
        const sel = select.selectedOptions && select.selectedOptions[0];
        const diaSel = sel && sel.dataset.fecha ? sel.dataset.fecha : dias[0];

        if (tabs) {
            for (const dia of dias) {
                const d = etiquetaDia(dia);
                const t = el('button', 'day-tab');
                t.type = 'button';
                t.setAttribute('role', 'tab');
                t.setAttribute('aria-selected', String(dia === diaSel));
                t.dataset.dia = dia;
                const corto = d.rel === 'Hoy' || d.rel === 'Mañana' ? d.rel : d.rel.slice(0, 3);
                t.append(el('span', 'd1', corto), el('span', 'd2', String(Number(dia.split('-')[2]))));
                tabs.append(t);
            }
        }

        const grid = el('div', 'slot-grid');
        lista.append(grid);
        for (const opt of reales.filter((o) => o.dataset.fecha === diaSel)) {
            const disp = parseInt(opt.dataset.disponibles || '0', 10);
            const cola = parseInt(opt.dataset.cola || '0', 10);
            const completo = disp <= 0;
            const [ini, fin] = (opt.dataset.hora || '').split('-');

            const b = el('button', 'slot' + (completo ? ' full' : ''));
            b.type = 'button';
            b.setAttribute('role', 'radio');
            b.setAttribute('aria-checked', String(opt.selected));
            b.dataset.value = opt.value;

            const t = el('span', 't', ini || '');
            if (fin) t.append(el('i', null, ` – ${fin}`));
            const s = el('span', 's', completo
                ? (cola > 0 ? `Completo · ${cola} en espera` : 'Completo · lista de espera')
                : `${disp} plaza${disp !== 1 ? 's' : ''} libre${disp !== 1 ? 's' : ''}`);
            b.append(t, s);
            grid.append(b);
        }
        actualizarBoton();
    }

    function actualizarBoton() {
        if (!submit) return;
        const opt = select.selectedOptions && select.selectedOptions[0];
        const espera = !!(opt && opt.dataset.fecha && parseInt(opt.dataset.disponibles || '0', 10) <= 0);
        submit.classList.toggle('waitlist', espera);
        submit.textContent = espera ? 'Apuntarme a la lista de espera' : 'Confirmar reserva';
    }

    if (tabs) tabs.addEventListener('click', (e) => {
        const t = e.target.closest('.day-tab');
        if (!t) return;
        const primera = [...select.options].find((o) => o.dataset.fecha === t.dataset.dia);
        if (!primera) return;
        select.value = primera.value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        programar();
    });

    lista.addEventListener('click', (e) => {
        const b = e.target.closest('.slot');
        if (!b) return;
        select.value = b.dataset.value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        for (const x of lista.querySelectorAll('.slot')) x.setAttribute('aria-checked', String(x === b));
        actualizarBoton();
    });

    new MutationObserver(programar).observe(select, { childList: true });
    select.addEventListener('change', programar);
    document.body.classList.add('has-slots');

    // ---------- panel abierto: fondo, cierre por inactividad ----------
    const barra = formulario && formulario.querySelector('.idle-bar');
    let reloj = null;

    function reiniciarInactividad() {
        clearTimeout(reloj);
        if (barra) {
            barra.classList.remove('run');
            void barra.offsetWidth;
            barra.style.setProperty('--idle', IDLE_MS / 1000 + 's');
            barra.classList.add('run');
        }
        reloj = setTimeout(cerrarPorInactividad, IDLE_MS);
    }

    function cerrarPorInactividad() {
        const nombre = $('nombre');
        const tel = $('telefono');
        if (nombre && !nombre.readOnly) nombre.value = '';
        if (tel && !tel.readOnly) tel.value = '';
        if (typeof window.cancelarFormulario === 'function') window.cancelarFormulario();
    }

    function sincronizarPanel() {
        const abierto = formulario.style.display === 'block';
        document.body.classList.toggle('form-open', abierto);
        if (abierto) {
            reiniciarInactividad();
            programar();
        } else {
            clearTimeout(reloj);
            if (barra) barra.classList.remove('run');
        }
    }

    if (formulario) {
        new MutationObserver(sincronizarPanel).observe(formulario, { attributes: true, attributeFilter: ['style'] });
        for (const ev of ['pointerdown', 'keydown', 'input', 'scroll']) {
            formulario.addEventListener(ev, () => {
                if (document.body.classList.contains('form-open')) reiniciarInactividad();
            }, { capture: true, passive: true });
        }
    }
})();
