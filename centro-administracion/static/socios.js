// Una sola búsqueda; las coincidencias no verificadas nunca se convierten en vínculos.
export function viewSocios(root, {api, esc}) {
  root.classList.add('member-search-page');
  const $ = s => root.querySelector(s);
  const money = n => new Intl.NumberFormat('es-ES', {style:'currency', currency:'EUR'}).format(Number(n)/100);
  const day = v => { const s=String(v||'').slice(0,10); return /^\d{4}-\d{2}-\d{2}$/.test(s)?s.split('-').reverse().join('/'):'—'; };
  const labels={SIGNED:'Firmado',CANCELLED:'Anulado',ACTIVE:'Activo',BAJA:'Baja',PREPARED:'Preparada',EXPORTED:'Exportada',SENT:'Enviada al banco',CONFIRMED:'Confirmada',RETURNED:'Devuelta',PENDING:'Pendiente',ACCEPTED:'Aceptada',REJECTED:'Rechazada',RESERVED:'Reserva',WAITLIST:'Lista de espera'};
  const state=s=>esc(labels[s]||'En revisión');
  const sources={altas:'Altas y contratos',innux:'Innux',reservas:'Reservas'};
  let run=0, detailRun=0, items=[], more=false, sourceState={}, selected='';
  const alive=n=>root.isConnected&&n===run;
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  root.innerHTML=`<div class="hello"><div><h1>Buscar socios</h1><p class="muted">Encuentra una ficha por nombre, teléfono o número de socio.</p></div></div>
    <form class="card member-search" role="search"><label for="member-query">Nombre, teléfono o número de socio</label><div class="member-search-row"><input id="member-query" type="search" autocomplete="off" minlength="2" maxlength="60" placeholder="Por ejemplo: María, 612345678 o 1234" required><button class="btn" type="submit">Buscar</button></div><p class="muted member-scope">El teléfono se busca en Altas y Reservas. En Innux, utiliza el nombre o el número de socio.</p></form>
    <div class="member-sources" aria-live="polite"></div><p class="member-status muted" role="status">Escribe al menos dos caracteres y pulsa Buscar.</p>
    <div class="member-layout"><section class="member-results" aria-label="Resultados de socios"></section><section class="member-profile" aria-label="Ficha del socio"><div class="card member-empty">Selecciona una ficha para consultar sus datos.</div></section></div>`;
  const input=$('#member-query');input.focus();
  function paintSources(){
    $('.member-sources').innerHTML=Object.entries(sourceState).map(([k,v])=>`<span class="pill ${v.state==='ok'?'':'warn'}">${esc(sources[k])} · ${esc(({ok:k==='innux'?'Nombre y número consultados':'Consultado',pending:'Consultando…',unavailable:'No disponible',forbidden:'Sin permiso'})[v.state]||'No disponible')}</span>`).join('');
  }
  function paintResults(){
    $('.member-status').textContent=items.length?`${items.length} fichas encontradas${more?' · Hay más coincidencias: concreta la búsqueda.':''}`:Object.values(sourceState).some(v=>v.state==='pending')?'Buscando también en Innux…':Object.values(sourceState).some(v=>v.state!=='ok')?'No hay coincidencias en las fuentes disponibles. Algunas no se pudieron consultar.':'No se encontraron socios. Prueba otro nombre, teléfono o número.';
    const repeated=items.some((v,i)=>v.number&&items.some((other,j)=>i!==j&&other.number===v.number));
    if(repeated)$('.member-status').textContent+=' · Hay números repetidos: comprueba el nombre y el teléfono.';
    $('.member-results').innerHTML=items.map((v,i)=>`<button type="button" class="card member-result ${v.ref===selected?'selected':''}" data-member="${i}" aria-pressed="${v.ref===selected}"><strong>${esc(v.name||'Sin nombre')}</strong><span>${v.number?'N.º '+esc(v.number):esc(v.reference||'Sin número de socio')}</span>${v.phone?`<span>${esc(v.phone)}</span>`:''}<small>${esc(sources[v.source])}${v.in_innux?' · Innux':''}${v.state==='BAJA'?' · Baja':''}</small></button>`).join('');
    $('.member-results').querySelectorAll('[data-member]').forEach(b=>b.onclick=()=>open(items[+b.dataset.member]));
  }
  async function search(event){
    event?.preventDefault();const q=input.value.trim();if(q.length<2){input.setCustomValidity('Escribe al menos dos caracteres.');input.reportValidity();return;}input.setCustomValidity('');
    const n=++run;++detailRun;root.classList.remove('member-selected');items=[];selected='';more=false;sourceState={};$('.member-results').replaceChildren();$('.member-profile').innerHTML='<div class="card member-empty">Selecciona una ficha para consultar sus datos.</div>';
    $('.member-status').textContent='Buscando socios…';$('.member-sources').replaceChildren();
    const button=$('form button');button.disabled=true;
    try{
      const d=await api('socios/buscar',{body:{query:q}});if(!alive(n))return;
      items=d.items;more=d.has_more;sourceState=d.sources;paintSources();paintResults();button.disabled=false;
      if(d.pending){
        for(let k=0;k<45&&alive(n);k++){
          await sleep(k<5?350:650);if(!alive(n))return;
          const p=await api('socios/innux',{body:{ref:d.pending}});if(!alive(n))return;
          if(p.state==='DONE'){
            for(const v of p.items){const same=items.find(x=>x.source==='altas'&&x.innux_reference&&x.innux_reference===v.innux_reference);if(same)same.in_innux=true;else items.push(v);}
            more=more||p.has_more;sourceState.innux={state:'ok'};paintSources();paintResults();return;
          }
          if(p.state==='FAILED')break;
        }
        if(alive(n)){sourceState.innux={state:'unavailable'};paintSources();paintResults();}
      }
    }catch(e){if(alive(n)){if(sourceState.innux?.state==='pending'){sourceState.innux={state:'unavailable'};paintSources();paintResults();}else $('.member-status').textContent=e.message;}}
    finally{if(alive(n))button.disabled=false;}
  }
  $('form').onsubmit=search;input.oninput=()=>{input.setCustomValidity('');++run;++detailRun;root.classList.remove('member-selected');items=[];selected='';sourceState={};$('.member-results').replaceChildren();$('.member-sources').replaceChildren();$('.member-profile').innerHTML='<div class="card member-empty">Selecciona una ficha para consultar sus datos.</div>';$('.member-status').textContent='Pulsa Buscar para consultar estos datos.';$('form button').disabled=false;};
  const table=(headers,rows)=>`<div class="member-table"><table><thead><tr>${headers.map(t=>`<th>${esc(t)}</th>`).join('')}</tr></thead><tbody>${rows.map(c=>`<tr>${c.map(t=>`<td>${t}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  async function open(item){
    const n=++detailRun;selected=item.ref;root.classList.add('member-selected');paintResults();const panel=$('.member-profile');panel.innerHTML='<div class="card" role="status">Cargando ficha…</div>';
    try{
      const d=await api('socios/ficha',{body:{ref:item.ref}});if(!root.isConnected||n!==detailRun)return;
      const m=d.member,p=d.portal||{},r=d.reservations||{};
      const innuxId=/^INNUX:([1-9][0-9]*)$/.exec(m.innux_reference||'')?.[1];
      const quotaLink=innuxId&&m.number?`#/clientes/${innuxId}/${encodeURIComponent(m.number)}`:'#/clientes';
      panel.innerHTML=`<button type="button" class="btn ghost member-back">← Volver a resultados</button><article class="card member-heading"><p class="muted">Ficha del socio</p><h2 tabindex="-1">${esc(m.name)}</h2><dl class="member-data"><div><dt>N.º de socio</dt><dd>${esc(m.number||'Sin asignar')}</dd></div><div><dt>Teléfono</dt><dd>${esc(m.phone||'No consta')}</dd></div><div><dt>Correo</dt><dd>${esc(m.email||'No consta')}</dd></div>${m.state?`<div><dt>Estado en Altas</dt><dd>${state(m.state)}</dd></div>`:''}</dl>${d.warnings.map(w=>`<p class="banner">${esc(w)}</p>`).join('')}</article>
        <section class="card"><div class="member-section-head"><h3>Cuotas y acceso en Innux</h3><a class="btn ghost sm" href="${quotaLink}">Gestionar cuotas</a></div><div class="member-quota-status muted">${d.quotas_available?'Consultando Innux…':m.innux_reference?'Innux no está disponible ahora.':'No hay una ficha de Innux vinculada. Busca su número para consultarla.'}</div><div class="member-quotas"></div></section>
        <section class="card"><div class="member-section-head"><h3>Contratos</h3><a class="btn ghost sm" href="#/altas">Abrir Altas</a></div>${p.member?p.contracts?.length?table(['Contrato / tarifa','Fecha','Estado',''],p.contracts.map(c=>[`${esc(c.reference)}<small>${esc(c.tariff)}</small>`,day(c.created_at),state(c.state),`<a class="btn ghost sm" href="#/altas/${esc(c.id)}">Ver contrato</a>`])):'<p class="muted">Sin contratos en esta ficha.</p>':'<p class="muted">No hay una ficha de Altas vinculada o no se pudo consultar. No se ha creado ninguna ficha nueva.</p>'}${p.contracts_more?'<p class="muted">Se muestran los últimos 30 contratos. Consulta el resto en Altas.</p>':''}</section>
        <section class="card"><h3>Domiciliaciones</h3>${p.dues_allowed?p.dues?.length?table(['Periodo','Importe','Estado'],p.dues.map(v=>[esc(v.period),money(v.amount_cents),state(v.state)])):'<p class="muted">Sin cuotas domiciliadas registradas. Esto no indica si tiene una cuota activa en Innux.</p>':'<p class="muted">No hay datos disponibles para esta ficha o tu cuenta no tiene permiso.</p>'}${p.dues_more?'<p class="muted">Se muestran las últimas 30 cuotas.</p>':''}</section>
        <section class="card"><div class="member-section-head"><h3>Reservas y lista de espera</h3><a class="btn ghost sm" href="#/reservas">Gestionar reservas</a></div>${r.unavailable?`<p class="muted">${r.forbidden?'Tu cuenta no tiene acceso a Reservas.':'Reservas no está disponible ahora.'}</p>`:r.items?.length?`${r.items.some(v=>!v.verified)?'<p class="banner">Hay coincidencias por teléfono. Comprueba el nombre: podrían ser de otra persona que comparte el número.</p>':''}${table(['Persona / clase','Fecha y hora','Estado'],r.items.map(v=>[`${esc(v.name)}<small>${esc(v.class)}</small>`,`${day(v.date)}<small>${esc(v.time)}</small>`,v.session_cancelled==1?'Clase cancelada':state(v.state)]))}${r.has_more?'<p class="muted">Se muestran hasta 30 reservas. Consulta el resto en Reservas.</p>':''}`:'<p class="muted">No se localizaron reservas vinculadas ni coincidencias por teléfono.</p>'}</section>
        ${p.withdrawals?.length?`<section class="card"><h3>Últimas bajas y mantenimientos</h3>${table(['Solicitud','Efectiva desde','Estado'],p.withdrawals.map(v=>[v.kind==='MAINTENANCE'?'Mantenimiento':'Baja',day(v.effective_date),state(v.state)]))}</section>`:''}`;
      panel.querySelector('.member-back').onclick=()=>{root.classList.remove('member-selected');const selected=$('.member-result.selected');selected?.focus();selected?.scrollIntoView({block:'center'});};
      panel.querySelector('h2').focus({preventScroll:true});
      if(matchMedia('(max-width:760px)').matches)panel.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
      for(const [kind,ref] of Object.entries(d.jobs||{}))pollQuota(kind,ref,n);
    }catch(e){if(root.isConnected&&n===detailRun){panel.innerHTML=`<div class="card" role="alert">${esc(e.message)}<p>Selecciona la ficha otra vez para reintentar.</p></div>`;root.classList.remove('member-selected');}}
  }
  async function pollQuota(kind,ref,n){
    try{
      for(let k=0;k<45&&root.isConnected&&n===detailRun;k++){
        await sleep(k<5?350:650);if(!root.isConnected||n!==detailRun)return;
        const d=await api('socios/cuotas',{body:{ref}});if(!root.isConnected||n!==detailRun)return;
        if(d.status==='succeeded'){
          if(kind==='client'){
            const c=d.result?.client;$('.member-quota-status').textContent=c?`${c.Activo===true||c.Activo===1?'Ficha activa':'Ficha inactiva'} en Innux · ${c.Nome||''}`:'Consulta de ficha completada.';
          }else{
            const rows=d.result?.quotas||[];$('.member-quotas').innerHTML=rows.length?table(['Tarifa','Desde / hasta','Importe','Pagada'],rows.map(v=>[esc(v.PlanDescripcion||'Cuota'),`${day(v.ValidadeInicio)}<small>${day(v.ValidadeFim)}</small>`,v.Valor!=null?money(Math.round(Number(v.Valor)*100)):'—',(v.Pago===true||v.Pago===1||v.Pago==='1')?'Sí':'No'])):'<p class="muted">Sin cuotas en el historial consultado.</p>';
            if(d.result?.has_more)$('.member-quotas').insertAdjacentHTML('beforeend','<p class="muted">Hay cuotas anteriores. Consúltalas en Gestionar cuotas.</p>');
          }return;
        }
        if(['failed','rejected','review_required','expired','cancelled'].includes(d.status))break;
      }
    }catch(e){/* se conservan los demás datos de la ficha */}
    if(root.isConnected&&n===detailRun){const el=$(kind==='client'?'.member-quota-status':'.member-quotas');el.textContent=kind==='client'?'No se pudo consultar ahora la ficha de Innux.':'No se pudo consultar ahora el historial de cuotas. Vuelve a seleccionar la ficha para reintentar.';}
  }
}
