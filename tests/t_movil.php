<?php
declare(strict_types=1);
// Pruebas de identificación y dispositivos contra la BD aislada tf_test_reservas (nunca producción).
$root=getenv('TF_WEB_ROOT')?:dirname(__DIR__).'/web';require $root.'/sso/notify.php';
require $root.'/public/conexion.php';
$f=0;$p=0;
function ck(bool $c,string $m):void{global $f,$p;if($c){$p++;return;}$f++;echo "FAIL $m\n";}
function boom(callable $fn,string $code,string $m):void{try{$fn();}catch(WebError $e){ck($e->getMessage()===$code,$m.' ('.$e->getMessage().')');return;}ck(false,$m.' sin error');}
if(!str_contains(getenv('TF_REAL_DB_NAME')?:'','test')){fwrite(STDERR,"¡No es la BD de pruebas!\n");exit(2);}
foreach(['tf_push_outbox','tf_notify_events','tf_push_subscriptions','tf_devices','tf_notify_audit','tf_rate_limits','tf_bookings','tf_people'] as $t)$conn->query("DELETE FROM $t");
$_SERVER['REMOTE_ADDR']='203.0.113.9';
$db=[ 'Ana Pérez'=>['612345678','ref-ana'],'Luis Gómez'=>['622111222','ref-luis'],'Marta Díaz'=>['633444555','MANY'] ];
$GLOBALS['tf_altas_stub']=function($n,$ph)use($db){foreach($db as $k=>[$tel,$ref])if(tfNormName($k)===$n&&$tel===$ph)return $ref==='MANY'?['result'=>'MANY']:['result'=>'ONE','ref'=>$ref];return ['result'=>'NONE'];};

// normalización
ck(tfNormPhone('+34 612-345 678')==='612345678','prefijo +34');ck(tfNormPhone('0034612345678')==='612345678','0034');ck(tfNormPhone('512345678')==='','no empieza por 6-9');ck(tfNormPhone('61234')==='','corto');
ck(tfNormName('  ÁNA   pérez ')==='ana perez','nombre normalizado');

// identificación correcta, no duplica persona
$r=tfIdentify($conn,'ana PEREZ','612 345 678');ck($r['status']==='OK','identifica');
$r2=tfIdentify($conn,'Ana Pérez','+34612345678');ck($r2['person']===$r['person'],'misma persona = misma fila');
// incorrectos / ambiguos: misma respuesta
$g1=tfIdentify($conn,'Ana Perez','612345679');ck($g1['status']==='OK'&&$g1['person']!==$r['person'],'teléfono distinto: queda sin ficha, nunca como la socia');
ck(tfQuery($conn,'SELECT external_reference r FROM tf_people WHERE id=?',[(string)$g1['person']])[0]['r']===null?false:str_starts_with(tfQuery($conn,'SELECT external_reference r FROM tf_people WHERE id=?',[(string)$g1['person']])[0]['r'],'GUEST:'),'referencia GUEST');
ck(tfIdentify($conn,'ANA perez','612345679')['person']===$g1['person'],'sin ficha: misma persona al repetir');
$mm=tfIdentify($conn,'Marta Díaz','633444555');ck($mm['status']==='OK'&&str_starts_with(tfQuery($conn,'SELECT external_reference r FROM tf_people WHERE id=?',[(string)$mm['person']])[0]['r'],'GUEST:'),'ambigua: sin ficha, no se elige a nadie');
ck((int)tfQuery($conn,"SELECT COUNT(*) n FROM tf_notify_audit WHERE action='IDENTIFY_REVIEW'")[0]['n']===1,'ambigua deja aviso a recepción');
ck(strpos(json_encode(tfQuery($conn,'SELECT detail_json FROM tf_notify_audit')),'633444555')===false,'la auditoría no guarda el teléfono completo');
boom(fn()=>tfIdentify($conn,'Ana Pérez','123'),'INVALID_DATA','formato inválido');
// fuente caída ≠ no socio
$GLOBALS['tf_altas_stub']=fn()=>throw new WebError('SOURCE_UNAVAILABLE',503);
$dn=tfIdentify($conn,'Ana Pérez','612345678');ck($dn['person']===$r['person']?false:true,'Altas caída: no se asocia a la ficha por suposición');
ck((int)tfQuery($conn,"SELECT COUNT(*) n FROM tf_notify_audit WHERE action='IDENTIFY_SOURCE_DOWN'")[0]['n']===1,'Altas caída queda registrado');
$GLOBALS['tf_altas_stub']=function($n,$ph)use($db){return ['result'=>'NONE'];};
// Innux asociado expresamente por recepción
$pid=tfAtomic($conn,fn()=>tfPersonForRef($conn,'INNUX:77','Pedro Ruiz','655000111'));
ck(tfIdentify($conn,'pedro ruiz','655000111')===['status'=>'OK','person'=>$pid],'socio Innux asociado');
ck(tfIdentify($conn,'Pedro Ruiz','655000112')['person']!==$pid,'Innux: teléfono distinto = otra persona');
// teléfono compartido: fichas separadas
$GLOBALS['tf_altas_stub']=fn($n,$ph)=>['result'=>'ONE','ref'=>$n==='madre lopez'?'ref-m':'ref-h'];
$m=tfIdentify($conn,'Madre Lopez','666000999');$h=tfIdentify($conn,'Hijo Lopez','666000999');
ck($m['person']!==$h['person'],'mismo teléfono, personas distintas no se fusionan');
// límite de intentos
$_SERVER['REMOTE_ADDR']='198.51.100.1';$GLOBALS['tf_altas_stub']=fn()=>['result'=>'NONE'];
$hit=false;for($i=0;$i<14;$i++){try{tfIdentify($conn,'Nadie Nada','6000000'.str_pad((string)$i,2,'0',STR_PAD_LEFT));}catch(WebError $e){$hit=$e->status===429;}}ck($hit,'límite por IP');
$_SERVER['REMOTE_ADDR']='198.51.100.2';$hit=false;for($i=0;$i<9;$i++){try{tfIdentify($conn,'Nadie Nada','600000001');}catch(WebError $e){$hit=$e->status===429;}}ck($hit,'límite por teléfono');

// dispositivos
$secret=tfDeviceCreate($conn,$r['person'],'ios');$_COOKIE[TF_DEVICE_COOKIE]=$secret;
$d=tfDeviceCurrent($conn);ck($d&&(int)$d['person_id']===$r['person'],'cookie válida');
ck(tfQuery($conn,'SELECT token_hash FROM tf_devices')[0]['token_hash']!==$secret,'solo se guarda el hash');
ck(tfDeviceCsrf()!==''&&tfDeviceCsrf()!==hash_hmac('sha256','topfitness-reservas-csrf',$secret),'CSRF propio de este móvil');
putenv('TF_PUBLIC_ORIGIN=https://x.test');$_SERVER['HTTP_ORIGIN']='https://x.test';$_SERVER['HTTP_X_TOPFITNESS_REQUEST']='1';
boom(fn()=>tfDeviceCheckWrite(true),'CSRF_REQUIRED','sin token CSRF');
$_SERVER['HTTP_X_CSRF_TOKEN']=tfDeviceCsrf();tfDeviceCheckWrite(true);ck(true,'con token CSRF');
$_SERVER['HTTP_ORIGIN']='https://evil.test';boom(fn()=>tfDeviceCheckWrite(true),'REQUEST_NOT_ALLOWED','origen ajeno');
$_SERVER['HTTP_ORIGIN']='https://x.test';unset($_SERVER['HTTP_X_TOPFITNESS_REQUEST']);boom(fn()=>tfDeviceCheckWrite(false),'REQUEST_NOT_ALLOWED','sin cabecera propia');
// suscripción cae al revocar
$conn->query("INSERT INTO tf_push_subscriptions(device_id,endpoint_hash,endpoint,p256dh,auth_secret) VALUES({$d['id']},'".str_repeat('e',64)."','https://push.example/x','k','a')");
tfAtomic($conn,fn()=>tfDeviceRevoke($conn,(int)$d['id'],'recepcion'));
ck(tfDeviceCurrent($conn)===null,'dispositivo revocado no autoriza');
ck(tfQuery($conn,'SELECT status FROM tf_push_subscriptions')[0]['status']==='REVOKED','revocar retira avisos');
// el token de móvil no vale como sesión de reservas ni administrativa
ck(!isset($_SERVER['REMOTE_USER']),'sin REMOTE_USER');
ck(tfSession($conn)===null,'la cookie de móvil no abre sesión de reservas/pagos');
echo ($f?'RESULT: FAIL':'RESULT: PASS')." ($p ok, $f fallos)\n";exit($f?1:0);
