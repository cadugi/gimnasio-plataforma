(()=>{'use strict';
const T=window.TF,{S,$,e,btn,api,toast}=T;let preview=null,revision=0;
T.clearPhotoPreview=()=>{revision++;preview=null;};
T.photoSection=()=>'<section class="photo-section"><h3>Foto para la ficha</h3><p class="muted">Puedes hacerla con la tablet. Si necesitas ayuda, déjala para recepción.</p>'+
  (S.boot.draft?.photo?'<img class="enrollment-photo" src="api.php?action=draft_photo" alt="Tu foto guardada"><p>Foto guardada</p>'+btn('Quitar foto','photo_remove','ghost small'):'')+
  '<label class="photo-picker">Hacer o elegir foto<input id="enrollment-photo-input" type="file" accept="image/jpeg,image/png,image/webp" capture="user"></label><div id="photo-preview" aria-live="polite"></div></section>';
async function prepare(file){
  const ticket=++revision;preview=null;
  if(!file||file.size>12000000||!['image/jpeg','image/png','image/webp'].includes(file.type))throw new Error('Elige una foto JPEG, PNG o WebP de menos de 12 MB.');
  const image=new Image(),url=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('No se pudo leer la foto.'));reader.readAsDataURL(file);});
  try{
    image.src=url;await image.decode();
    if(ticket!==revision||!$('photo-preview'))return;
    if(image.naturalWidth<160||image.naturalHeight<160||image.naturalWidth*image.naturalHeight>40000000)throw new Error('Elige una foto de tamaño adecuado.');
    const scale=Math.min(1,960/image.naturalWidth,960/image.naturalHeight),canvas=document.createElement('canvas');
    canvas.width=Math.round(image.naturalWidth*scale);canvas.height=Math.round(image.naturalHeight*scale);
    if(canvas.width<160||canvas.height<160)throw new Error('La foto es demasiado estrecha.');
    const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);
    preview=canvas.toDataURL('image/jpeg',0.82);
    if(preview.length>730000)throw new Error('La foto ocupa demasiado. Prueba otra imagen.');
    $('photo-preview').innerHTML='<img class="enrollment-photo" src="'+preview+'" alt="Vista previa de tu foto"><p>¿Quieres usar esta foto en tu ficha?</p>'+btn('Guardar esta foto','photo_save','primary small')+btn('Descartar','photo_discard','ghost small');
  }finally{image.src='';}
}
T.photoAction=async action=>{
  if(action==='photo_save'){
    if(!preview)throw new Error('Primero elige una foto.');
    const photo=await api('photo_save',{image:preview,confirmed:true});S.boot.draft.photo=photo;S.review=null;
    T.clearPhotoPreview();document.querySelector('.photo-section').outerHTML=T.photoSection();toast('Foto guardada.');
  }
  if(action==='photo_remove'){
    await api('photo_remove');S.boot.draft.photo=null;S.review=null;
    document.querySelector('.photo-section').outerHTML=T.photoSection();
  }
  if(action==='photo_discard'){T.clearPhotoPreview();$('photo-preview').replaceChildren();$('enrollment-photo-input').value='';}
};
document.addEventListener('change',ev=>{if(ev.target.id==='enrollment-photo-input'){prepare(ev.target.files[0]).catch(error=>{preview=null;toast(error.message,true);});}});
document.addEventListener('visibilitychange',()=>{if(document.hidden){T.clearPhotoPreview();$('photo-preview')?.replaceChildren();if($('enrollment-photo-input'))$('enrollment-photo-input').value='';}});
T.enrollmentInbox=async()=>{
  const d=await api('enrollment_inbox'),pending=d.items.filter(v=>!['MANUALLY_CONFIRMED','VERIFIED_READ_ONLY','VERIFIED_CONNECTOR','CANCELLED'].includes(v.innux_state));
  return '<div class="notice">Revisa los datos de cada alta. Al aceptarla se envía a Innux y el programa del PC crea la ficha cuando Innux está disponible.</div><div class="section-title space-top"><span></span>'+btn('Actualizar la lista','nav','ghost small','data-page="registrations"')+'</div><div class="table-wrap"><table><thead><tr><th>Socio</th><th>Fecha</th><th>Foto</th><th>Contrato</th><th></th></tr></thead><tbody>'+
    (pending.map(v=>'<tr><td><strong>'+e(v.name)+'</strong><small>'+e(v.reference)+'</small></td><td>'+T.date(v.created_at)+'</td><td>'+(v.has_photo?'Guardada':'Pendiente')+'</td><td>'+(v.center_accepted_at?'Aceptado por el centro':'Por revisar')+'</td><td>'+btn('Revisar alta','contract_detail','primary small','data-id="'+e(v.id)+'"')+'</td></tr>').join('')||'<tr><td colspan="5" class="empty">No hay altas pendientes de Innux.</td></tr>')+'</tbody></table></div>';
};
})();
