(()=>{const original=window.fetch.bind(window);window.fetch=(url,options={})=>{const headers=new Headers(options.headers||{});headers.set('X-TopFitness-Request','1');return original(url,{...options,headers});};})();
// ==================== VARIABLES GLOBALES ====================
let horariosActuales = [];
let diaFiltro = '';

// ==================== UTILIDADES ====================
function normalizarDia(dia) {
    return dia.toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
}

function formatearFecha(fecha) {
    const diasSemana = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
    let dateObj = new Date(fecha);
    let diaSemana = diasSemana[dateObj.getDay()];
    let diaMes = dateObj.getDate();
    return `${diaSemana} ${diaMes}`;
}

function ordenarHorarios(horarios) {
    const diasSemana = ["domingo", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado"];
    const hoy = new Date();

    let inicioRango = new Date(hoy);
    inicioRango.setHours(0, 0, 0, 0);

    let finRango = new Date(hoy);
    finRango.setDate(hoy.getDate() + 5);
    finRango.setHours(23, 59, 59, 999);

    const horariosConFechas = horarios.map(horario => {
        const indiceClase = diasSemana.indexOf(normalizarDia(horario.dia));
        if (indiceClase === -1) return null;

        let indiceHoy = hoy.getDay();
        let ajusteDias = (indiceClase - indiceHoy + 7) % 7;
        if (ajusteDias === 0 && hoy.getHours() >= 20) ajusteDias = 7;

        let fechaClase = new Date(hoy);
        fechaClase.setDate(hoy.getDate() + ajusteDias);

        return {
            ...horario,
            fecha: [fechaClase.getFullYear(), String(fechaClase.getMonth()+1).padStart(2,'0'), String(fechaClase.getDate()).padStart(2,'0')].join('-')
        };
    }).filter(Boolean);

    const horariosFiltrados = horariosConFechas.filter(horario => {
        let fechaHorario = new Date(horario.fecha);
        return fechaHorario >= inicioRango && fechaHorario <= finRango;
    });

    return horariosFiltrados.sort((a, b) => new Date(a.fecha) - new Date(b.fecha));
}

// ==================== OBTENCIÓN DE DATOS ====================
async function obtenerHorariosClase(clase) {
    try {
        const response = await fetch(`obtener_horarios_clase.php?clase=${encodeURIComponent(clase)}`, {
            cache: 'no-store'
        });
        if (!response.ok) throw new Error("Error al obtener los horarios");
        const data = await response.json();
        const horarios = (data.ok && data.data) ? data.data : [];
        return ordenarHorarios(horarios);
    } catch (error) {
        console.error("Error obtenerHorariosClase:", error);
        return [];
    }
}

async function comprobarDisponibilidad(horario_id, fecha) {
    try {
        const response = await fetch(
            `comprobar_disponibilidad.php?horario_id=${encodeURIComponent(horario_id)}&fecha=${encodeURIComponent(fecha)}`,
            { cache: 'no-store' }
        );
        if (!response.ok) throw new Error("Error al comprobar disponibilidad");
        const data = await response.json();
        return {
            success: data.success || false,
            disponibles: parseInt(data.disponibles || 0),
            limite: parseInt(data.limite || 0),
            en_cola: parseInt(data.en_cola || 0),
            cancelada: data.cancelada === true
        };
    } catch (error) {
        console.error("Error comprobarDisponibilidad:", error);
        return { success: false, disponibles: 0, limite: 0, en_cola: 0 };
    }
}

// ==================== GENERADOR DE QR ====================
function generarQR(texto) {
    const qrContainer = document.getElementById('qrCode');
    qrContainer.innerHTML = '';
    
    try {
        QRCode.toCanvas(qrContainer, texto, {
            errorCorrectionLevel: 'H',
            type: 'image/png',
            quality: 0.95,
            margin: 1,
            width: 200,
            color: {
                dark: '#048625',
                light: '#ffffff'
            }
        }, function(error) {
            if (error) console.error('QR Error:', error);
        });
    } catch (e) {
        console.error('Error generando QR:', e);
    }
}

// ==================== CREAR EVENTO CALENDARIO ====================
function crearEnlaceCalendario(clase, hora, fecha, nombre) {
    const [inicio, fin] = hora.split('-');
    const [hIni, mIni] = inicio.split(':');
    const [hFin, mFin] = fin.split(':');
    
    const fechaObj = new Date(fecha);
    const startDate = new Date(fechaObj);
    startDate.setHours(parseInt(hIni), parseInt(mIni), 0);
    
    const endDate = new Date(fechaObj);
    endDate.setHours(parseInt(hFin), parseInt(mFin), 0);
    
    // Formato iCal
    const dtstart = startDate.toISOString().replace(/[-:]/g, '').replace(/\.000/, '');
    const dtend = endDate.toISOString().replace(/[-:]/g, '').replace(/\.000/, '');
    
    const icalText = `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Top Fitness//NONSGML Events//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
UID:topfitness-${fecha}-${clase}@topfitness.local
DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').replace(/\.000/, '')}
DTSTART:${dtstart}
DTEND:${dtend}
SUMMARY:${clase.toUpperCase()} - Top Fitness
DESCRIPTION:Tu clase de ${clase} en Top Fitness. Inscrito: ${nombre}
LOCATION:Top Fitness Gym
END:VEVENT
END:VCALENDAR`;
    
    return 'data:text/calendar;charset=utf-8,' + encodeURIComponent(icalText);
}

// ==================== MODAL DE ESTADO ====================
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function mensajeModal(estado, html) {
    document.getElementById('modal-inscripcion').dataset.state = estado;
    document.getElementById('textoModal').innerHTML = html;
}

// ==================== INTERFAZ ====================
window.mostrarFormulario = async (clase) => {
    const formulario = document.getElementById('formulario');
    const titulo = document.getElementById('form-titulo');
    const select = document.getElementById('selectHorarios');

    if (!formulario || !select || !titulo) return;

    // Reset
    const nombre = document.getElementById('nombre');
    const tel = document.getElementById('telefono');
    if (nombre) nombre.value = '';
    if (tel) tel.value = '';
    select.innerHTML = '';

    titulo.innerHTML = `Inscripción a<strong>${(clase || '').toUpperCase()}</strong>`;
    formulario.style.display = 'block';

    // Estado de cola
    let estadoCola = document.getElementById('estado-cola');
    if (!estadoCola) {
        estadoCola = document.createElement('div');
        estadoCola.id = 'estado-cola';
        estadoCola.style.margin = '10px 0';
        estadoCola.style.fontSize = '12px';
        estadoCola.style.fontWeight = '600';
        estadoCola.style.color = '#ffb74d';
        const selectWrap = document.querySelector('.formulario .select-container') || select;
        (selectWrap.parentNode || document.getElementById('formulario')).insertBefore(estadoCola, selectWrap.nextSibling);
    }
    estadoCola.textContent = '';

    // Cargar horarios
    const horarios = await obtenerHorariosClase(clase);
    horariosActuales = horarios;
    
    if (horarios.length === 0) {
        select.innerHTML = '<option disabled>No hay horarios disponibles</option>';
        return;
    }

    for (const h of horarios) {
        const info = await comprobarDisponibilidad(h.id, h.fecha);
        if (info.cancelada) continue; // clase cancelada ese día: no se ofrece
        const disponibles = Math.max(0, info.disponibles || 0);
        const enCola = info.en_cola || 0;

        const opt = document.createElement('option');
        opt.value = `${h.id}|${h.fecha}|${h.hora}|${clase}`;
        opt.dataset.fecha = h.fecha;
        opt.dataset.disponibles = disponibles;
        opt.dataset.cola = enCola;
        opt.dataset.hora = h.hora;

        let texto = `${formatearFecha(h.fecha)}: ${h.hora}`;
        
        if (disponibles > 0) {
            opt.textContent = `${texto} (${disponibles} plaza${disponibles !== 1 ? 's' : ''})`;
        } else if (enCola >= 0) {
            opt.disabled = false;
            opt.textContent = `${texto} - COMPLETO (Cola: ${enCola})`;
            opt.style.color = '#ffb74d';
        } else {
            opt.disabled = true;
            opt.textContent = `${texto} - COMPLETO`;
        }
        select.appendChild(opt);
    }

    if (!select.options.length) {
        select.innerHTML = '<option disabled>No hay horarios disponibles</option>';
        return;
    }

    // Evento de cambio en select
    select.onchange = () => {
        const opt = select.selectedOptions[0];
        if (!opt) {
            estadoCola.textContent = '';
            return;
        }
        const enCola = parseInt(opt.dataset.cola || 0);
        if (enCola > 0) {
            estadoCola.textContent = `Hay ${enCola} persona${enCola !== 1 ? 's' : ''} en lista de espera`;
        } else {
            estadoCola.textContent = '';
        }
    };
};

window.cancelarFormulario = () => {
    const formulario = document.getElementById('formulario');
    if (formulario) {
        formulario.style.display = 'none';
    }
};

window.cerrarModal = () => {
    const modal = document.getElementById('modal-inscripcion');
    const overlay = document.getElementById('modal-overlay');
    if (modal) modal.style.display = 'none';
    if (overlay) overlay.style.display = 'none';
};

window.inscribirCliente = async () => {
    const nombreInput = document.getElementById('nombre');
    const telefonoInput = document.getElementById('telefono');
    const selectHorarios = document.getElementById('selectHorarios');
    const modal = document.getElementById('modal-inscripcion');
    const overlay = document.getElementById('modal-overlay');
    const textoModal = document.getElementById('textoModal');
    const qrContainer = document.getElementById('qrContainer');

    const nombre = nombreInput.value.trim();
    const telefono = telefonoInput.value.trim();

    if (!nombre || !telefono) {
        mensajeModal('error', '<strong>Faltan datos</strong>Rellena todos los campos');
        qrContainer.style.display = 'none';
        modal.style.display = 'block';
        overlay.style.display = 'block';
        setTimeout(cerrarModal, 2000);
        return;
    }

    if (!selectHorarios.value) {
        mensajeModal('error', '<strong>Elige una sesión</strong>Selecciona día y hora');
        qrContainer.style.display = 'none';
        modal.style.display = 'block';
        overlay.style.display = 'block';
        setTimeout(cerrarModal, 2000);
        return;
    }

    const [horario_id, fecha, hora, clase] = selectHorarios.value.split('|');

    try {
        const response = await fetch('inscribir_cliente.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({
                nombre,
                telefono,
                horario_id,
                fecha
            }).toString()
        });

        const data = await response.json();

        if (data.success) {
            nombreInput.value = '';
            telefonoInput.value = '';

            if (data.already) {
                mensajeModal('ok', `<strong>Ya estabas apuntado/a</strong><small>${clase.toUpperCase()} · ${formatearFecha(fecha)} a las ${hora}. No se ha usado otra plaza.</small>`);
                qrContainer.style.display = 'none';
            } else if (data.status === 'WAITLIST') {
                mensajeModal('wait', `<strong>En lista de espera</strong>Posición: <b>${data.posicion}</b><small>Te avisaremos cuando haya plaza</small>`);
                qrContainer.style.display = 'none';
            } else {
                const enlaceCalendario = crearEnlaceCalendario(clase, hora, fecha, nombre);
                mensajeModal('ok', `<strong>¡Inscripción confirmada!</strong><small>${clase.toUpperCase()} · ${formatearFecha(fecha)} a las ${hora}</small>`);
                
                const link=document.createElement('a');link.href=enlaceCalendario;link.download='topfitness-clase.ics';link.className='calendar-link';link.textContent='Añadir a mi calendario';qrContainer.replaceChildren(link);
                qrContainer.style.display = 'block';
            }

            modal.style.display = 'block';
            overlay.style.display = 'block';
            
            window.cancelarFormulario();
        } else {
            mensajeModal('error', '<strong>No se pudo reservar</strong>' + esc(data.error || 'Inténtalo de nuevo'));
            qrContainer.style.display = 'none';
            modal.style.display = 'block';
            overlay.style.display = 'block';
            setTimeout(cerrarModal, 7000);
        }
    } catch (error) {
        console.error('Error al inscribirse:', error);
        mensajeModal('error', '<strong>Sin conexión</strong>Inténtalo de nuevo');
        qrContainer.style.display = 'none';
        modal.style.display = 'block';
        overlay.style.display = 'block';
        setTimeout(cerrarModal, 3000);
    }
};

// ==================== FILTRO POR DÍA ====================
document.addEventListener('DOMContentLoaded', () => {
    const filterDia = document.getElementById('filterDia');
    const botonesGrid = document.getElementById('botones');

    if (filterDia) {
        filterDia.addEventListener('change', async (e) => {
            diaFiltro = e.target.value;
            
            if (!diaFiltro) {
                // Mostrar todas las tarjetas
                const tarjetas = botonesGrid.querySelectorAll('.card');
                tarjetas.forEach(tarjeta => {
                    tarjeta.style.display = 'flex';
                });
            } else {
                // Filtrar por día
                const tarjetas = botonesGrid.querySelectorAll('.card');
                tarjetas.forEach(async (tarjeta) => {
                    const clase = tarjeta.getAttribute('onclick').match(/'([^']+)'/)[1];
                    const horarios = await obtenerHorariosClase(clase);
                    const tieneEseDia = horarios.some(h => normalizarDia(h.dia) === normalizarDia(diaFiltro));
                    
                    tarjeta.style.display = tieneEseDia ? 'flex' : 'none';
                });
            }
        });
    }

    // Auto-refresh de la imagen del horario cada 30 segundos
    setInterval(() => {
        const img = document.getElementById('imgho');
        if (img) {
            img.src = 'img/horario.jpg?t=' + Date.now();
        }
    }, 30000);

    // Cerrar modal al hacer click fuera
    document.getElementById('modal-overlay').addEventListener('click', cerrarModal);
});