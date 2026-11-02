// La tablet nunca debe caducar ni pedir "recarga la página".
// Servidor local: up-tablet.sh (portales reales /alta/ y /alta/admin/, inactividad 3 s, dispositivo 6 s).
const BASE='http://127.0.0.1:8098';let fails=0;const ok=(c,m)=>{if(!c){fails++;console.log('FAIL',m);}else console.log('ok  ',m);};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function client(prefix){
  const jar={};let csrf='';let lastSetCookie=[];
  const req=async(action,data,get=false)=>{
    const url=BASE+prefix+(get?'api.php?action='+action:'api.php');
    const res=await fetch(url,{method:get?'GET':'POST',headers:{Cookie:Object.entries(jar).map(([k,v])=>k+'='+v).join('; '),...(get?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf})},body:get?undefined:JSON.stringify({action,...data})});
    lastSetCookie=res.headers.getSetCookie();for(const c of lastSetCookie){const [kv]=c.split(';');const i=kv.indexOf('=');jar[kv.slice(0,i)]=kv.slice(i+1);}
    const j=await res.json().catch(()=>({ok:false,error:'no json '+res.status}));if(j.data?.csrf)csrf=j.data.csrf;return j;
  };
  return {req,cookies:()=>lastSetCookie};
}
(async()=>{
  const admin=client('/alta/admin/');await admin.req('bootstrap',{},true);
  ok((await admin.req('login',{username:'e2e.admin',password:process.env.TF_E2E_PASSWORD})).ok,'login del equipo');
  const inv=await admin.req('tablet_invitation',{});const code=inv.data?.code;ok(!!code,'código de activación');
  const tab=client('/alta/');await tab.req('bootstrap',{},true);
  ok((await tab.req('tablet_activate',{code})).ok,'tablet activada');
  ok(tab.cookies().some(c=>/expires=/i.test(c)),'A: la cookie de la tablet sobrevive a cerrar el navegador');
  // B: tras la inactividad, el siguiente toque funciona sin recargar
  await sleep(4200);
  const d=await tab.req('draft_new',{});ok(d.ok,'B: empezar alta tras inactividad sin "recarga la página" ('+(d.error||'ok')+')');
  // D: el latido no cuenta como actividad: el borrador abandonado se limpia igual
  let expiredSeen=false;for(let i=0;i<5;i++){await sleep(1000);const p=await tab.req('ping',{},true);if(p.data?.expired)expiredSeen=true;}
  ok(expiredSeen,'D: el latido avisa de que el borrador caducó por inactividad');
  const b=await tab.req('bootstrap',{},true);ok(b.data?.mode==='kiosk'&&!b.data?.draft,'D: sigue en recepción y sin el borrador abandonado');
  // C: con el latido, el dispositivo no caduca nunca (6 s configurados, esperamos 10 s)
  for(let i=0;i<5;i++){await sleep(2000);await tab.req('ping',{},true);}
  const c=await tab.req('bootstrap',{},true);ok(c.data?.mode==='kiosk','C: la tablet sigue activada pasado su plazo ('+c.data?.mode+')');
  console.log(fails?'RESULT: FAIL':'RESULT: PASS');process.exit(fails?1:0);
})().catch(e=>{console.log('ERROR',e.message);process.exit(1);});
