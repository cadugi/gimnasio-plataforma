(() => {
  let previousFocus;
  const form = document.getElementById('formulario');
  const submit = document.getElementById('submit');
  const modal = document.getElementById('modal-inscripcion');
  window.openMobileBooking = async (button, session) => {
    previousFocus = button;
    submit.disabled = true;
    document.getElementById('selectHorarios').replaceChildren(new Option('Cargando sesiones...', ''));
    document.body.classList.add('dialog-open');
    try {
      const loading = mostrarFormulario(button.dataset.class);
      form.focus();
      await loading;
      if (session) {
        const select = document.getElementById('selectHorarios');
        const option = [...select.options].find(item => item.value.split('|')[0] === String(session.id) && item.dataset.fecha === session.date);
        if (option) { select.value = option.value; select.dispatchEvent(new Event('change')); }
        else { select.replaceChildren(new Option('Esta sesión ya no está disponible', '')); }
      }
    }
    finally { submit.disabled = !document.getElementById('selectHorarios').value; }
  };
  document.querySelectorAll('[data-class]').forEach(button => button.addEventListener('click', () => openMobileBooking(button)));
  const cancel = window.cancelarFormulario;
  window.cancelarFormulario = () => {
    cancel();
    document.body.classList.remove('dialog-open');
    previousFocus?.focus();
  };
  const book = window.inscribirCliente;
  window.inscribirCliente = async () => {
    if (submit.disabled) return;
    submit.disabled = true;
    submit.textContent = 'Enviando reserva...';
    try { await book(); }
    finally { submit.disabled = false; submit.textContent = 'Reservar plaza'; }
  };
  new MutationObserver(() => { if (modal.style.display === 'block') modal.focus(); }).observe(modal, {attributes:true, attributeFilter:['style']});
  document.addEventListener('keydown', event => {
    const active = modal.style.display === 'block' ? modal : form.style.display === 'block' ? form : null;
    if (!active) return;
    if (event.key === 'Escape') { active === modal ? cerrarModal() : cancelarFormulario(); return; }
    if (event.key !== 'Tab') return;
    const items = [...active.querySelectorAll('button:not(:disabled),input,select,a[href]')].filter(el => el.getClientRects().length);
    const first = items[0], last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === active)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === active)) { event.preventDefault(); first?.focus(); }
  });
})();
