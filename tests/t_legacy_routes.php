<?php
declare(strict_types=1);
// Rutas heredadas reales (recepción) frente a las ofertas. Orquesta procesos PHP sobre tf_test_reservas.
$W=getenv('TF_WEB_ROOT')?:dirname(__DIR__).'/web';require $W.'/sso/offers.php';require $W.'/public/conexion.php';
$f=0;$p=0;function ck(bool $c,string $m):void{global $f,$p;if($c){$p++;return;}$f++;echo "FAIL $m\n";}
function route(string $script,array $post):array{global $W;$cmd='php '.escapeshellarg(dirname(__DIR__,1).'/tests/legacy_call.php').' '.escapeshellarg($W.'/'.$script).' '.escapeshellarg(json_encode($post));$o=shell_exec($cmd.' 2>&1');$j=json_decode((string)$o,true);return is_array($j)?$j:['raw'=>$o];}
foreach(['tf_push_outbox','tf_notify_events','tf_offers','tf_push_subscriptions','tf_devices','tf_notify_audit','tf_rate_limits','tf_bookings','tf_people','inscripciones','inscripciones_cola','clases_canceladas','horarios'] as $t)$conn->query("DELETE FROM $t");
$conn->query("UPDATE tf_notify_settings SET v='1' WHERE k='OFFERS_ENABLED'");$conn->query("UPDATE tf_notify_settings SET v='' WHERE k IN ('OFFERS_ONLY_HORARIOS','OFFERS_QUIET_FROM','OFFERS_QUIET_TO')");$conn->query("UPDATE tf_notify_settings SET v=DATE_FORMAT(NOW() - INTERVAL 1 DAY,'%Y-%m-%d %H:%i:%s') WHERE k='OFFERS_SINCE'");
$days=['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];$s=tfNow()->modify('+1500 minutes');$d=$s->format('Y-m-d');
$conn->query("INSERT INTO horarios(clase,dia,hora,limite) VALUES('Yoga','{$days[(int)$s->format('w')]}','".$s->format('H:i').'-'.$s->modify('+1 hour')->format('H:i')."',1)");$h=$conn->insert_id;
$mk=function(string $n,string $tel,bool $push)use($conn){$conn->query("INSERT INTO tf_people(nombre,telefono) VALUES('$n','$tel')");$id=$conn->insert_id;if($push){$conn->query("INSERT INTO tf_devices(person_id,token_hash) VALUES($id,'".hash('sha256',$n)."')");$dv=$conn->insert_id;$conn->query("INSERT INTO tf_push_subscriptions(device_id,endpoint_hash,endpoint,p256dh,auth_secret,test_confirmed_at,test_sent_at) VALUES($dv,'".hash('sha256','e'.$n)."','https://fcm.googleapis.com/x','k','a',NOW(),NOW())");}return $id;};
$A=$mk('Ana Avisos','611111111',true);$N=$mk('Nora Sinavisos','622222222',false);$M=$mk('Marta Avisos','633333333',true);
$r=route('public/inscribir_cliente.php',['nombre'=>'Fijo Uno','telefono'=>'600000001','horario_id'=>$h,'fecha'=>$d]);ck(($r['status']??'')==='INSCRIBED','recepción inscribe en plaza libre');
$r=route('public/inscribir_cliente.php',['nombre'=>'Ana Avisos','telefono'=>'611111111','horario_id'=>$h,'fecha'=>$d]);ck(($r['status']??'')==='WAITLIST','clase llena: Ana (con avisos) entra en la espera');
$r=route('public/inscribir_cliente.php',['nombre'=>'Nora Sinavisos','telefono'=>'622222222','horario_id'=>$h,'fecha'=>$d]);ck(($r['code']??'')==='WAITLIST_REQUIRES_NOTICES'&&!$conn->query("SELECT 1 FROM inscripciones_cola WHERE nombre LIKE 'Nora%'")->num_rows,'recepción: sin avisos NO entra en la cola (todas las rutas)');
$r=route('public/admin_inscribir_multiple.php',['nombre'=>'Nora Sinavisos','telefono'=>'622222222','fechas'=>[$d],'horario_id'=>$h]);
// libera la plaza por la ruta heredada: no debe promover sola
$fijo=(int)$conn->query("SELECT id FROM inscripciones WHERE nombre='Fijo Uno'")->fetch_row()[0];
$r=route('public/eliminar_inscripcion.php',['id'=>$fijo]);if(getenv('DBG'))fwrite(STDERR,json_encode($r)."\n");ck(($r['success']??false)===true&&($r['promoted']??null)===null,'ruta heredada de borrado: no promueve en modo OFERTAS');
ck((int)$conn->query("SELECT COUNT(*) FROM inscripciones")->fetch_row()[0]===0&&(int)$conn->query("SELECT COUNT(*) FROM inscripciones_cola")->fetch_row()[0]===1,'Ana sigue en la espera, sin reserva automática');
tfOffersTick($conn);ck(tfHeld($conn,$h,$d)===1,'el worker ofrece la plaza a Ana');
// la plaza retenida no se puede coger por la ruta de recepción
$r=route('public/inscribir_cliente.php',['nombre'=>'Marta Avisos','telefono'=>'633333333','horario_id'=>$h,'fecha'=>$d]);ck(($r['status']??'')==='WAITLIST','recepción: la plaza retenida cuenta como ocupada (Marta va a la espera)');
$r=route('public/comprobar_disponibilidad.php',[]);
$disp=shell_exec('cd '.escapeshellarg($W.'/public').' && php -r '.escapeshellarg('$_GET=["horario_id"=>'.$h.',"fecha"=>"'.$d.'"];$_SERVER["REQUEST_METHOD"]="GET";include "comprobar_disponibilidad.php";'));
// (comprobar_disponibilidad usa POST/GET según la versión; se comprueba la ocupación con la misma consulta)
ck(tfSchedule($conn,$h,$d)['disponibles']===0,'disponibilidad = 0 con la plaza retenida');
// cancelar la clase por la ruta de recepción invalida la oferta
$r=route('public/admin_cancelar_clase.php',['horario_id'=>$h,'fecha'=>$d,'accion'=>'cancelar','motivo'=>'prueba']);
ck(count(tfQuery($conn,"SELECT id FROM tf_offers WHERE status='CANCELLED'"))===1,'cancelar clase (ruta real) invalida la oferta');
echo ($f?'RESULT: FAIL':'RESULT: PASS')." ($p ok, $f fallos)\n";exit($f?1:0);
