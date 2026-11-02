(()=>{'use strict';
const T=window.TF,{S,$,e,api,btn,brand,modal,toast}=T;
T.renderTabletActivation=()=>{
  $('app').innerHTML='<main class="login card">'+brand()+'<div class="eyebrow">Inscripción de clientes</div><h1>Alta de socio</h1><p class="muted">Recepción debe activar esta tablet antes de comenzar.</p><form id="tablet-activation-form"><div class="field"><label for="tablet-code">Código de recepción</label><input id="tablet-code" autocomplete="off" autocapitalize="characters" maxlength="40" required></div><div class="actions space-top">'+btn('Activar tablet','tablet_activate','primary','type="submit"')+'</div></form><p class="consent-note space-top">Este acceso solo permite rellenar tu inscripción.</p></main>';
};
T.showTabletInvitation=invitation=>{
  if(invitation.staff_session_closed){
    S.boot.mode='guest';S.boot.user=null;S.detail=null;S.handoff=null;S.configuration=null;S.billingRows=[];S.exportPreview=null;S.exportIds=[];
    $('app').innerHTML='<main class="login card">'+brand()+'<h1>Sesión del personal cerrada</h1><p class="muted">El código solo activa el formulario de clientes.</p><a href="/alta/admin/">Volver al acceso del personal</a></main>';
  }
  modal('<h2>Activar formulario de clientes</h2><p>Abre <strong>whatsapp.gimnasio.example/alta/</strong> en la tablet e introduce este código.</p><div class="field space-top"><label>Código de un solo uso · válido 15 minutos</label><input id="issued-tablet-code" value="'+e(invitation.code)+'" readonly autocomplete="off"></div><div class="actions space-top">'+btn('Copiar código','copy_tablet_code','primary')+'<a href="/alta/" target="_blank" rel="noopener">Abrir formulario de clientes ↗</a></div><p class="consent-note space-top">Por seguridad, se ha cerrado esta sesión del personal. Para volver al panel tendrás que identificarte de nuevo.</p>');
};
T.issueTabletInvitation=async()=>modal('<h2>Activar una tablet de clientes</h2><p>Vas a generar un código de un solo uso para introducirlo en la tablet.</p><p><strong>Por seguridad, se cerrará tu sesión de Altas en este dispositivo.</strong> Podrás volver desde el Centro de control.</p><div class="modal-footer">'+btn('Cancelar','close_modal','ghost')+btn('Generar código y cerrar sesión','tablet_issue_confirm','primary')+'</div>');
T.tabletAction=async action=>{
  if(action==='tablet_issue_confirm'){T.showTabletInvitation(await api('tablet_invitation'));return;}
  if(action==='tablet_activate'){
    if(!$('tablet-activation-form').reportValidity())return;
    await api('tablet_activate',{code:$('tablet-code').value});$('tablet-code').value='';S.loginScreen=false;await T.boot();
  }
  if(action==='tablet_lock'){await api('tablet_lock');await T.boot();}
  if(action==='copy_tablet_code'){
    if(!navigator.clipboard)throw new Error('Selecciona y copia el código de la pantalla.');
    await navigator.clipboard.writeText($('issued-tablet-code').value);toast('Código copiado.');
  }
};
document.addEventListener('submit',async ev=>{
  if(ev.target.id!=='tablet-activation-form'||S.busy)return;
  ev.preventDefault();S.busy=true;
  try{await T.tabletAction('tablet_activate');}catch(error){toast(error.message,true);}finally{S.busy=false;}
});
})();
