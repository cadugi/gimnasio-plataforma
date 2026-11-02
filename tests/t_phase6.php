<?php
declare(strict_types=1);
// Fase 6: avisos de recepción, clase cancelada, cambio de horario y datos para la pantalla de recepción. Rutas reales sobre tf_test_reservas.
$W=getenv('TF_WEB_ROOT')?:dirname(__DIR__).'/web';require $W.'/sso/offers.php';require $W.'/public/conexion.php';
$f=0;$p=0;function ck(bool $c,string $m):void{global $f,$p;if($c){$p++;return;}$f++;echo "FAIL $m\n";}
function route(string $script,array $post,string $method='POST'):array{global $W;$o=shell_exec('php '.escapeshellarg(dirname(__DIR__).'/tests/legacy_call.php').' '.escapeshellarg($W.'/'.$script).' '.escapeshellarg(json_encode($post)).' '.$method.' 2>&1');$j=json_decode((string)$o,true);return is_array($j)?$j:['raw'=>$o];}
foreach(['tf_push_outbox','tf_notify_events','tf_offers','tf_push_subscriptions','tf_devices','tf_notify_audit','tf_rate_limits','tf_bookings','tf_people','inscripciones','inscripciones_cola','clases_canceladas','horarios'] as $t)$conn->query("DELETE FROM $t");
$days=['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];$s=tfNow()->modify('+1500 minutes');$d=$s->format('Y-m-d');$dia=$days[(int)$s->format('w')];$hora=$s->format('H:i').'-'.$s->modify('+1 hour')->format('H:i');
$conn->query("INSERT INTO horarios(clase,dia,hora,limite) VALUES('Yoga','$dia','$hora',5)");$h=$conn->insert_id;
$mk=function(string $n,string $tel,bool $push)use($conn){$conn->query("INSERT INTO tf_people(nombre,telefono) VALUES('$n','$tel')");$id=$conn->insert_id;if($push){$conn->query("INSERT INTO tf_devices(person_id,token_hash) VALUES($id,'".hash('sha256',$n)."')");$dv=$conn->insert_id;$conn->query("INSERT INTO tf_push_subscriptions(device_id,endpoint_hash,endpoint,p256dh,auth_secret,test_confirmed_at,test_sent_at) VALUES($dv,'".hash('sha256','e'.$n)."','https://fcm.googleapis.com/x','k','a',NOW(),NOW())");}return $id;};
$madre=$mk('Madre Lopez','666000999',true);$hijo=$mk('Hijo Lopez','666000999',false);$solo=$mk('Sin Movil','677000111',false);
$ev=fn(string $k)=>tfQuery($conn,'SELECT person_id,kind FROM tf_notify_events WHERE kind=? ORDER BY id',[$k]);
// ---- reserva en recepción ----
$r=route('public/inscribir_cliente.php',['nombre'=>'Madre Lopez','telefono'=>'666000999','horario_id'=>$h,'fecha'=>$d]);
ck(($r['status']??'')==='INSCRIBED'&&$r['avisos']===true,'recepción: reserva y se avisa al móvil de la persona');
ck(count($ev('RECEPTION_BOOKING'))===1&&(int)$ev('RECEPTION_BOOKING')[0]['person_id']===$madre,'el aviso va a Madre');
$r=route('public/inscribir_cliente.php',['nombre'=>'Hijo Lopez','telefono'=>'666000999','horario_id'=>$h,'fecha'=>$d]);
ck(($r['status']??'')==='INSCRIBED'&&$r['avisos']===false,'mismo teléfono, otra persona sin móvil: reserva igualmente, «sin avisos»');
ck(count($ev('RECEPTION_BOOKING'))===1,'la reserva del hijo NO llega al móvil de la madre (teléfono compartido)');
$r=route('public/inscribir_cliente.php',['nombre'=>'Sin Movil','telefono'=>'677000111','horario_id'=>$h,'fecha'=>$d]);ck(($r['status']??'')==='INSCRIBED'&&$r['avisos']===false,'persona sin ningún móvil: se puede reservar y se indica que no recibirá avisos');
$r=route('public/inscribir_cliente.php',['nombre'=>'Madre Lopez','telefono'=>'666000999','horario_id'=>$h,'fecha'=>$d]);ck(count($ev('RECEPTION_BOOKING'))===1,'repetir la misma reserva no duplica el aviso');
$m=route('public/admin_inscribir_multiple.php',['nombre'=>'Madre Lopez','telefono'=>'666000999','horario_id'=>$h,'fechas'=>json_encode([$d])]);
// ---- cambio de horario: solo reservas futuras, una vez ----
$conn->query("INSERT INTO inscripciones(nombre,telefono,horario_id,fecha) VALUES('Madre Lopez','666000999',$h,'".tfNow()->modify('-10 days')->format('Y-m-d')."')");   // reserva pasada
$nuevaHora=$s->modify('+1 hour')->format('H:i').'-'.$s->modify('+2 hours')->format('H:i');
$r=route('public/editar_horario.php',['id'=>$h,'clase'=>'Yoga','dia'=>$dia,'hora'=>$nuevaHora,'limite'=>5]);ck(($r['success']??false)===true,'editar horario (ruta real)');
$sc=$ev('SCHEDULE_CHANGED');ck(count($sc)===1&&(int)$sc[0]['person_id']===$madre,'cambio de hora: aviso a quien tiene reserva futura con móvil (no a la reserva pasada)');
$r=route('public/editar_horario.php',['id'=>$h,'clase'=>'Yoga','dia'=>$dia,'hora'=>$nuevaHora,'limite'=>8]);ck(count($ev('SCHEDULE_CHANGED'))===1,'cambiar solo el aforo no genera avisos de horario');
$r=route('public/editar_horario.php',['id'=>$h,'clase'=>'Yoga','dia'=>$dia,'hora'=>$hora,'limite'=>8]);ck(count($ev('SCHEDULE_CHANGED'))===2,'un nuevo cambio de hora vuelve a avisar');
// ---- clase cancelada ----
$conn->query("DELETE FROM tf_push_outbox");$conn->query("DELETE FROM tf_notify_events");
$conn->query("INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha) VALUES('Sin Movil','677000111',$h,'$d')");
$r=route('public/admin_cancelar_clase.php',['horario_id'=>$h,'fecha'=>$d,'accion'=>'cancelar','motivo'=>'prueba']);
ck(count($ev('CLASS_CANCELLED'))===1&&(int)$ev('CLASS_CANCELLED')[0]['person_id']===$madre,'cancelar clase: aviso a quien tenía reserva y móvil; la espera no recibe este aviso');
$r=route('public/admin_cancelar_clase.php',['horario_id'=>$h,'fecha'=>$d,'accion'=>'cancelar','motivo'=>'otra vez']);ck(count($ev('CLASS_CANCELLED'))===1,'cancelar dos veces no duplica el aviso');
// ---- pantalla de recepción ----
$conn->query("INSERT INTO tf_notify_audit(actor,action,person_id,detail_json) VALUES('sender','PUSH_FAILED',$madre,'{\"kind\":\"OFFER\",\"reason\":\"HTTP_410\"}')");
$conn->query("UPDATE tf_notify_settings SET v='1' WHERE k='HB_OFFERS'");
$g=route('public/admin_movil.php',[],'GET');
ck(($g['success']??false)===true&&array_key_exists('envio',$g['salud'])&&array_key_exists('worker_ofertas_seg',$g['salud'])&&is_array($g['devices'])&&is_array($g['ofertas'])&&is_array($g['incidencias']),'API de recepción: salud, móviles, ofertas e incidencias');
ck(count($g['devices'])===1&&str_starts_with($g['devices'][0]['telefono'],'***'),'los teléfonos salen enmascarados');
ck(count($g['incidencias'])>=1&&!str_contains(json_encode($g),'666000999'),'incidencias visibles y sin teléfonos completos');
// ---- confirmar oferta a petición (recepción) y revocar ----
$conn->query("DELETE FROM inscripciones_cola");$conn->query("DELETE FROM clases_canceladas");$conn->query("DELETE FROM inscripciones");$conn->query("UPDATE horarios SET limite=1 WHERE id=$h");$conn->query("UPDATE tf_notify_settings SET v='1' WHERE k='OFFERS_ENABLED'");$conn->query("UPDATE tf_notify_settings SET v='' WHERE k IN ('OFFERS_ONLY_HORARIOS','OFFERS_QUIET_FROM','OFFERS_QUIET_TO')");$conn->query("UPDATE tf_notify_settings SET v=DATE_FORMAT(NOW() - INTERVAL 1 DAY,'%Y-%m-%d %H:%i:%s') WHERE k='OFFERS_SINCE'");
$conn->query("INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha) VALUES('Sin Movil','677000111',$h,'$d')");$w=$conn->insert_id;$conn->query("INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,wait_id) VALUES($solo,$h,'$d','WAITLIST',$w)");
tfOffersTick($conn);$g=route('public/admin_movil.php',[],'GET');ck(count($g['ofertas'])===1&&(int)$g['ofertas'][0]['avisos']===0,'ofertas pendientes visibles, marcando la que no tiene avisos');
$o=tfOfferAcceptByStaff($conn,(int)$g['ofertas'][0]['id'],'recepcion');ck($o['ok']&&(int)$conn->query('SELECT COUNT(*) FROM inscripciones')->fetch_row()[0]===1,'recepción confirma la oferta a petición de la persona');
tfAtomic($conn,fn()=>tfDeviceRevoke($conn,(int)$conn->query('SELECT id FROM tf_devices LIMIT 1')->fetch_row()[0],'recepcion'));$g=route('public/admin_movil.php',[],'GET');ck(count($g['devices'])===0,'revocar quita el móvil de la lista');
echo ($f?'RESULT: FAIL':'RESULT: PASS')." ($p ok, $f fallos)\n";exit($f?1:0);
