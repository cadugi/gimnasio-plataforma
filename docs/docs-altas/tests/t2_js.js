// Extrae la función prorate() de app.js y la compara con los valores del servidor.
const fs=require('fs');const src=fs.readFileSync('/home/ubuntu/work/bajas-src/public/assets/app.js','utf8');
const m=src.match(/function prorate\([\s\S]*?\n\}/);if(!m){console.log('FAIL: prorate() no existe');process.exit(1);}
const prorate=eval('('+m[0]+')');let f=0;const eq=(g,w,msg)=>{if(JSON.stringify(g)!==JSON.stringify(w)){f++;console.log('FAIL',msg,g,w);}};
eq(prorate(3990,'18-10-2026').cents,1802,'18-oct');eq(prorate(3990,'01-10-2026').cents,3990,'día 1');eq(prorate(3990,'10-02-2027').cents,2708,'febrero');
eq(prorate(3990,'18-10-2026').from,'18-10-2026','desde');eq(prorate(3990,'18-10-2026').to,'31-10-2026','hasta');
console.log(f?'RESULT: FAIL':'RESULT: PASS');process.exit(f?1:0);
