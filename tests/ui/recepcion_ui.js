// Pantalla de recepción con Chromium real y servidor simulado. Uso: node tests/ui/recepcion_ui.js [carpeta_capturas]
const {chromium}=require('/home/ubuntu/.npm/_npx/381cec31605a419a/node_modules/playwright-core');
const BASE='http://127.0.0.1:8765';const OUT=process.argv[2]||'/tmp';let fails=0;const ok=(c,m)=>{if(!c){fails++;console.log('FAIL',m);}else console.log('ok  ',m);};
(async()=>{const b=await chromium.launch({executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args:['--no-sandbox']});
 const p=await (await b.newContext({viewport:{width:1100,height:900}})).newPage();const errs=[];p.on('pageerror',e=>errs.push(e.message));
 await p.goto(BASE+'/reservas/avisos-recepcion.html');await p.waitForTimeout(700);const t=await p.evaluate(()=>document.body.innerText);
 ok(t.includes('Envío de avisos: activado')&&t.includes('Remitente: hace 3 s'),'muestra el estado del envío y del remitente');
 ok(t.includes('Control de ofertas: hace 3 min'),'avisa de que el control de ofertas lleva minutos sin dar señal');
 ok(t.includes('Luis Gómez (***222)')&&t.includes('NO tiene avisos'),'oferta pendiente con aviso de que no tiene avisos');
 ok(t.includes('Ana Pérez (***678)')&&t.includes('iPhone'),'móvil asociado con teléfono enmascarado');
 ok(t.includes('Llámale: si la quiere, confírmala arriba'),'incidencia explicada en lenguaje sencillo');
 ok(!/token|VAPID|PWA/i.test(t),'sin términos técnicos');
 await p.getByRole('button',{name:'Confirmar plaza'}).click();ok(await p.getByRole('button',{name:/Pulsa otra vez/}).first().isVisible(),'confirmar pide una segunda pulsación');
 await p.screenshot({path:OUT+'/12-recepcion.png',fullPage:true});
 await p.getByRole('button',{name:/Pulsa otra vez: la persona/}).click();await p.waitForTimeout(500);ok((await p.evaluate(()=>document.body.innerText)).includes('Plaza confirmada para Luis Gómez'),'confirmar muestra mensaje que no desaparece');
 ok(errs.length===0,'sin errores de JavaScript '+errs.join(';'));await b.close();console.log(fails?'RESULT: FAIL ('+fails+')':'RESULT: PASS');process.exit(fails?1:0);})();
