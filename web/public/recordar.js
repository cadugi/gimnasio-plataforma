'use strict';
/* Recordar nombre y teléfono en el móvil personal. Nunca en una pantalla compartida (se declara de forma explícita, no por tamaño). */
(() => {
  let compartida = false, activado = false;
  try { compartida = localStorage.getItem('tf_modo') === 'compartido'; activado = localStorage.getItem('tf_recordar') === '1'; } catch (_) {}
  if (compartida || !activado) return;
  let datos = null;
  const rellenar = () => {
    if (!datos) return;
    const n = document.getElementById('nombre'), t = document.getElementById('telefono');
    if (n && !n.value) n.value = datos.nombre; if (t && !t.value) t.value = datos.telefono;
  };
  fetch('movil.php', { credentials: 'same-origin' }).then(r => r.json()).then(j => { if (j.linked) datos = { nombre: j.nombre, telefono: j.telefono }; }).catch(() => {});
  const original = window.mostrarFormulario;
  if (typeof original === 'function') window.mostrarFormulario = async (...a) => { const r = await original(...a); rellenar(); return r; };
})();
