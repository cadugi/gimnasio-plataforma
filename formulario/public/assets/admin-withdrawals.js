(()=>{'use strict';
/* Panel: bajas definitivas y mantenimientos firmados en la tablet. Recepción los revisa, los tramita en Innux y los acepta. */
const T=window.TF,{S,$,e,money,date,chip,btn,field,api,toast,modal,closeModal}=T;
Object.assign(T.labels,{PENDING:'Pendiente',ACCEPTED:'Aceptada',REJECTED:'Rechazada',PERMANENT:'Baja definitiva',MAINTENANCE:'Mantenimiento',RETURNED_MAINTENANCE:'Ha vuelto',IN_MAINTENANCE:'En mantenimiento'});
const canStaff=()=>['admin','staff'].includes(S.boot.user?.role);
const kindChip=k=>chip(k,k==='PERMANENT'?'red':'blue');
const stateChip=w=>w.state==='ACCEPTED'&&w.kind==='MAINTENANCE'?chip(w.returned_at?'RETURNED_MAINTENANCE':'IN_MAINTENANCE',w.returned_at?'green':'blue'):chip(w.state,w.state==='ACCEPTED'?'green':w.state==='REJECTED'?'red':'orange');
const ymd=dmy=>dmy.split('-').reverse().join('-');

async function withdrawalsPage(){
  const rows=await api('withdrawals');const f=S.withdrawalFilter||'PENDING';
  const shown=rows.filter(w=>f==='ALL'||(f==='MAINTENANCE'?w.kind==='MAINTENANCE'&&w.state==='ACCEPTED'&&!w.returned_at:w.state===f));
  const tabs=[['PENDING','Pendientes'],['MAINTENANCE','En mantenimiento'],['ACCEPTED','Aceptadas'],['REJECTED','Rechazadas'],['ALL','Todas']];
  return `<div class="brand-toggle" role="group" aria-label="Filtrar bajas">${tabs.map(([k,l])=>btn(l+(k==='PENDING'?' ('+rows.filter(w=>w.state==='PENDING').length+')':''),'wa_filter',f===k?'selected':'',`data-filter="${k}"`)).join('')}</div>`+
    T.table(['Socio / referencia','Tipo','Solicitada','Efecto','Estado',''],shown.map(w=>T.tr([`<strong>${e(w.name)}</strong><small>${e(w.reference)}${w.member_number?' · Socio '+e(w.member_number):''}</small>`,kindChip(w.kind),date(w.created_at),date(w.effective_date),stateChip(w),btn('Ver','wa_detail','ghost small',`data-id="${e(w.id)}"`)])));
}

/* Historial: altas (contratos) y bajas juntas, en cualquier estado. Solo consulta; filtra en el navegador. */
const H_KIND={ENROLLMENT:'Alta',NEW_VERSION:'Alta (nueva versión)',PERMANENT:'Baja definitiva',MAINTENANCE:'Mantenimiento'};
const H_STATE={PENDING:'Pendiente',ACCEPTED:'Aceptada',REJECTED:'Rechazada',ANNULLED:'Anulada'};
const hState=r=>r.kind==='MAINTENANCE'&&r.state==='ACCEPTED'?(r.returned_at?'Ha vuelto':'En mantenimiento'):H_STATE[r.state]||r.state;
const madridDay=v=>v?(v.length===10?v:new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Madrid'}).format(new Date(v))):'';
function historyRows(){const f=S.history||{},q=(f.query||'').toLowerCase().trim();
  return (S.historyRows||[]).filter(r=>(!f.kind||(f.kind==='ALTA'?r.source==='contract':f.kind==='BAJA'?r.source==='withdrawal':r.kind===f.kind))&&(!f.state||r.state===f.state)
    &&(!f.from||madridDay(r.created_at)>=f.from)&&(!f.until||madridDay(r.created_at)<=f.until)&&(!q||(r.name+' '+r.reference+' '+(r.member_number||'')).toLowerCase().includes(q)));}
async function historyPage(){
  S.historyRows=await api('history');const f=S.history||{},rows=historyRows(),opt=(v,l,cur)=>`<option value="${v}" ${cur===v?'selected':''}>${l}</option>`;
  const count=k=>rows.filter(r=>r.source===k).length;
  return `<div class="filter-bar">${field('Socio, n.º o referencia','hist-q',f.query||'','search','placeholder="Buscar…"')}${field('Desde','hist-from',f.from||'','date')}${field('Hasta','hist-until',f.until||'','date')}
  <div class="field"><label for="hist-kind">Tipo</label><select id="hist-kind">${opt('','Todos',f.kind||'')}${opt('ALTA','Altas',f.kind)}${opt('BAJA','Bajas y mantenimientos',f.kind)}${opt('PERMANENT','Solo bajas definitivas',f.kind)}${opt('MAINTENANCE','Solo mantenimientos',f.kind)}</select></div>
  <div class="field"><label for="hist-state">Estado</label><select id="hist-state">${opt('','Todos',f.state||'')}${opt('PENDING','Pendiente',f.state)}${opt('ACCEPTED','Aceptada',f.state)}${opt('REJECTED','Rechazada',f.state)}${opt('ANNULLED','Anulada',f.state)}</select></div>
  ${btn('Filtrar','wa_hist_apply','dark')}${btn('Descargar para Excel','wa_hist_csv','ghost')}</div>
  <p class="muted">${rows.length} registros · ${count('contract')} altas · ${count('withdrawal')} bajas/mantenimientos</p>`+
  T.table(['Fecha','Tipo','Socio / referencia','Estado','Tramitada','Efecto',''],rows.map(r=>T.tr([date(r.created_at),r.source==='contract'?chip(H_KIND[r.kind],'green'):kindChip(r.kind),
    `<strong>${e(r.name)}</strong><small>${e(r.reference)}${r.member_number?' · Socio '+e(r.member_number):''}</small>`,e(hState(r)),
    r.decided_at?date(r.decided_at)+(r.decided_actor?'<small>'+e(r.decided_actor_name||r.decided_actor)+'</small>':''):'—',r.effective_date?date(r.effective_date):'—',
    btn('Ver',r.source==='contract'?'contract_detail':'wa_detail','ghost small',`data-id="${e(r.id)}"`)])));
}
function historyCsv(){
  const cell=v=>{const s=String(v??'');return /[";\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;};
  const lines=[['Fecha solicitud','Tipo','Socio','N.º socio','Referencia','Estado','Tramitada el','Tramitada por','Fecha efecto','Fecha vuelta'].join(';')]
    .concat(historyRows().map(r=>[date(r.created_at),H_KIND[r.kind],r.name,r.member_number,r.reference,hState(r),r.decided_at?date(r.decided_at):'',r.decided_actor_name||r.decided_actor,r.effective_date?date(r.effective_date):'',r.returned_at?date(r.returned_at):''].map(cell).join(';')));
  const url=URL.createObjectURL(new Blob(['﻿'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='historial-altas-bajas-'+madridDay(new Date().toISOString())+'.csv';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

async function detail(id){
  const d=await api('withdrawal_detail',{id});S.withdrawalDetail=d;const p=d.personal,m=d.kind==='MAINTENANCE';
  const pair=(k,v)=>`<div class="detail-pair"><small>${e(k)}</small><strong>${v}</strong></div>`;
  let actions='';
  if(d.state==='PENDING'&&canStaff())actions=`<div class="card"><h3>Tramitar</h3><p class="consent-note">Revisa los datos, ${m?'pon la ficha en pausa en Innux y la domiciliación si la hay. Después acéptala aquí.':'al aceptarla, el socio se elimina de Innux con todas sus relaciones el día en que la baja es efectiva, y su ficha completa y sus contratos firmados quedan en el histórico. No hace falta hacerlo a mano.'}</p>${T.check('wa-done',m?'Ya la he tramitado en Innux':'Entiendo que se elimina de Innux y queda su histórico')}<div class="actions space-top">${btn('Aceptar','wa_accept','primary',`data-id="${e(id)}"`)}${btn('Rechazar','wa_reject_open','ghost',`data-id="${e(id)}"`)}</div></div>`;
  if(m&&d.state==='ACCEPTED'&&!d.returned_at&&canStaff()){
    const tariffs=S.boot.catalog?.tariffs||[];
    actions=`<div class="card"><h3>Registrar la vuelta</h3><p class="consent-note">Cobra en recepción el recargo de los meses fuera y la cuota del mes de vuelta (proporcional). Sin matrícula.</p>${field('Fecha de vuelta','wa-date',ymd(S.boot.server_date),'date')}<div class="field"><label for="wa-tariff">Tarifa con la que vuelve</label><select id="wa-tariff">${tariffs.map(t=>`<option value="${e(t.id)}" data-monthly="${e(t.monthly_cents)}" ${t.id===d.default_tariff_id?'selected':''}>${e(t.name)} · ${money(t.monthly_cents)}</option>`).join('')}</select></div><div id="wa-quote" class="bill space-top"></div><div class="actions space-top">${btn('Registrar vuelta','wa_return','primary',`data-id="${e(id)}"`)}</div></div>`;
  }
  const back=d.returned_at?`<div class="card"><h3>Vuelta registrada</h3>${pair('Fecha de vuelta',date(d.returned_at))}${pair('Meses fuera',e(d.return_months))}${pair('Recargo',money(d.return_fee_cents))}${pair('Cuota del mes de vuelta',money(d.return_renewal_cents))}${pair('Total cobrado',money(Number(d.return_fee_cents)+Number(d.return_renewal_cents)))}</div>`:'';
  modal(`<h2 class="modal-title">${e(p.name+' '+p.surname)}</h2><p class="mono muted">${e(d.reference)}</p><div class="actions">${kindChip(d.kind)}${stateChip(d)}</div>
  <div class="details-grid space-top"><div class="card"><h3>Solicitud</h3>${pair('Firmada',e(d.date_local))}${pair('Puede entrenar hasta',date(d.last_day))}${pair(m?'Empieza el mantenimiento':'Baja efectiva',date(d.effective_date))}${m?pair('Recargo',money(d.fee_cents_per_month)+' por mes completo'):''}${pair('Motivo',e(d.reason_label?(d.reason_label+(d.reason_text?' · '+d.reason_text:'')):'No indicado'))}<a class="print-link" href="api.php?action=withdrawal_document&inline=1&id=${encodeURIComponent(id)}" target="_blank" rel="noopener">Ver el PDF firmado</a></div>
  <div class="card"><h3>Socio</h3>${pair('N.º socio',e(d.member_number||'No indicado'))}${pair('Documento',e(p.document_type+' '+p.document))}${pair('Nacimiento',date(p.birth_date))}${pair('Teléfono',e(p.phone||'—'))}${pair('E-mail',e(p.email||'—'))}${pair('En el sistema',d.member_linked?'Sí, ficha vinculada':'No (alta antigua o en papel): búscalo en Innux')}${pair('Copia por correo',e({SENT:'Enviada',QUEUED:'En cola',RETRY:'Reintentando',SENDING:'Enviando',FAILED:'Falló'}[d.email?.state]||'Sin correo'))}</div>
  ${d.state!=='PENDING'?`<div class="card"><h3>Decisión</h3>${pair(d.state==='REJECTED'?'Rechazada':'Aceptada',date(d.decided_at)+' · '+e(d.decided_actor))}${d.reject_reason?pair('Motivo del rechazo',e(d.reject_reason)):''}</div>`:''}${back}${actions}</div>`);
  quote();
}

function quote(){
  const box=$('wa-quote'),d=S.withdrawalDetail;if(!box||!d)return;const day=$('wa-date').value,opt=$('wa-tariff').selectedOptions[0];
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||!opt){box.innerHTML='';return;}
  const [ey,em]=d.effective_date.split('-').map(Number),[ry,rm]=day.split('-').map(Number),months=Math.max(0,(ry-ey)*12+rm-em);
  const renew=T.prorate(Number(opt.dataset.monthly),day.split('-').reverse().join('-')),fee=months*d.fee_cents_per_month;
  box.innerHTML=`<div><span>Recargo (${months} ${months===1?'mes':'meses'} × ${money(d.fee_cents_per_month)})</span><strong>${money(fee)}</strong></div><div><span>Cuota del ${renew.from} al ${renew.to}</span><strong>${money(renew.cents)}</strong></div><div class="total"><span>Total a cobrar</span><span>${money(fee+renew.cents)}</span></div>`;
}
document.addEventListener('change',ev=>{if(['wa-date','wa-tariff'].includes(ev.target.id))quote();});

async function action(a,t){switch(a){
  case 'wa_filter':S.withdrawalFilter=t.dataset.filter;T.render();break;
  case 'wa_hist_apply':S.history={query:$('hist-q').value,from:$('hist-from').value,until:$('hist-until').value,kind:$('hist-kind').value,state:$('hist-state').value};T.render();break;
  case 'wa_hist_csv':historyCsv();break;
  case 'wa_detail':await detail(t.dataset.id);break;
  case 'wa_accept':if(!$('wa-done').checked){toast('Marca la casilla para continuar.',true);break;}const d=await api('withdrawal_accept',{id:t.dataset.id,confirmed:true});const r=d?.retirement||{};toast('Solicitud aceptada. '+(r.state==='QUEUED'?(r.due?'El socio se está eliminando de Innux.':'Se eliminará de Innux el '+r.not_before.split('-').reverse().join('/')+'.'):r.state==='BLOCKED'?'No se pudo programar la eliminación de Innux (hay un alta pendiente). Hazlo desde «Eliminar socios».':r.state==='NOT_LINKED'?'El socio no tiene ficha vinculada en Innux: revísalo en «Eliminar socios».':'Sigue disponible en «Aceptadas» y en «Historial altas y bajas».'));closeModal();T.render();break;
  case 'wa_reject_open':S.withdrawalReject=t.dataset.id;modal(`<h2>Rechazar la solicitud</h2><p>El socio seguirá activo. Indica el motivo (queda en el registro).</p>${field('Motivo','wa-reason','')}<div class="modal-footer">${btn('Rechazar solicitud','wa_reject','primary')}${btn('Volver','wa_detail','ghost',`data-id="${e(S.withdrawalReject)}"`)}</div>`);break;
  case 'wa_reject':await api('withdrawal_reject',{id:S.withdrawalReject,reason:$('wa-reason').value});toast('Solicitud rechazada');closeModal();T.render();break;
  case 'wa_return':{const r=await api('withdrawal_return',{id:t.dataset.id,date:$('wa-date').value,tariff_id:$('wa-tariff').value});toast('Vuelta registrada. Cobrar '+money(r.total_cents));await detail(t.dataset.id);break;}
}}
T.withdrawalsPage=withdrawalsPage;T.historyPage=historyPage;T.withdrawalAdminAction=action;
})();
