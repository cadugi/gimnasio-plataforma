// Pantalla de oferta con Chromium real y servidor simulado. Uso: node tests/ui/oferta_ui.js [carpeta_capturas]
const {chromium}=require('/home/ubuntu/.npm/_npx/381cec31605a419a/node_modules/playwright-core');
const BASE='http://127.0.0.1:8765';const OUT=process.argv[2]||'/tmp';let fails=0;const TOK='a'.repeat(64);
const ok=(c,m)=>{if(!c){fails++;console.log('FAIL',m);}else console.log('ok  ',m);};
const state=async()=>(await fetch(BASE+'/x',{method:'PATCH'})).json();
const reset=async(q='')=>fetch(BASE+'/x'+q,{method:'DELETE'});
(async()=>{
 const b=await chromium.launch({executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args:['--no-sandbox']});
 const mk=async(w=360)=>{const c=await b.newContext({viewport:{width:w,height:740},isMobile:true,hasTouch:true});const p=await c.newPage();p.errs=[];p.on('pageerror',e=>p.errs.push(e.message));return p;};
 const txt=p=>p.evaluate(()=>document.body.innerText);
 // abrir NO acepta
 await reset();let p=await mk();await p.goto(BASE+'/reservas/oferta.html#'+TOK);await p.waitForTimeout(600);
 ok((await txt(p)).includes('Yoga')&&(await txt(p)).includes('18:00')&&(await txt(p)).includes('hasta las 17:42'),'muestra clase, día, hora y la hora límite real');
 ok((await state()).of_posts===0&&(await state()).offer==='PENDING','abrir la oferta no modifica nada (ninguna escritura)');
 ok((await txt(p)).includes('Abrir este aviso no te apunta'),'explica que abrir no apunta');
 const bad=await p.evaluate(()=>{const o=[];document.querySelectorAll('button,a').forEach(e=>{const r=e.getBoundingClientRect();if(r.width&&r.height<48)o.push(e.textContent)});document.querySelectorAll('body *').forEach(e=>{if([...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())&&e.getBoundingClientRect().width&&parseFloat(getComputedStyle(e).fontSize)<18)o.push('txt '+e.textContent.slice(0,20))});return o});
 ok(bad.length===0,'texto ≥18 px y botones ≥48 px '+bad.join('|'));await p.screenshot({path:OUT+'/10-oferta.png',fullPage:true});
 // doble pulsación = una sola escritura y mensaje persistente
 await p.getByRole('button',{name:'Aceptar plaza'}).dblclick();await p.waitForTimeout(700);
 ok((await txt(p)).includes('Plaza confirmada'),'aceptar: «Plaza confirmada»');ok((await state()).of_posts===1,'doble pulsación: una sola petición');
 await p.waitForTimeout(5000);ok((await txt(p)).includes('Plaza confirmada'),'la confirmación no desaparece sola');
 await p.screenshot({path:OUT+'/11-oferta-ok.png',fullPage:true});
 // rechazar pide confirmación
 await reset();p=await mk();await p.goto(BASE+'/reservas/oferta.html#'+TOK);await p.waitForTimeout(500);
 await p.getByRole('button',{name:'No quiero la plaza'}).click();ok((await txt(p)).includes('¿Seguro que no la quieres?')&&(await state()).of_posts===0,'rechazar pide confirmar antes de escribir');
 await p.getByRole('button',{name:'No, volver'}).click();ok((await state()).of_posts===0,'volver no cambia nada');
 await p.getByRole('button',{name:'No quiero la plaza'}).click();await p.getByRole('button',{name:'Sí, no quiero la plaza'}).click();await p.waitForTimeout(600);
 ok((await txt(p)).includes('Ya no estás en la lista de espera')&&(await state()).offer==='DECLINED','rechazo confirmado');
 // caducada
 await reset('?expired');p=await mk();await p.goto(BASE+'/reservas/oferta.html#'+TOK);await p.waitForTimeout(600);
 ok((await txt(p)).includes('Ha pasado el tiempo')&&await p.getByRole('button',{name:'Aceptar plaza'}).count()===0||!(await p.getByRole('button',{name:'Aceptar plaza'}).isVisible()),'oferta caducada: sin botón de aceptar');
 // enlace falso
 p=await mk();await p.goto(BASE+'/reservas/oferta.html#'+'b'.repeat(64));await p.waitForTimeout(600);ok((await txt(p)).includes('no es válido'),'enlace falso: mensaje claro');
 p=await mk();await p.goto(BASE+'/reservas/oferta.html');await p.waitForTimeout(400);ok((await txt(p)).includes('no es válido'),'sin enlace: mensaje claro');
 // sin conexión
 await reset();p=await mk();await p.goto(BASE+'/reservas/oferta.html#'+TOK);await p.waitForTimeout(500);await p.context().setOffline(true);
 await p.getByRole('button',{name:'Aceptar plaza'}).click();await p.waitForTimeout(500);ok((await txt(p)).includes('No se ha confirmado nada'),'sin conexión: dice que no se ha confirmado');
 // otro aviso con la pantalla vieja abierta: cambia el # y debe recargarse con la oferta nueva
 await reset();p=await mk();await p.goto(BASE+'/reservas/oferta.html#'+TOK);await p.waitForTimeout(500);await p.getByRole('button',{name:'Aceptar plaza'}).click();await p.waitForTimeout(500);
 ok((await txt(p)).includes('Plaza confirmada'),'pantalla vieja: oferta anterior aceptada');
 await reset();await p.evaluate(()=>{location.hash='#'+'b'.repeat(64)});await p.waitForTimeout(600);await p.evaluate(()=>{location.hash='#'+'a'.repeat(64)});await p.waitForTimeout(800);
 ok((await txt(p)).includes('Aceptar plaza')&&(await txt(p)).includes('Yoga'),'cambio de # con la pantalla abierta: muestra la oferta nueva y sus botones');
 await b.close();console.log(fails?'RESULT: FAIL ('+fails+')':'RESULT: PASS');process.exit(fails?1:0);
})();
