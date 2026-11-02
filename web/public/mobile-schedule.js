(() => {
  const panel = document.querySelector('#weekly-schedule');
  const days = document.querySelector('#schedule-days');
  const list = document.querySelector('#schedule-list');
  const title = document.querySelector('#schedule-date');
  const dayNames = ['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
  const normalize = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  const dateKey = date => [date.getUTCFullYear(), String(date.getUTCMonth()+1).padStart(2,'0'), String(date.getUTCDate()).padStart(2,'0')].join('-');
  const madrid = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Madrid', year:'numeric',month:'2-digit',day:'2-digit'});
  let sessions = [], dates = [], selected = 0, loading = false, cancelled = new Set();
  function render() {
    const date = dates[selected];
    if (!date) return;
    title.textContent = new Intl.DateTimeFormat('es-ES', {weekday:'long',day:'numeric',month:'long',timeZone:'UTC'}).format(date);
    [...days.children].forEach((button,index) => button.setAttribute('aria-pressed', String(index === selected)));
    list.replaceChildren();
    const matches = sessions.filter(session => normalize(session.dia) === dayNames[date.getUTCDay()]).sort((a,b) => a.hora.localeCompare(b.hora, 'es', {numeric:true}));
    if (!matches.length) { const empty = document.createElement('p');empty.className='schedule-empty';empty.textContent='Día de descanso. No hay clases programadas.';list.append(empty);return; }
    const now = new Date();
    const time = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
    for (const session of matches) {
      const row = document.createElement('div');row.className='session-row'+(/boxeo|thai/i.test(session.clase)?' fighters':'');
      const hour = document.createElement('span');hour.className='session-hour';hour.textContent=session.hora;
      const name = document.createElement('strong');name.textContent=session.clase;
      const action = document.createElement('button');action.type='button';action.dataset.class=session.clase;
      const start = session.hora.match(/(\d{1,2}):(\d{2})/);
      const isCancelled = cancelled.has(session.id+'|'+dateKey(date));
      if (isCancelled) row.classList.add('cancelled');
      const past = selected === 0 && start && `${start[1].padStart(2,'0')}:${start[2]}` <= time;
      action.disabled = selected > 5 || Boolean(past) || isCancelled;
      action.textContent = isCancelled ? 'Cancelada' : past ? 'Ya iniciada' : selected > 5 ? 'Aún no abre' : 'Reservar';
      action.setAttribute('aria-label', `${action.textContent}: ${session.clase}, ${session.hora}`);
      action.addEventListener('click', () => openMobileBooking(action, {...session,date:dateKey(date)}));
      row.append(hour,name,action);list.append(row);
    }
  }
  async function load() {
    if (loading) return;
    loading = true; list.textContent='Cargando horario...';
    try {
      const response = await fetch('obtener_horarios_clase.php', {cache:'no-store'});
      if (!response.ok) throw new Error('schedule unavailable');
      const result = await response.json();
      if (!result.ok || !Array.isArray(result.data)) throw new Error('invalid schedule');
      sessions=result.data;cancelled=new Set((result.canceladas||[]).map(c=>c.horario_id+'|'+c.fecha));
      const parts = Object.fromEntries(madrid.formatToParts(new Date()).map(part => [part.type,part.value]));
      const today = new Date(Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day),12));
      dates=Array.from({length:7},(_,index) => new Date(today.getTime()+index*86400000));
      days.replaceChildren();
      dates.forEach((date,index) => {
        const button=document.createElement('button');button.type='button';
        const label=document.createElement('span');label.textContent=index===0?'Hoy':new Intl.DateTimeFormat('es-ES',{weekday:'short',timeZone:'UTC'}).format(date).replace('.','');
        const number=document.createElement('strong');number.textContent=date.getUTCDate();
        button.append(label,number);button.setAttribute('aria-label',new Intl.DateTimeFormat('es-ES',{dateStyle:'full',timeZone:'UTC'}).format(date));
        button.addEventListener('click',()=>{selected=index;render();});days.append(button);
      });
      render();
    } catch (_) {
      list.replaceChildren();const error=document.createElement('p');error.textContent='No hemos podido cargar el horario.';
      const retry=document.createElement('button');retry.type='button';retry.className='secondary';retry.textContent='Volver a intentar';retry.addEventListener('click',load);list.append(error,retry);
    } finally { loading=false; }
  }
  panel.addEventListener('toggle',()=>{if(panel.open) load();});
  if(panel.open) load();
})();
