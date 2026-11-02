const {chromium}=require('/home/ubuntu/.npm/_npx/381cec31605a419a/node_modules/playwright-core');
const BASE='http://127.0.0.1:8098';let fails=0;const ok=(c,m)=>{if(!c){fails++;console.log('FAIL',m);}else console.log('ok  ',m);};
(async()=>{
 const b=await chromium.launch({executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args:['--no-sandbox']});
 const ctx=await b.newContext({viewport:{width:820,height:1180}});const p=await ctx.newPage();const errs=[];p.on('pageerror',e=>errs.push(e.message));
 // código de activación desde el panel
 const a=await ctx.newPage();await a.goto(BASE+'/alta/admin/');await a.waitForTimeout(800);
 const code=await a.evaluate(async()=>{const T=window.TF;await T.api('login',{username:'e2e.admin',password:process.env.TF_E2E_PASSWORD});const r=await T.api('tablet_invitation',{});return r.code;});await a.close();
 await p.goto(BASE+'/alta/');await p.waitForTimeout(800);
 await p.evaluate(async c=>{await window.TF.api('tablet_activate',{code:c});await window.TF.boot();},code);await p.waitForTimeout(500);
 ok(await p.locator('#start-enrollment').count()===1,'tablet en la pantalla de inicio');
 const toast=async()=>p.evaluate(()=>{const t=document.getElementById('toast');return t&&t.style.display==='block'?t.textContent:'';});
 // 1) tras la inactividad (3 s), tocar "Empezar el alta" funciona
 await p.waitForTimeout(4000);await p.click('#start-enrollment');await p.waitForTimeout(800);
 ok(await p.locator('#enrollment-form').count()===1,'1: empieza el alta tras la inactividad ('+(await toast())+')');
 await p.click('[data-action=cancel]');await p.waitForTimeout(300);await p.click('[data-action=cancel_confirm]');await p.waitForTimeout(500);
 // 2) token roto (como tras un reinicio): se recupera solo
 await p.evaluate(()=>{window.TF.S.boot.csrf='roto';});await p.click('#start-withdrawal');await p.waitForTimeout(300);await p.click('[data-kind=PERMANENT]');await p.click('[data-action=w_kind_next]');await p.waitForTimeout(800);
 ok(await p.locator('#w-doc').count()===1,'2: con el token roto sigue funcionando ('+(await toast())+')');
 // 3) baja a medias abandonada: el latido la cierra y vuelve al inicio
 await p.waitForTimeout(4000);await p.evaluate(()=>window.dispatchEvent(new Event('x')));await p.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await p.waitForTimeout(1500);
 ok(await p.locator('#start-enrollment').count()===1,'3: baja abandonada → vuelve al inicio sola');
 // 4) cerrar y abrir el navegador (cookie persistente)
 const state=await ctx.storageState();const ctx2=await b.newContext({storageState:state});const p2=await ctx2.newPage();await p2.goto(BASE+'/alta/');await p2.waitForTimeout(1000);
 ok(await p2.locator('#start-enrollment').count()===1,'4: al reabrir el navegador sigue activada');
 ok(errs.length===0,'sin errores JS '+errs.join(' | '));
 console.log(fails?'RESULT: FAIL':'RESULT: PASS');await b.close();process.exit(fails?1:0);
})().catch(e=>{console.log('ERROR',e.message);process.exit(1);});
