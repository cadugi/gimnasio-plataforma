// Pruebas de interfaz del asistente de avisos con navegador real (Chromium) y servidor simulado (tests/ui/mock_server.py).
// Simulan iPhone/Android: NO sustituyen la prueba en móviles reales. Uso: node tests/ui/avisos_ui.js [carpeta_capturas]
const {chromium}=require('/home/ubuntu/.npm/_npx/381cec31605a419a/node_modules/playwright-core');
const BASE='http://127.0.0.1:8765';const OUT=process.argv[2]||'/tmp';let fails=0;
const ok=(c,m)=>{if(!c){fails++;console.log('FAIL',m);}else console.log('ok  ',m);};
const UA={android:'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36',
 ios:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
 iosOld:'Mozilla/5.0 (iPhone; CPU iPhone OS 15_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Mobile/15E148 Safari/604.1'};
const stub=(perm,standalone)=>`(()=>{let p='${perm}';window.__req=0;
 Object.defineProperty(window,'Notification',{value:{get permission(){return p},requestPermission:async()=>{window.__req++;p=window.__grant||'granted';return p}},configurable:true});
 window.PushManager=function(){};
 const sub={endpoint:'https://fcm.googleapis.com/fcm/send/test',getKey:n=>new Uint8Array(n==='auth'?16:65).fill(7).buffer,unsubscribe:async()=>true};
 const reg={pushManager:{getSubscription:async()=>null,subscribe:async()=>sub}};
 Object.defineProperty(navigator,'serviceWorker',{value:{register:async()=>reg,ready:Promise.resolve(reg),getRegistration:async()=>reg},configurable:true});
 ${standalone?"Object.defineProperty(navigator,'standalone',{value:true});":''}
 const mm=window.matchMedia.bind(window);window.matchMedia=q=>${standalone?"q.includes('standalone')?{matches:true,addListener(){},addEventListener(){}}:mm(q)":'mm(q)'};})();`;
async function page(b,{ua,perm='default',standalone=false,w=360,h=740,url='/reservas/avisos.html',grant}){
 const ctx=await b.newContext({viewport:{width:w,height:h},userAgent:ua,isMobile:true,hasTouch:true});
 const p=await ctx.newPage();p.errs=[];p.on('pageerror',e=>p.errs.push(e.message));
 await p.addInitScript(stub(perm,standalone)+(grant?`window.__grant='${grant}';`:''));
 await fetch(BASE+'/x',{method:'DELETE'});await p.goto(BASE+url);await p.waitForTimeout(600);return p;}
const txt=p=>p.evaluate(()=>document.body.innerText);
async function ident(p){await p.fill('#nombre','Ana Pérez');await p.fill('#telefono','612345678');await p.click('#b-ident');await p.waitForTimeout(700);}
async function audit(p,name){ // tamaños mínimos y desbordamiento
 const r=await p.evaluate(()=>{const bad=[];const vis=e=>{const s=getComputedStyle(e),b=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&b.width>0&&b.height>0};
  document.querySelectorAll('body *').forEach(e=>{if(!vis(e))return;const s=getComputedStyle(e);
   if([...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())&&parseFloat(s.fontSize)<18&&!e.closest('svg'))bad.push('texto '+s.fontSize+': '+e.textContent.trim().slice(0,30));
   if(/^(BUTTON|A|INPUT)$/.test(e.tagName)&&e.type!=='checkbox'&&e.getBoundingClientRect().height<48)bad.push('objetivo '+Math.round(e.getBoundingClientRect().height)+'px: '+(e.textContent||e.id).trim().slice(0,30));});
  return {bad,over:document.documentElement.scrollWidth>document.documentElement.clientWidth};});
 ok(r.bad.length===0,name+': texto ≥18 px y botones ≥48 px '+r.bad.join(' | '));ok(!r.over,name+': sin desplazamiento horizontal');}
(async()=>{
 const b=await chromium.launch({executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args:['--no-sandbox']});
 // ---------- Android ----------
 let p=await page(b,{ua:UA.android});
 ok(await p.locator('#s-ident').isVisible(),'Android: pide nombre y teléfono');
 await audit(p,'Android identificación');await p.screenshot({path:OUT+'/01-identificar.png'});
 await p.fill('#nombre','Ana Pérez');await p.fill('#telefono','12');await p.click('#b-ident');await p.waitForTimeout(400);
 ok(await p.locator('#err').isVisible(),'Android: dato incorrecto → error visible');await p.waitForTimeout(6000);
 ok(await p.locator('#err').isVisible(),'Android: el error NO desaparece solo');
 await p.fill('#telefono','612 345 678');await p.click('#b-ident');await p.waitForTimeout(700);
 ok(await p.locator('#s-wiz').isVisible()&&(await txt(p)).includes('Hola, Ana Pérez'),'Android: entra al asistente');
 ok(await p.locator('#b1 img').count()===3,'Android: tutorial con 3 imágenes (sin beforeinstallprompt)');
 ok(!/PWA|token|VAPID|suscripci/i.test(await txt(p)),'Android: sin términos técnicos');
 ok((await p.locator('#chip').textContent())==='Activar avisos','Android: estado «Activar avisos»');
 await audit(p,'Android paso 1');await p.screenshot({path:OUT+'/02-android-paso1.png',fullPage:true});
 await p.evaluate(()=>{const e=new Event('beforeinstallprompt');e.prompt=()=>{window.__prompted=1};e.userChoice=Promise.resolve({outcome:'accepted'});window.dispatchEvent(e)});await p.waitForTimeout(200);
 ok(await p.getByRole('button',{name:'Añadir Top Fitness al móvil'}).isVisible(),'Android: con beforeinstallprompt aparece el botón de instalar');
 await p.getByRole('button',{name:'Añadir Top Fitness al móvil'}).click();await p.waitForTimeout(400);
 ok(await p.evaluate(()=>window.__prompted===1),'Android: el botón lanza la instalación del navegador');
 ok(await p.evaluate(()=>window.__req===0),'Android: aún no se ha pedido ningún permiso');
 await p.getByRole('button',{name:'Activar avisos'}).click();await p.waitForTimeout(700);
 ok(await p.evaluate(()=>window.__req===1),'Android: el permiso se pide solo al pulsar «Activar avisos»');
 ok((await p.locator('#chip').textContent())==='Revisar avisos','Android: activados pero sin probar → «Revisar avisos»');
 await p.getByRole('button',{name:'Enviar aviso de prueba'}).click();await p.waitForTimeout(3600);
 ok(await p.getByRole('button',{name:'Sí, lo he recibido'}).isVisible(),'Android: tras la prueba pregunta si la recibió');
 await p.screenshot({path:OUT+'/03-android-prueba.png',fullPage:true});
 await p.getByRole('button',{name:'No lo he recibido'}).click();await p.waitForTimeout(300);
 ok(await p.locator('#err').isVisible(),'Android: «No lo he recibido» explica qué revisar');
 await p.getByRole('button',{name:'Sí, lo he recibido'}).click();await p.waitForTimeout(500);
 ok((await p.locator('#chip').textContent())==='Avisos activados','Android: «Avisos activados» tras confirmar');
 ok(await p.locator('#mis').isVisible(),'Android: muestra «Mis últimos avisos»');
 ok(p.errs.length===0,'Android: sin errores de JavaScript '+p.errs.join(';'));
 await p.screenshot({path:OUT+'/04-android-listo.png',fullPage:true});
 ok(await p.getByText('No soy yo').count()===0,'ya no hay «No soy yo»: cada usuario es único (nombre + teléfono)');
 await p.getByRole('button',{name:'Cerrar sesión'}).click();await p.waitForTimeout(400);
 ok(await p.locator('#s-ident').isVisible(),'Cerrar sesión vuelve a pedir los datos');
 // ---------- iPhone en Safari ----------
 p=await page(b,{ua:UA.ios});await ident(p);
 ok(await p.locator('#b1 img').count()===4,'iPhone Safari: tutorial con 4 imágenes');
 ok((await txt(p)).includes('Añadir a pantalla de inicio')&&(await txt(p)).includes('desde el icono'),'iPhone: Compartir → Añadir a pantalla de inicio → abrir desde el icono');
 ok(await p.getByRole('button',{name:'Activar avisos'}).count()===0&&(await txt(p)).includes('solo funcionan desde el icono'),'iPhone en Safari: no ofrece activar; explica que hay que abrir desde el icono');
 ok(await p.getByRole('button',{name:/Ya lo he hecho/}).count()===0,'iPhone: no se puede saltar la instalación');
 await audit(p,'iPhone paso 1');await p.screenshot({path:OUT+'/05-iphone-paso1.png',fullPage:true});
 p=await page(b,{ua:UA.iosOld});await ident(p);
 ok((await txt(p)).includes('16.4'),'iPhone iOS 15: pide actualizar a iOS 16.4');
 // ---------- iPhone desde el icono ----------
 p=await page(b,{ua:UA.ios,standalone:true});await ident(p);
 ok(await p.getByRole('button',{name:'Activar avisos'}).isVisible(),'iPhone desde el icono: ofrece «Activar avisos»');
 // ---------- permiso rechazado ----------
 p=await page(b,{ua:UA.android,grant:'denied'});await ident(p);
 await p.getByRole('button',{name:/Ya lo he hecho/}).click();await p.waitForTimeout(200);await p.getByRole('button',{name:'Activar avisos'}).click();await p.waitForTimeout(500);
 ok((await txt(p)).includes('bloqueados')&&(await txt(p)).includes('candado'),'Rechazado: explica cómo recuperarlos');
 ok(await p.getByRole('button',{name:'Activar avisos'}).count()===0,'Rechazado: no vuelve a ofrecer la petición');
 await p.reload();await p.waitForTimeout(600);ok(await p.evaluate(()=>window.__req===0),'Rechazado: al recargar no se pide otra vez');
 await p.screenshot({path:OUT+'/06-rechazado.png',fullPage:true});
 // ---------- navegador sin push ----------
 const ctx=await b.newContext({viewport:{width:360,height:740},userAgent:UA.android,isMobile:true});p=await ctx.newPage();await fetch(BASE+'/x',{method:'DELETE'});
 await p.addInitScript(`delete window.PushManager;`);await p.goto(BASE+'/reservas/avisos.html');await ident(p);
 await p.getByRole('button',{name:/Ya lo he hecho/}).click();await p.waitForTimeout(200);ok((await txt(p)).includes('no puede recibir avisos'),'Navegador incompatible: mensaje claro, sin botones muertos');
 // ---------- pantalla compartida ----------
 p=await page(b,{ua:UA.android,url:'/reservas/avisos.html?modo=compartido'});
 ok(await p.locator('#compartida').isVisible()&&!(await p.locator('#s-ident').isVisible()),'Pantalla compartida: aviso y sin formulario');
 ok(await p.evaluate(()=>localStorage.getItem('tf_recordar')===null),'Pantalla compartida: no guarda datos');
 // ---------- 320 px y letra grande ----------
 p=await page(b,{ua:UA.android,w:320,h:640});await ident(p);await audit(p,'320 px');
 await p.addStyleTag({content:'html{font-size:200%}body{font-size:38px}'});await p.waitForTimeout(300);
 ok(!(await p.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+2)),'Letra ampliada al 200%: sin desplazamiento horizontal');
 await p.screenshot({path:OUT+'/07-letra-grande.png'});
 await b.close();console.log(fails?'RESULT: FAIL ('+fails+')':'RESULT: PASS');process.exit(fails?1:0);
})();
