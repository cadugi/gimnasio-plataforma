(()=>{const original=window.fetch.bind(window);window.fetch=(url,options={})=>{const headers=new Headers(options.headers||{});headers.set('X-TopFitness-Request','1');return original(url,{...options,headers});};})();

// ==================== AVISOS Y CONFIRMACIONES PROPIOS ====================
function cerrarDialogoPropio(id) {
    const m = document.getElementById(id);
    if (m) m.remove();
}

function mostrarAviso(mensaje, titulo) {
    cerrarDialogoPropio('aviso-modal');
    const modal = document.createElement('div');
    modal.id = 'aviso-modal';
    modal.className = 'modal';
    modal.setAttribute('role', 'alertdialog');
    modal.setAttribute('aria-modal', 'true');
    const caja = document.createElement('div');
    caja.className = 'modal-content modal-error';
    const h = document.createElement('h2');
    h.textContent = titulo || (/^error|no se pudo|inv[aá]lido/i.test(String(mensaje)) ? 'Algo ha salido mal' : 'Aviso');
    const p = document.createElement('p');
    p.className = 'aviso-texto';
    p.textContent = String(mensaje);
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn btn-primary';
    b.textContent = 'Entendido';
    b.addEventListener('click', () => modal.remove());
    caja.append(h, p, b);
    modal.append(caja);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    document.body.append(modal);
    b.focus();
}

function confirmarAccion(titulo, texto, textoOk) {
    return new Promise((resolve) => {
        cerrarDialogoPropio('confirmar-modal');
        const modal = document.createElement('div');
        modal.id = 'confirmar-modal';
        modal.className = 'modal';
        modal.setAttribute('role', 'alertdialog');
        modal.setAttribute('aria-modal', 'true');
        const caja = document.createElement('div');
        caja.className = 'modal-content modal-delete';
        const h = document.createElement('h2');
        h.textContent = titulo;
        const p = document.createElement('p');
        p.textContent = texto || '';
        const fila = document.createElement('div');
        fila.className = 'modal-buttons';
        const ok = document.createElement('button');
        ok.type = 'button';
        ok.className = 'btn btn-danger';
        ok.textContent = textoOk || 'Sí, continuar';
        const no = document.createElement('button');
        no.type = 'button';
        no.className = 'btn btn-secondary';
        no.textContent = 'Cancelar';
        const fin = (v) => { modal.remove(); resolve(v); };
        ok.addEventListener('click', () => fin(true));
        no.addEventListener('click', () => fin(false));
        modal.addEventListener('click', (e) => { if (e.target === modal) fin(false); });
        fila.append(ok, no);
        caja.append(h, p, fila);
        modal.append(caja);
        document.body.append(modal);
        no.focus();
    });
}

// Escapa texto antes de meterlo en HTML (nombres, teléfonos, clases...)
function esc(valor) {
    return String(valor ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function errorAmigable(codigo) {
    const textos = {
        CLASE_CANCELADA: 'Esta clase está cancelada ese día. Reactívala si quieres apuntar a alguien.',
        YA_INSCRITO: 'Esa persona ya está apuntada a esta clase ese día. No se apunta dos veces. (Si lo que quieres es cerrar la clase, usa «Cancelar clase».)',
        AFORO_COMPLETO: 'La clase está completa.',
        WAITLIST_IDENTITY_CONFLICT: 'Ya hay otra persona en espera con este teléfono. Comprueba el nombre y el teléfono; no se ha añadido ni cambiado ninguna persona.',
        PARAMS: 'Revisa el nombre y el teléfono.',
        WAITLIST_REQUIRES_NOTICES: 'Para entrar en la lista de espera esa persona debe tener los avisos activados en su móvil (y haber comprobado el aviso de prueba). Pídele que abra la web con su móvil y pulse «Activar avisos de mis clases».',
        WAITLIST_OTHER_DATE: 'Esa persona ya está en la lista de espera de esta clase en otro día.',
        SERVICE_ERROR: 'El servidor no ha podido completar la acción. Inténtalo de nuevo.',
        REQUEST_NOT_ALLOWED: 'Recarga la página e inténtalo de nuevo.'
    };
    return textos[codigo] || ('No se ha podido completar la acción' + (codigo ? ' (' + codigo + ')' : '') + '.');
}

// Sustituye las ventanas de aviso del navegador por las propias
window.alert = (mensaje) => mostrarAviso(mensaje);
// ==================== ESTADO GLOBAL ====================
const admin = {
    horarioId: null,
    clase: null,
    hora: null,
    fechaISO: null
};

// ==================== FUNCIONES DE FECHA ====================
function normalizarFecha(fechaStr) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(fechaStr)) return fechaStr;

    if (/^\d{2}\/\d{2}\/\d{4}$/.test(fechaStr)) {
        const [dd, mm, yyyy] = fechaStr.split("/");
        return `${yyyy}-${mm}-${dd}`;
    }

    return new Date().toISOString().slice(0, 10);
}
function normalizarHora(horaStr) {
    if (!horaStr) return "";
    horaStr = horaStr.trim();
    
    // Si ya tiene formato correcto (HH:MM-HH:MM)
    if (/^\d{2}:\d{2}-\d{2}:\d{2}$/.test(horaStr)) {
        return horaStr;
    }
    
    // Intenta extraer dos horas del formato flexible
    let match = horaStr.match(/(\d{1,2}):?(\d{2})\s*[-:\s]\s*(\d{1,2}):?(\d{2})/);
    
    if (match) {
        const h1 = parseInt(match[1]);
        const m1 = parseInt(match[2]);
        const h2 = parseInt(match[3]);
        const m2 = parseInt(match[4]);
        
        if (h1 >= 0 && h1 <= 23 && m1 >= 0 && m1 <= 59 &&
            h2 >= 0 && h2 <= 23 && m2 >= 0 && m2 <= 59) {
            return `${String(h1).padStart(2, '0')}:${String(m1).padStart(2, '0')}-${String(h2).padStart(2, '0')}:${String(m2).padStart(2, '0')}`;
        }
    }
    return "";
}

function getFechaISO() {
    const el = document.getElementById('fecha');
    if (el && el.value) return normalizarFecha(el.value);
    return new Date().toISOString().slice(0, 10);
}

// ==================== NOTIFICACIONES ====================
function notificarExito(mensaje) {
    if (typeof mostrarModalExito === 'function') {
        mostrarModalExito(mensaje);
    } else {
        alert(mensaje);
    }
}

function mostrarModalExito(mensaje) {
    const modal = document.getElementById('modal-exito');
    if (!modal) return;
    const texto = document.getElementById('modal-mensaje');
    if (texto) texto.textContent = mensaje;
    modal.style.display = 'flex';
    setTimeout(() => {
        modal.style.display = 'none';
    }, 2500);
}

// ==================== REFRESCO DE UI ====================
function refreshAdminUI() {
    try {
        const activeTabBtn = document.querySelector('.tab-button.active');
        const activeTab = activeTabBtn ? activeTabBtn.dataset.tab : null;

        if (activeTab === 'gestion-horarios' && typeof cargarHorarios === 'function') {
            cargarHorarios();
        }

        if (activeTab === 'inscripciones') {
            const fechaInput = document.getElementById('fecha');
            let diaSemana = null;
            if (fechaInput && fechaInput.value) {
                const d = new Date(normalizarFecha(fechaInput.value));
                diaSemana = d.toLocaleString('es-ES', { weekday: 'long' }).toLowerCase();
            } else {
                const d = new Date();
                diaSemana = d.toLocaleString('es-ES', { weekday: 'long' }).toLowerCase();
            }

            if (typeof obtenerHorariosDia === 'function' && diaSemana) {
                obtenerHorariosDia(diaSemana);
            }

            const activo = document.querySelector('#menu button.active');
            if (activo) {
                const horarioId = activo.id;
                const clase = activo.dataset.clase || '';
                const hora = activo.dataset.hora || '';
                const fechaISO = getFechaISO();
                obtenerInscripciones(fechaISO, horarioId, clase, hora);
            }
        }
    } catch (e) {
        console.warn('refreshAdminUI error:', e);
    }
}

// ==================== INICIALIZACIÓN ====================
document.addEventListener('DOMContentLoaded', () => {
    let fechaSeleccionada = new Date();
    const fechaInput = document.getElementById('fecha');
    if (fechaInput) fechaInput.valueAsDate = fechaSeleccionada;
    let diaSemana = fechaSeleccionada.toLocaleString('es-ES', { weekday: 'long' }).toLowerCase();
    if (typeof obtenerHorariosDia === 'function') obtenerHorariosDia(diaSemana);

    if (fechaInput) {
        fechaInput.addEventListener('change', async (event) => {
            fechaSeleccionada = new Date(normalizarFecha(event.target.value));
            diaSemana = fechaSeleccionada.toLocaleString('es-ES', { weekday: 'long' }).toLowerCase();
            await obtenerHorariosDia(diaSemana);
        });
    }

    cargarHorarios();
});

// ==================== OBTENCIÓN DE DATOS ====================
async function obtenerHorariosDia(dia) {
    try {
        const response = await fetch(`obtener_horarios_dia.php?dia=${encodeURIComponent(dia)}`);
        if (!response.ok) throw new Error('Error al obtener los horarios');
        const horarios = await response.json();
        mostrarMenu(horarios);
    } catch (error) {
        console.error('Error obtenerHorariosDia:', error);
        alert('Error al cargar los horarios del día');
    }
}

async function obtenerInscripciones(fecha, horario_id, clase, hora) {
    try {
        if (!horario_id || horario_id === 'nuevo') {
            alert('Por favor selecciona un horario válido');
            return;
        }
        
        const fechaISO = normalizarFecha(fecha);
        const response = await fetch(`obtener_inscripciones.php?fecha=${encodeURIComponent(fechaISO)}&horario_id=${encodeURIComponent(horario_id)}`);
        if (!response.ok) throw new Error('Error al obtener las inscripciones');
        const inscripciones = await response.json();
        mostrarInscripciones(inscripciones, clase, hora, horario_id);
    } catch (error) {
        console.error('Error obtenerInscripciones:', error);
        alert('Error al cargar las inscripciones');
    }
}

async function obtenerLimiteInscripciones(horario_id) {
    try {
        const response = await fetch(`obtener_limite_inscripciones.php?horario_id=${horario_id}`);
        if (!response.ok) throw new Error('Error al obtener el límite');
        const data = await response.json();
        return data.limite || 0;
    } catch (error) {
        console.error('Error obtenerLimiteInscripciones:', error);
        return 0;
    }
}

// ==================== MOSTRAR MENÚ DE HORARIOS ====================
function mostrarMenu(horarios) {
    const menu = document.getElementById('menu');
    if (!menu) return;
    menu.innerHTML = '';
    eliminarTablaYMensaje();

    horarios.forEach((horario) => {
        const boton = document.createElement('button');
        boton.id = horario.id;
        boton.dataset.clase = horario.clase || '';
        boton.dataset.hora = horario.hora || '';
        boton.innerHTML = `<b>${esc((horario.clase || '').toUpperCase())}:</b> ${esc(horario.hora || '')}`;
        boton.style.margin = '10px 0';
        boton.addEventListener('click', () => {
            document.querySelectorAll('#menu button').forEach((btn) => btn.classList.remove('active'));
            boton.classList.add('active');
            admin.horarioId = horario.id;
            admin.clase = horario.clase;
            admin.hora = horario.hora;
            const fechaISO = getFechaISO();
            obtenerInscripciones(fechaISO, horario.id, horario.clase, horario.hora);
        });
        menu.appendChild(boton);
    });
}

// ==================== MOSTRAR INSCRIPCIONES ====================
async function mostrarInscripciones(inscripciones, clase, hora, horario_id) {
    admin.horarioId = horario_id;
    admin.clase = clase;
    admin.hora = hora;
    admin.fechaISO = getFechaISO();

    const contenedor = document.getElementById('inscritos');
    if (!contenedor) return;
    contenedor.innerHTML = '';

    const mensaje = document.createElement('h2');
    mensaje.id = 'mensaje-inscripciones';

    const limiteInscripciones = await obtenerLimiteInscripciones(horario_id);
    const totalInscritos = Array.isArray(inscripciones) ? inscripciones.length : 0;
    
    if (totalInscritos === 0) {
        mensaje.textContent = `No hay inscripciones para ${(clase || '').toUpperCase()} de ${hora || ''}`;
    } else {
        const limiteTexto = limiteInscripciones > 0 ? `${totalInscritos}/${limiteInscripciones}` : `${totalInscritos}`;
        mensaje.textContent = `Inscripciones para ${(clase || '').toUpperCase()} de ${hora || ''} - ${limiteTexto} inscritos`;
    }

    const botonAnadir = document.createElement('button');
    botonAnadir.id = 'boton-inscripciones';
    botonAnadir.classList.add('btnAnadir');
    botonAnadir.textContent = 'Añadir Inscripción';
    botonAnadir.onclick = abrirModalAnadirInscripcion;

    contenedor.appendChild(mensaje);
    contenedor.appendChild(botonAnadir);

    // TABLA DE INSCRIPCIONES
    if (Array.isArray(inscripciones) && inscripciones.length > 0) {
        const tabla = document.createElement('table');
        const thead = document.createElement('thead');
        thead.innerHTML = `<tr><th><input type='checkbox' id='chk-master'></th><th>#</th><th>Nombre</th><th>Teléfono</th><th>Acciones</th></tr>`;
        tabla.appendChild(thead);
        const tbody = document.createElement('tbody');

        let index = 1;
        inscripciones.forEach((inscrito) => {
            const fila = document.createElement('tr');
            fila.innerHTML = `
                <td><input type="checkbox" class="chk-del" data-id="${esc(inscrito.id)}" data-nombre="${esc(inscrito.nombre)}" data-telefono="${esc(inscrito.telefono)}"></td>
                <td>${index}</td>
                <td>${esc(inscrito.nombre)}</td>
                <td>${esc(inscrito.telefono)}</td>
                <td><button class="btnEliminar" data-id="${esc(inscrito.id)}">ELIMINAR</button></td>
            `;
            tbody.appendChild(fila);
            index++;
        });

        tabla.appendChild(tbody);
        const tablaContainer = document.createElement('div');
        tablaContainer.classList.add('tabla-container');
        tablaContainer.appendChild(tabla);
        
        const actions = document.createElement('div');
        actions.className = 'bulk-actions';
        actions.innerHTML = `<button id="btn-del-selected" class="btn btn-danger" disabled>Eliminar seleccionados</button>`;
        tablaContainer.appendChild(actions);
        contenedor.appendChild(tablaContainer);

        // EVENT LISTENERS - UNA SOLA VEZ
        const master = tablaContainer.querySelector('#chk-master');
        const tbodyEl = tablaContainer.querySelector('tbody');
        const btnDelSelected = tablaContainer.querySelector('#btn-del-selected');

        function actualizarBtnEliminar() {
            const selCount = tbodyEl.querySelectorAll('.chk-del:checked').length;
            btnDelSelected.disabled = selCount === 0;
        }

        master.addEventListener('change', () => {
            tbodyEl.querySelectorAll('.chk-del').forEach(ch => ch.checked = master.checked);
            actualizarBtnEliminar();
        });

        tbodyEl.addEventListener('change', (e) => {
            if (e.target.classList.contains('chk-del')) {
                actualizarBtnEliminar();
            }
        });

        btnDelSelected.addEventListener('click', () => {
            const seleccionados = Array.from(tbodyEl.querySelectorAll('.chk-del:checked')).map(ch => ch.dataset.id);
            if (seleccionados.length > 0) {
                confirmarEliminarMultiple(seleccionados);
            }
        });

        // BOTONES INDIVIDUALES
        const botonesEliminar = contenedor.querySelectorAll('.btnEliminar');
        botonesEliminar.forEach((boton) => {
            boton.addEventListener('click', () => {
                const id = boton.getAttribute('data-id');
                confirmarEliminar(id);
            });
        });
    }

    // CARGAR COLA DE ESPERA
    if (typeof renderColaEspera === 'function') {
        renderColaEspera(horario_id, admin.fechaISO);
    }
}

function eliminarTablaYMensaje() {
    const mensaje = document.getElementById('mensaje-inscripciones');
    if (mensaje) mensaje.remove();
    const boton = document.getElementById('boton-inscripciones');
    if (boton) boton.remove();
    const tablaContainer = document.querySelector('.tabla-container');
    if (tablaContainer) tablaContainer.remove();
}

// ==================== MODAL AÑADIR INSCRIPCIÓN ====================
function abrirModalAnadirInscripcion() {
    if (!admin.horarioId) {
        alert('Selecciona un horario primero');
        return;
    }

    const formHtml = `
        <div id="modal-form" class="modal">
            <div class="modal-content">
                <h2>Añadir Inscripción</h2>
                <label>Nombre:</label>
                <input type="text" id="nombre" required>
                <label>Teléfono:</label>
                <input type="text" id="telefono" required>
                <div style="margin-top:10px">
                    <button id="guardarInscripcion">Guardar</button>
                    <button id="cancelarInscripcion">Cancelar</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', formHtml);

    document.getElementById('cancelarInscripcion').addEventListener('click', () => {
        const modal = document.getElementById('modal-form');
        if (modal) modal.remove();
    });

    document.getElementById('guardarInscripcion').addEventListener('click', guardarNuevaInscripcion);
}

async function guardarNuevaInscripcion() {
    const nombre = document.getElementById('nombre').value.trim();
    const telefono = document.getElementById('telefono').value.trim();

    if (nombre === '' || telefono === '') {
        alert('Por favor, completa todos los campos.');
        return;
    }

    if (!admin.horarioId) {
        alert('Error: no hay horario seleccionado');
        return;
    }

    const fechaIso = getFechaISO();

    try {
        const response = await fetch('inscribir_cliente.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ nombre, telefono, horario_id: admin.horarioId, fecha: fechaIso }).toString()
        });
        const result = await response.json();
        if (result.success) {
            const modal = document.getElementById('modal-form');
            if (modal) modal.remove();
            if (result.status === 'WAITLIST') {
                const turno = result.posicion ? ' Posición: ' + result.posicion + '.' : '';
                notificarExito((result.already ? 'Esta persona ya está en la lista de espera.' : 'La clase está completa. Persona añadida a la lista de espera.') + turno);
            } else {
                notificarExito('Inscripción realizada con éxito' + (result.avisos === false ? '. Esta persona no recibirá avisos en el móvil (no tiene el móvil asociado).' : result.avisos === true ? '. Se le ha avisado al móvil.' : ''));
            }
            obtenerInscripciones(fechaIso, admin.horarioId, admin.clase, admin.hora);
        } else {
            alert(errorAmigable(['WAITLIST_IDENTITY_CONFLICT', 'WAITLIST_REQUIRES_NOTICES'].includes(result.code) ? result.code : result.error));
        }
    } catch (error) {
        console.error('Error guardarNuevaInscripcion:', error);
        alert('Error al conectar con el servidor');
    }
}

// ==================== ELIMINAR INSCRIPCIÓN ====================
function confirmarEliminar(id) {
    const confirmModalHtml = `
    <div id="confirm-cancel-modal" class="modal">
        <div class="modal-content modal-delete">
            <h2>¿Seguro que quieres eliminar esta inscripción?</h2>
            <p>Esta acción no se puede deshacer.</p>
            <div class="modal-buttons">
                <button id="confirmarEliminar" class="btn btn-danger">Sí, eliminar</button>
                <button id="noEliminar" class="btn btn-secondary">Cancelar</button>
            </div>
        </div>
    </div>
    `;
    document.body.insertAdjacentHTML('beforeend', confirmModalHtml);

    const modal = document.getElementById('confirm-cancel-modal');

    document.getElementById('confirmarEliminar').addEventListener('click', async () => {
        await eliminarInscripcion(id);
        modal.remove();
    });

    document.getElementById('noEliminar').addEventListener('click', () => modal.remove());
}

async function eliminarInscripcion(id) {
    if (!id) {
        alert('Error interno: ID vacío.');
        return;
    }

    try {
        const response = await fetch('eliminar_inscripcion.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ id }).toString()
        });

        const result = await response.json();

        if (result.success) {
            notificarExito('Inscripción eliminada correctamente');
            if (admin.horarioId) {
                obtenerInscripciones(admin.fechaISO, admin.horarioId, admin.clase, admin.hora);
            }
        } else {
            alert('Error al eliminar: ' + (result.error || 'desconocido'));
        }
    } catch (error) {
        console.error('Error eliminarInscripcion:', error);
        alert('Error al conectar con el servidor');
    }
}

function confirmarEliminarMultiple(ids) {
    if (!Array.isArray(ids) || ids.length === 0) {
        alert('No hay seleccionados para eliminar');
        return;
    }

    const confirmModalHtml = `
    <div id="confirm-multi-modal" class="modal">
        <div class="modal-content modal-delete">
            <h2>¿Eliminar ${ids.length} inscripción(es)?</h2>
            <p>Esta acción no se puede deshacer.</p>
            <div class="modal-buttons">
                <button id="confirmarMulti" class="btn btn-danger">Sí, eliminar todos</button>
                <button id="cancelarMulti" class="btn btn-secondary">Cancelar</button>
            </div>
        </div>
    </div>
    `;
    document.body.insertAdjacentHTML('beforeend', confirmModalHtml);

    const modal = document.getElementById('confirm-multi-modal');

    document.getElementById('confirmarMulti').addEventListener('click', async () => {
        for (const id of ids) {
            await eliminarInscripcion(id);
        }
        modal.remove();
    });

    document.getElementById('cancelarMulti').addEventListener('click', () => modal.remove());
}

// ==================== GESTIÓN DE HORARIOS ====================
const clasesDisponibles = ['YOGA', 'FULL BODY', 'CORE', 'BOXEO', 'PUMP', 'PILATES', 'TRX', 'ESPALDA SANA', 'HIIT', 'FUNCIONAL', 'THAI', 'BALANCE', 'GAP', 'COMBAT', 'TOP DANCE', 'MANTENIMIENTO', 'CICLO'];
const diasDisponibles = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'];
const horasDisponibles = ['09:30-10:25', '10:30-11:25', '11:30-12:25', '17:30-18:25', '18:30-19:25', '19:30-20:25', '20:30-21:25'];

function crearSelect(opciones, valor, id, campo) {
    let html = `<select data-id="${id}" data-field="${campo}">`;
    opciones.forEach((opt) => {
        const sel = String(opt).toLowerCase() === String(valor).toLowerCase() ? 'selected' : '';
        html += `<option value="${opt}" ${sel}>${opt}</option>`;
    });
    html += `</select>`;
    return html;
}

function crearInputLimite(valor, id) {
    const val = valor === null || valor === undefined ? '' : valor;
    return `<input type="number" min="0" data-id="${id}" data-field="limite" value="${val}" placeholder="Sin límite">`;
}
function crearInputHora(valor, id) {
    const val = valor ? valor : '';
    return `<input type="text" data-id="${id}" data-field="hora" value="${val}" 
             placeholder="Ej: 09:30-10:25" 
             style="width:140px; text-align:center; padding: 8px; border-radius: 4px; border: 1px solid #048625;">`;
}


async function cargarHorarios() {
    try {
        const response = await fetch('obtener_horarios.php');
        if (!response.ok) throw new Error('Error al obtener horarios');
        const horarios = await response.json();
        const tbody = document.querySelector('#tabla-horarios tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        horarios.forEach((h) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${crearSelect(clasesDisponibles, h.clase, h.id, 'clase')}</td>
                <td>${crearSelect(diasDisponibles, h.dia, h.id, 'dia')}</td>
                <td>${crearInputHora(h.hora, h.id)}</td>
                <td>${crearInputLimite(h.limite, h.id)}</td>
                <td class="acciones">
                    <button onclick="guardarHorario(${h.id})">Guardar</button>
                    <button onclick="eliminarHorario(${h.id})">Eliminar</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        console.error('Error cargarHorarios:', error);
        alert('Error al cargar los horarios');
    }
}

async function guardarHorario(id) {
    const inputs = document.querySelectorAll(`[data-id="${id}"]`);
    const data = {};
    let horaError = false;
    
    inputs.forEach((input) => {
        if (input.dataset.field === 'hora') {
            const horaOriginal = input.value.trim();
            const horaNormalizada = normalizarHora(horaOriginal);
            
            if (!horaNormalizada) {
                horaError = true;
                input.style.borderColor = '#dc3545';
                return;
            }
            
            data[input.dataset.field] = horaNormalizada;
            input.style.borderColor = '';
        } else {
            data[input.dataset.field] = typeof input.value === 'string' ? input.value.trim() : input.value;
        }
    });
    
    if (horaError) {
        alert('Formato de hora inválido\nUsa: 09:30-10:25');
        return;
    }
    
    data.id = id;
    try {
        const response = await fetch('editar_horario.php', {
            method: 'POST',
            body: new URLSearchParams(data)
        });
        const result = await response.json();
        if (result.success) {
            notificarExito('Horario actualizado');
            cargarHorarios();
        } else {
            alert('Error: ' + (result.error || 'desconocido'));
        }
    } catch (err) {
        console.error('Error guardarHorario:', err);
        alert('Error de conexión');
    }
}

async function eliminarHorario(id) {
    if (!(await confirmarAccion('¿Eliminar este horario?', 'Se borrará de la tabla de horarios y ya no se podrá reservar.', 'Sí, eliminar'))) return;
    try {
        const response = await fetch('eliminar_horario.php', {
            method: 'POST',
            body: new URLSearchParams({ id })
        });
        const result = await response.json();
        if (result.success) {
            notificarExito('Horario eliminado');
            refreshAdminUI();
        } else {
            alert('Error: ' + (result.error || 'desconocido'));
        }
    } catch (err) {
        console.error('Error eliminarHorario:', err);
        alert('Error al conectar con el servidor');
    }
}

function nuevoHorario() {
    const tbody = document.querySelector('#tabla-horarios tbody');
    if (!tbody) return;
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>${crearSelect(clasesDisponibles, '', 'nuevo', 'clase')}</td>
        <td>${crearSelect(diasDisponibles, '', 'nuevo', 'dia')}</td>
        <td>${crearInputHora('', 'nuevo')}</td>
        <td>${crearInputLimite('', 'nuevo')}</td>
        <td><button onclick="insertarHorario()">Insertar</button></td>
    `;
    tbody.appendChild(tr);
}

async function insertarHorario() {
    const selClase = document.querySelector("[data-id='nuevo'][data-field='clase']");
    const selDia = document.querySelector("[data-id='nuevo'][data-field='dia']");
    const inputHora = document.querySelector("[data-id='nuevo'][data-field='hora']");
    const inputLimite = document.querySelector("[data-id='nuevo'][data-field='limite']");
    
    if (!selClase || !selDia || !inputHora) {
        alert('Completa todos los campos');
        return;
    }
    
    const horaOriginal = inputHora.value.trim();
    const horaNormalizada = normalizarHora(horaOriginal);
    
    if (!horaNormalizada) {
        alert('Formato de hora inválido\nEjemplos válidos:\n• 09:30-10:25\n• 09:30 10:25\n• 0930-1025');
        inputHora.style.borderColor = '#dc3545';
        return;
    }
    
    inputHora.style.borderColor = '';
    
    const data = {
        clase: selClase.value,
        dia: selDia.value,
        hora: horaNormalizada,
        limite: inputLimite && inputLimite.value ? inputLimite.value.trim() : ''
    };
    
    try {
        const response = await fetch('insertar_horario.php', {
            method: 'POST',
            body: new URLSearchParams(data)
        });
        const result = await response.json();
        if (result.success) {
            notificarExito('Horario añadido');
            cargarHorarios();
        } else {
            alert('Error: ' + (result.error || 'desconocido'));
        }
    } catch (err) {
        console.error('Error insertarHorario:', err);
        alert('Error de conexión');
    }
}

// ==================== UPLOAD DE IMAGEN DEL HORARIO ====================
document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('archivo-horario');
    const chk = document.getElementById('chk-confirm');
    const btn = document.getElementById('btn-subir-horario');
    const msg = document.getElementById('upload-msg');
    if (!fileInput || !chk || !btn) return;

    function updateButton() {
        btn.disabled = !(fileInput.files && fileInput.files.length > 0 && chk.checked);
    }
    fileInput.addEventListener('change', updateButton);
    chk.addEventListener('change', updateButton);

    btn.addEventListener('click', async () => {
        if (!fileInput.files || fileInput.files.length === 0) return;
        const fd = new FormData();
        fd.append('archivo', fileInput.files[0]);
        btn.disabled = true;
        msg.textContent = 'Subiendo...';

        try {
            const resp = await fetch('admin_upload_horario.php', { method: 'POST', body: fd });
            const raw = await resp.text();
            const data = JSON.parse(raw);
            if (!resp.ok || !data.success) {
                msg.textContent = 'Error: ' + (data.msg || data.error || resp.status);
                btn.disabled = false;
                return;
            }
            msg.textContent = '¡Horario actualizado!';
            const cacheBust = '?t=' + Date.now();
            const img = document.getElementById('preview-actual');
            if (img) {
                img.style.display = 'block';
                img.src = 'img/horario.jpg' + cacheBust;
            }
            const pdf = document.getElementById('preview-pdf');
            if (pdf) {
                pdf.style.display = 'none';
            }
        } catch (e) {
            console.error(e);
            msg.textContent = 'Error de red subiendo el archivo.';
            btn.disabled = false;
        }
    });
});

// ==================== COLA DE ESPERA ====================
async function fetchCola(horario_id, fechaISO) {
    try {
        const r = await fetch(`obtener_cola.php?horario_id=${encodeURIComponent(horario_id)}&fecha=${encodeURIComponent(fechaISO)}`, { cache: 'no-store' });
        const raw = await r.text();
        if (!r.ok) {
            console.error('cola HTTP', r.status, raw);
            return null;
        }
        const data = JSON.parse(raw);
        return Array.isArray(data) ? data : (data.data || []);
    } catch (e) {
        console.error('cola JSON', e);
        return null;
    }
}

function ensureColaContainer() {
    let cont = document.getElementById('cola-admin');
    if (!cont) {
        const parent = document.getElementById('inscritos');
        if (parent) {
            cont = document.createElement('div');
            cont.id = 'cola-admin';
            cont.style.marginTop = '16px';
            cont.style.position = 'static';
            cont.style.zIndex = '1';
            cont.style.pointerEvents = 'auto';
            cont.style.borderTop = '1px solid #ddd';
            cont.style.paddingTop = '10px';
            parent.appendChild(cont);
        }
    }
    return cont;
}

let colaRenderSeq = 0;
let colaRemovalBusy = false;
async function quitarDeCola(persona, horario_id, fechaISO, boton) {
    if (colaRemovalBusy) return;
    colaRemovalBusy = true;
    boton.disabled = true;
    try {
        const confirmado = await confirmarAccion('Quitar de la lista de espera',
            '¿Quieres quitar a ' + persona.nombre + ' (' + persona.telefono + ') de la lista de espera del ' + fechaISO.split('-').reverse().join('/') + '?',
            'Sí, quitar de la cola');
        if (!confirmado) return;
        if (String(admin.horarioId) !== String(horario_id) || getFechaISO() !== fechaISO) {
            mostrarAviso('Has cambiado de clase o de fecha. Vuelve a seleccionar a la persona.');
            return;
        }
        const response = await fetch('eliminar_cola.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ id: persona.id, horario_id, fecha: fechaISO }).toString()
        });
        const result = await response.json();
        if (result.success) {
            await renderColaEspera(horario_id, fechaISO);
            notificarExito('Persona quitada de la lista de espera.');
        } else {
            if (result.code === 'WAITLIST_CHANGED') await renderColaEspera(horario_id, fechaISO);
            mostrarAviso(result.error || 'No se pudo quitar a esta persona de la lista de espera.');
        }
    } catch (error) {
        mostrarAviso('No se ha podido confirmar la retirada. Recarga la lista antes de volver a intentarlo.');
    } finally {
        colaRemovalBusy = false;
        if (boton.isConnected) boton.disabled = false;
    }
}

async function renderColaEspera(horario_id, fechaISO) {
    if (!horario_id || !fechaISO || String(admin.horarioId) !== String(horario_id) || getFechaISO() !== fechaISO) return;
    const seq = ++colaRenderSeq;
    const items = await fetchCola(horario_id, fechaISO);
    if (seq !== colaRenderSeq || String(admin.horarioId) !== String(horario_id) || getFechaISO() !== fechaISO) return;
    const cont = ensureColaContainer();
    if (!cont) return;
    cont.style.overflowX = 'auto';
    const title = '<h3 style="margin:6px 0 8px 0">En lista de espera</h3>';
    if (items === null) {
        cont.innerHTML = title + '<p role="alert">No se ha podido cargar la lista de espera.</p><button type="button" class="btn">Volver a cargar</button>';
        cont.querySelector('button').onclick = () => renderColaEspera(horario_id, fechaISO);
        return;
    }
    if (!items.length) {
        cont.innerHTML = title + '<p>No hay personas en lista de espera.</p>';
        return;
    }
    let html = title + '<table class="tabla" style="width:100%"><thead><tr><th>#</th><th>Nombre</th><th>Teléfono</th><th>Apuntado</th><th>Acciones</th></tr></thead><tbody>';
    for (let i = 0; i < items.length; i++) {
        const r = items[i];
        html += `<tr><td>${i + 1}</td><td>${esc(r.nombre)}</td><td>${esc(r.telefono)}</td><td>${esc(r.creado_en)}</td><td><button type="button" class="btn btn-danger" data-wait-row="${i}">Quitar de la cola</button></td></tr>`;
    }
    cont.innerHTML = html + '</tbody></table>';
    cont.querySelectorAll('[data-wait-row]').forEach(boton => {
        const persona = items[Number(boton.dataset.waitRow)];
        boton.setAttribute('aria-label', 'Quitar de la cola a ' + persona.nombre);
        boton.onclick = () => quitarDeCola(persona, horario_id, fechaISO, boton);
    });
}

// ==================== UTILIDADES ====================
function limpiarModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.remove();
}

function mostrarError(titulo, mensaje) {
    const errorHtml = `
    <div id="error-modal" class="modal">
        <div class="modal-content modal-error">
            <h2>${esc(titulo)}</h2>
            <p>${esc(mensaje)}</p>
            <button onclick="document.getElementById('error-modal').remove()">Cerrar</button>
        </div>
    </div>
    `;
    document.body.insertAdjacentHTML('beforeend', errorHtml);
}

// ==================== EXPORTAR FUNCIONES GLOBALES ====================
if (typeof window !== 'undefined') {
    window.notificarExito = notificarExito;
    window.mostrarModalExito = mostrarModalExito;
    window.normalizarFecha = normalizarFecha;
    window.getFechaISO = getFechaISO;
    window.obtenerHorariosDia = obtenerHorariosDia;
    window.obtenerInscripciones = obtenerInscripciones;
    window.mostrarInscripciones = mostrarInscripciones;
    window.cargarHorarios = cargarHorarios;
    window.guardarHorario = guardarHorario;
    window.eliminarHorario = eliminarHorario;
    window.insertarHorario = insertarHorario;
    window.nuevoHorario = nuevoHorario;
    window.confirmarEliminar = confirmarEliminar;
    window.eliminarInscripcion = eliminarInscripcion;
    window.refreshAdminUI = refreshAdminUI;
    window.renderColaEspera = renderColaEspera;
    window.fetchCola = fetchCola;
    window.mostrarError = mostrarError;
    window.limpiarModal = limpiarModal;
}