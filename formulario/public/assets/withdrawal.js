(()=>{'use strict';
/* Tablet: el socio pide su baja definitiva o su mantenimiento (baja temporal), firma y recibe copia por correo. */
const T=window.TF,{S,$,e,money,btn,brand,strip,field,check,api,toast,render}=T;
const STEPS=['Tipo','Identificación','Tus datos','Revisión y firma'];
const REASONS=[['','Prefiero no decirlo'],['price','Precio'],['schedule','Horario'],['moving','Cambio de domicilio'],['injury','Lesión o salud'],['other','Otro motivo']];
const dmy=v=>v?v.split('-').reverse().join('-'):'';
const W=()=>S.withdrawal;

function layout(step,title,hint,body,actions){
  const rail='<aside class="rail">'+brand()+'<ol class="rail-steps" aria-label="Pasos de la baja">'+STEPS.map((n,i)=>'<li class="'+(i===step?'active':i<step?'done':'')+'"'+(i===step?' aria-current="step"':'')+'><span class="rail-mark">'+(i+1)+'</span><span class="rail-label">'+n+'</span></li>').join('')+'</ol><div class="rail-foot">'+btn('Cancelar','w_exit','rail-cancel')+'</div></aside>';
  return strip()+'<div class="shell">'+rail+'<main class="stage"><div class="stage-body"><header class="stage-head"><h1>'+title+'</h1><p>'+hint+'</p></header><form id="withdrawal-form" novalidate>'+body+'</form></div><div class="actionbar">'+actions+'</div></main></div>';
}

function typeStep(){
  const k=W().kind;const opt=(kind,title,lines)=>`<button type="button" class="choice ${k===kind?'selected':''}" data-action="w_kind" data-kind="${kind}" aria-pressed="${k===kind}"><strong>${title}</strong>${lines.map(l=>'<small>'+l+'</small>').join('')}</button>`;
  return layout(0,'¿Qué necesitas?','Elige si te vas del todo o si quieres hacer una pausa.',
    '<div class="option-grid withdrawal-kinds">'+opt('MAINTENANCE','Mantenimiento','Una pausa sin fecha de vuelta|Acumulas 5,00 € por cada mes fuera y los pagas al volver|Al volver no pagas matrícula'.split('|'))+opt('PERMANENT','Baja definitiva','Dejas de ser socio|Si vuelves algún día, sería un alta nueva con matrícula'.split('|'))+'</div><p class="consent-note space-top">En los dos casos puedes seguir entrenando hasta el último día de este mes, que ya está pagado.</p>',
    btn('Volver al inicio','w_exit','ghost')+btn('Continuar','w_kind_next','primary',k?'':'disabled'));
}

function identifyStep(){
  const p=W().id||{};
  return layout(1,'Identifícate','Con tu documento y tu fecha de nacimiento buscamos tu ficha.',
    `<div class="form-grid"><div class="field"><label for="w-doc-type">Tipo de documento</label><select id="w-doc-type">${[['DNI','DNI / NIF'],['NIE','NIE'],['PASSPORT','Pasaporte']].map(([v,l])=>`<option value="${v}" ${p.document_type===v?'selected':''}>${l}</option>`).join('')}</select></div>${field('Número de documento','w-doc',p.document||'','text','required autocomplete="off" autocapitalize="characters"')}${field('Fecha de nacimiento','w-birth',p.birth_date||'','date','required')}</div>`,
    btn('Atrás','w_back','ghost')+btn('Continuar','w_identify','primary'));
}

function detailsStep(){
  const w=W(),d=w.data||{};
  const who=w.found?`<div class="notice"><strong>Hola, ${e(w.name)}.</strong>${w.member_number?' Socio n.º '+e(w.member_number)+'.':''} Ya tenemos tus datos.</div>${field('Correo para recibir la copia'+(w.email_hint?' (ahora: '+w.email_hint+')':''),'w-email',d.email||'','email','placeholder="Déjalo vacío para usar el de tu ficha" autocomplete="off"',true)}`
    :`<div class="notice warn">No encontramos tu ficha en el sistema nuevo (es normal si te diste de alta en papel). Rellena estos datos para que recepción te localice.</div><div class="form-grid">${field('Nombre','w-name',d.name||'','text','required')}${field('Apellidos','w-surname',d.surname||'','text','required')}${field('Teléfono','w-phone',d.phone||'','tel','required')}${field('Correo electrónico','w-email',d.email||'','email','required')}${field('N.º de socio · opcional','w-number',d.member_number||'','text','inputmode="numeric"')}</div>`;
  return layout(2,'Tus datos',w.kind==='MAINTENANCE'?'Comprueba tus datos para el mantenimiento.':'Comprueba tus datos para la baja.',
    who+`<div class="section-title space-top"><h3>¿Nos cuentas el motivo?</h3></div><div class="form-grid"><div class="field"><label for="w-reason">Motivo · opcional</label><select id="w-reason">${REASONS.map(([v,l])=>`<option value="${v}" ${d.reason===v?'selected':''}>${l}</option>`).join('')}</select></div>${field('Comentario · opcional','w-reason-text',d.reason_text||'','text','maxlength="200"')}</div><p class="consent-note">Nos ayuda a mejorar. No cambia nada de tu solicitud.</p>`,
    btn('Atrás','w_back','ghost')+btn('Continuar','w_details','primary'));
}

function reviewStep(){
  const s=W().review.summary,m=s.kind==='MAINTENANCE';
  return layout(3,'Revisión y firma','Revisa el documento completo antes de firmar.',
    `<div class="bill"><div><span>Puedes entrenar hasta</span><strong>${e(dmy(s.last_day))}</strong></div><div><span>${m?'Empieza el mantenimiento':'Baja efectiva desde'}</span><strong>${e(dmy(s.effective_date))}</strong></div>${m?`<div><span>Recargo por mes completo fuera</span><strong>${money(s.fee_cents_per_month)}</strong></div><div><span>Al volver pagas</span><strong>Cuota del mes + recargo, sin matrícula</strong></div>`:''}</div>
    <iframe title="Solicitud completa antes de firmar" class="pdf-frame space-top" src="api.php?action=withdrawal_review"></iframe><a class="print-link" href="api.php?action=withdrawal_preview" target="_blank" rel="noopener">Abrir la vista previa del PDF</a>
    <div class="section-title space-top"><h3>Tu firma</h3>${btn('Borrar y repetir','clear_signature','ghost small','type="button"')}</div><div class="signature-wrap"><canvas id="signature" aria-label="Dibuja tu firma con el dedo o lápiz"></canvas></div>${check('confirm_signature',m?'He revisado la solicitud y confirmo que quiero pasar a mantenimiento.':'He revisado la solicitud y confirmo que quiero darme de baja.')}<p class="consent-note">Firma dibujada en pantalla. No se presenta como firma electrónica cualificada.${s.email?' Te enviaremos una copia a '+e(s.email)+'.':''}</p>`,
    btn('Atrás','w_back','ghost')+btn('Firmar solicitud','w_sign','primary','id="sign-contract" disabled'));
}

function doneStep(){
  const r=W().receipt,m=r.kind==='MAINTENANCE';
  return strip()+`<main class="done-screen"><section class="complete goodbye"><h1>${m?'¡Te esperamos a la vuelta!':'Sentimos que te vayas'}</h1><p class="lead">${m?'Tu mantenimiento está registrado. Cuando quieras volver, pásate por recepción: solo pagarás la cuota del mes y el recargo acumulado, sin matrícula.':'Gracias por haber entrenado con nosotros. Aquí tienes tu casa si algún día quieres volver.'}</p><p class="muted">Puedes seguir entrenando hasta el <strong>${e(dmy(r.last_day))}</strong>. Recepción revisará tu solicitud.</p><p class="mono">${e(r.reference)}</p><div class="actions space-top"><a href="api.php?action=withdrawal_document&id=${encodeURIComponent(r.id)}">Descargar mi PDF</a></div><div class="actions space-top">${btn('Terminar','w_finish','primary')}</div><p class="consent-note space-top">Tus datos ya no se muestran en esta pantalla.</p></section></main>`;
}

function renderWithdrawal(){
  const w=W();$('app').innerHTML=({type:typeStep,identify:identifyStep,details:detailsStep,review:reviewStep,done:doneStep}[w.step]||typeStep)();
  if(w.step==='review')T.setupSignature();window.scrollTo({top:0});
}
const val=id=>($(id)?.value||'').trim();

async function action(a,t){const w=W();switch(a){
  case 'w_begin':T.wipe();S.withdrawal={step:'type',kind:null};render();break;
  case 'w_kind':w.kind=t.dataset.kind;render();break;
  case 'w_kind_next':if(!w.kind)throw new Error('Elige baja definitiva o mantenimiento.');await api('withdrawal_start',{kind:w.kind});w.step='identify';render();break;
  case 'w_identify':{if(!$('withdrawal-form').reportValidity())return;w.id={document_type:val('w-doc-type'),document:val('w-doc'),birth_date:val('w-birth')};
    const r=await api('withdrawal_identify',w.id);Object.assign(w,{found:r.found,name:r.name,member_number:r.member_number,email_hint:r.email_hint,step:'details',data:{}});render();break;}
  case 'w_details':{if(!$('withdrawal-form').reportValidity())return;
    w.data=w.found?{email:val('w-email')}:{name:val('w-name'),surname:val('w-surname'),phone:val('w-phone'),email:val('w-email'),member_number:val('w-number')};
    Object.assign(w.data,{reason:val('w-reason'),reason_text:val('w-reason-text')});
    await api('withdrawal_save',w.data);w.review=await api('withdrawal_prepare');S.sig=[];w.step='review';render();break;}
  case 'w_back':w.step={identify:'type',details:'identify',review:'details'}[w.step]||'type';render();break;
  case 'w_sign':{const r=await api('withdrawal_sign',{confirmed:$('confirm_signature').checked,review_hash:w.review.review_hash,signature:S.sig});if(r.csrf)S.boot.csrf=r.csrf;S.sig=[];w.receipt=r;w.step='done';render();break;}
  case 'w_exit':if(w&&w.step!=='type'&&!confirm('¿Cancelar la solicitud? Se borrarán los datos que has escrito.'))return;await api('withdrawal_cancel').then(r=>{if(r.csrf)S.boot.csrf=r.csrf;}).catch(()=>{});S.withdrawal=null;S.sig=[];render();break;
  case 'w_finish':await api('withdrawal_cancel').then(r=>{if(r.csrf)S.boot.csrf=r.csrf;}).catch(()=>{});S.withdrawal=null;S.sig=[];render();break;
}}
T.renderWithdrawal=renderWithdrawal;T.withdrawalAction=action;
})();
