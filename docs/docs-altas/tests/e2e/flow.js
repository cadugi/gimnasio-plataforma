// Recorrido real: mantenimiento desde la tablet (socio en papel) y aceptación + vuelta en el panel.
const {chromium}=require('/home/ubuntu/.npm/_npx/381cec31605a419a/node_modules/playwright-core');
const OUT='/tmp/claude-1000/-home-ubuntu/f295b7ac-87b7-4d6f-9112-20c6a042c263/scratchpad/e2e';require('fs').mkdirSync(OUT,{recursive:true});
(async()=>{
 const b=await chromium.launch({executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args:['--no-sandbox']});
 const p=await b.newPage({viewport:{width:820,height:1180}});const errs=[];p.on('pageerror',e=>errs.push(e.message));p.on('console',m=>{if(m.type()==='error')errs.push(m.text());});
 const shot=async n=>{await p.waitForTimeout(400);await p.screenshot({path:OUT+'/'+n+'.png',fullPage:true});console.log('shot',n);};
 const click=async sel=>{await p.click(sel);await p.waitForTimeout(500);};
 const toastText=async()=>(await p.locator('.toast').allInnerTexts().catch(()=>[])).join(' | ');
 await p.goto('http://127.0.0.1:8099/');await p.waitForTimeout(800);
 if(await p.locator('[data-action=login_screen]').count())await click('[data-action=login_screen]');
 await p.fill('#username','e2e.admin');await p.fill('#password',process.env.TF_E2E_PASSWORD);await click('[data-action=login]');
 await click('[data-action=kiosk]');const tablet=async()=>{await p.evaluate(()=>{document.querySelectorAll('link[href*="admin.css"]').forEach(l=>l.remove());document.body.classList.add('portal-client');if(!document.querySelector('link[href*="client.css"]')){const l=document.createElement('link');l.rel='stylesheet';l.href='assets/client.css';document.head.appendChild(l);}});await p.waitForTimeout(300);};await tablet();await shot('01-inicio');
 await click('#start-withdrawal');await tablet();await shot('02-tipo');
 await click('[data-kind=MAINTENANCE]');await click('[data-action=w_kind_next]');
 await p.selectOption('#w-doc-type','DNI');await p.fill('#w-doc','87654321X');await p.fill('#w-birth','1970-02-02');await shot('03-identificacion');
 await click('[data-action=w_identify]');await tablet();await shot('04-datos-papel');
 await p.fill('#w-name','Pepe');await p.fill('#w-surname','De Papel');await p.fill('#w-phone','611222333');await p.fill('#w-email','pepe@example.com');await p.fill('#w-number','5120');await p.selectOption('#w-reason','injury');
 await click('[data-action=w_details]');await p.waitForTimeout(800);await tablet();await shot('05-revision');
 await p.locator('#signature').scrollIntoViewIfNeeded();const c=await p.locator('#signature').boundingBox();await p.mouse.move(c.x+30,c.y+60);await p.mouse.down();for(let i=1;i<=12;i++)await p.mouse.move(c.x+30+i*25,c.y+60+(i%2?-30:30));await p.mouse.up();
 await p.check('#confirm_signature');await p.waitForTimeout(200);console.log('boton firmar habilitado:',await p.isEnabled('#sign-contract'));
 await click('#sign-contract');await p.waitForTimeout(800);await tablet();await shot('06-final');
 await click('[data-action=w_finish]');await shot('07-inicio-de-nuevo');
 // Panel
 await p.goto('http://127.0.0.1:8099/');await p.waitForTimeout(800);
 if(await p.locator('[data-action=login_screen]').count())await click('[data-action=login_screen]');
 await p.fill('#username','e2e.admin');await p.fill('#password',process.env.TF_E2E_PASSWORD);await click('[data-action=login]');await p.waitForTimeout(600);await shot('08-resumen');
 await click('[data-page=withdrawals]');await p.waitForTimeout(600);await shot('09-bajas');
 await click('[data-action=wa_detail]');await p.waitForTimeout(600);await shot('10-detalle');
 await p.check('#wa-done');await click('[data-action=wa_accept]');console.log('toast:',await toastText());
 await click('[data-filter=MAINTENANCE]');await click('[data-action=wa_detail]');await p.waitForTimeout(600);
 await p.fill('#wa-date','2027-02-10');await p.dispatchEvent('#wa-date','change');await p.waitForTimeout(300);await shot('11-vuelta');
 console.log('presupuesto:',await p.locator('#wa-quote').innerText());
 console.log('ERRORES JS:',errs.length?errs:'ninguno');await b.close();
})().catch(e=>{console.error('FALLO',e.message);process.exit(1);});
