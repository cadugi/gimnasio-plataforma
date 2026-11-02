<?php
declare(strict_types=1);
// Suscripciones, prueba, alta de eventos y recordatorios contra tf_test_reservas.
$root=getenv('TF_WEB_ROOT')?:dirname(__DIR__).'/web';require $root.'/sso/avisos.php';require $root.'/public/conexion.php';
$f=0;$p=0;function ck(bool $c,string $m):void{global $f,$p;if($c){$p++;return;}$f++;echo "FAIL $m\n";}
function boom(callable $fn,string $code,string $m):void{try{$fn();}catch(WebError $e){ck($e->getMessage()===$code,$m.' ('.$e->getMessage().')');return;}ck(false,$m.' sin error');}
if(!str_contains(getenv('TF_REAL_DB_NAME')?:'','test')){fwrite(STDERR,"¡No es la BD de pruebas!\n");exit(2);}
foreach(['tf_push_outbox','tf_notify_events','tf_push_subscriptions','tf_devices','tf_notify_audit','tf_rate_limits','tf_bookings','tf_people','inscripciones','clases_canceladas','horarios'] as $t)$conn->query("DELETE FROM $t");
$_SERVER['REMOTE_ADDR']='203.0.113.9';
function person(mysqli $c,string $n,string $t):array{$c->query("INSERT INTO tf_people(nombre,telefono) VALUES('$n','$t')");$id=$c->insert_id;$c->query("INSERT INTO tf_devices(person_id,token_hash) VALUES($id,'".hash('sha256',$n.$t)."')");$d=$c->insert_id;return ['id'=>$d,'person_id'=>$id,'nombre'=>$n];}
function sub(string $host='fcm.googleapis.com'):array{return ['endpoint'=>"https://$host/fcm/send/abc123",'keys'=>['p256dh'=>str_repeat('B',87),'auth'=>str_repeat('a',22)]];}

// validación de destinos
foreach(['https://fcm.googleapis.com/x','https://updates.push.services.mozilla.com/wpush/v2/x','https://web.push.apple.com/x','https://wns2.notify.windows.com/x'] as $u)ck(tfPushEndpointOk($u),"permitido $u");
foreach(['http://fcm.googleapis.com/x','https://127.0.0.1/x','https://localhost/x','https://169.254.169.254/x','https://fcm.googleapis.com:8443/x','https://fcm.googleapis.com@evil.test/x','https://evil.test/?fcm.googleapis.com','https://fcm.googleapis.com.evil.test/x','https://[::1]/x'] as $u)ck(!tfPushEndpointOk($u),"bloqueado $u");

$ana=person($conn,'Ana Pérez','612345678');
ck(tfAvisosStatus($conn,$ana)['state']==='NONE','sin avisos al inicio');
boom(fn()=>tfSubscribe($conn,$ana,['endpoint'=>'https://evil.test/x','keys'=>sub()['keys']]),'INVALID_SUBSCRIPTION','destino ajeno');
boom(fn()=>tfSubscribe($conn,$ana,['endpoint'=>sub()['endpoint'],'keys'=>['p256dh'=>'x','auth'=>'y']]),'INVALID_SUBSCRIPTION','claves inválidas');
boom(fn()=>tfRequestTest($conn,$ana),'PUSH_NOT_ACTIVE','probar sin suscripción');
$st=tfSubscribe($conn,$ana,sub());ck($st['state']==='REVIEW'&&$st['subscribed']&&!$st['test_confirmed'],'suscrito pero sin probar = Revisar avisos');
ck(!tfPersonHasConfirmedPush($conn,$ana['person_id']),'cola exige prueba confirmada');
boom(fn()=>tfConfirmTest($conn,$ana),'TEST_NOT_SENT','no se puede confirmar sin envío');
tfRequestTest($conn,$ana);
ck((int)tfQuery($conn,"SELECT COUNT(*) n FROM tf_notify_events WHERE kind='TEST'")[0]['n']===1&&(int)tfQuery($conn,'SELECT COUNT(*) n FROM tf_push_outbox')[0]['n']===1,'prueba crea evento + envío');
boom(fn()=>tfConfirmTest($conn,$ana),'TEST_NOT_SENT','aún no enviado por el servicio push');
$conn->query('UPDATE tf_push_subscriptions SET test_sent_at=NOW()');      // lo hace el remitente
$st=tfConfirmTest($conn,$ana);ck($st['state']==='ACTIVATED'&&$st['test_confirmed'],'Avisos activados tras confirmar');
ck(tfPersonHasConfirmedPush($conn,$ana['person_id']),'persona apta para la cola');
// el mismo navegador pasa a otro móvil/persona: exige probar de nuevo
$luis=person($conn,'Luis Gómez','622111222');tfSubscribe($conn,$luis,sub());
ck(tfAvisosStatus($conn,$luis)['state']==='REVIEW'&&!tfPersonHasConfirmedPush($conn,$ana['person_id']),'suscripción reasignada: la anterior persona pierde los avisos');
ck((int)tfQuery($conn,'SELECT COUNT(*) n FROM tf_push_subscriptions')[0]['n']===1,'un endpoint = una fila');
tfSubscribe($conn,$ana,sub('updates.push.services.mozilla.com'));
// emisión + dedupe
$conn->query('DELETE FROM tf_push_outbox');$conn->query('DELETE FROM tf_notify_events');
$id=tfAtomic($conn,fn()=>tfNotifyEmit($conn,'CLASS_CANCELLED',$ana['person_id'],'CC:1',3600));ck($id>0,'evento creado');
ck(tfAtomic($conn,fn()=>tfNotifyEmit($conn,'CLASS_CANCELLED',$ana['person_id'],'CC:1',3600))===0,'dedupe');
ck((int)tfQuery($conn,'SELECT COUNT(*) n FROM tf_push_outbox')[0]['n']===1,'un envío por suscripción activa');
tfAtomic($conn,fn()=>tfDeviceRevoke($conn,$ana['id'],'recepcion'));
ck(tfAtomic($conn,fn()=>tfNotifyEmit($conn,'CLASS_CANCELLED',$ana['person_id'],'CC:2',3600))>0&&(int)tfQuery($conn,"SELECT COUNT(*) n FROM tf_push_outbox o JOIN tf_notify_events e ON e.id=o.event_id WHERE e.dedupe_key='CC:2'")[0]['n']===0,'dispositivo revocado: sin envíos');
// rollback: el evento forma parte de la transacción de negocio
try{tfAtomic($conn,function()use($conn,$luis){tfNotifyEmit($conn,'CLASS_CANCELLED',$luis['person_id'],'CC:3',3600);throw new RuntimeException('x');});}catch(RuntimeException){}
ck((int)tfQuery($conn,"SELECT COUNT(*) n FROM tf_notify_events WHERE dedupe_key='CC:3'")[0]['n']===0,'si falla la operación no queda evento');

// recordatorios
$conn->query('DELETE FROM tf_push_outbox');$conn->query('DELETE FROM tf_notify_events');
$sara=person($conn,'Sara Gil','655111222');tfSubscribe($conn,$sara,sub('web.push.apple.com'));
$madre=person($conn,'Madre Ruiz','666000999');tfSubscribe($conn,$madre,sub('fcm.googleapis.com'));
$conn->query("UPDATE tf_push_subscriptions SET endpoint_hash=MD5(CONCAT(endpoint,id))");
$now=tfNow();$days=['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
function clase(mysqli $c,DateTimeImmutable $start,string $dia):int{$c->query("INSERT INTO horarios(clase,dia,hora,limite) VALUES('Yoga','$dia','".$start->format('H:i').'-'.$start->modify('+1 hour')->format('H:i')."',10)");return $c->insert_id;}
$start=$now->modify('+2 hours 5 minutes');$h=clase($conn,$start,$days[(int)$start->format('w')]);
$ins=function(string $n,string $t,int $h,string $d,string $creado)use($conn){$conn->query("INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES('$n','$t',$h,'$d','$creado')");return $conn->insert_id;};
$fecha=$start->format('Y-m-d');$old=$now->modify('-1 day')->format('Y-m-d H:i:s');
$r1=$ins('SARA gil','+34 655 111 222',$h,$fecha,$old);                      // coincide
$r2=$ins('Sara Gil','655999888',$h,$fecha,$old);                            // otro teléfono: nadie
$r3=$ins('Pepe Otro','655111222',$h,$fecha,$old);                           // mismo teléfono, otra persona
$r4=$ins('Sara Gil','655111222',$h,$fecha,$now->format('Y-m-d H:i:s'));     // otra reserva idéntica pero tardía (misma sesión: se prueba abajo con otra clase)
ck(tfPlanReminders($conn)===2,'programa recordatorio a Sara (dos reservas idénticas en la misma clase)');
$ev=tfQuery($conn,"SELECT kind,person_id,not_before,ttl_at,booking_id FROM tf_notify_events WHERE kind='REMINDER' ORDER BY booking_id");
ck(count($ev)===2&&(int)$ev[0]['person_id']===$sara['person_id'],'solo a la ficha correcta');
ck($ev[0]['not_before']===$start->setTime((int)$start->format('H'),(int)$start->format('i'),0)->modify('-2 hours')->format('Y-m-d H:i:s'),'not_before = inicio - 2 h');
ck(tfPlanReminders($conn)===0,'idempotente');
// reserva tardía: sin recordatorio
$conn->query('DELETE FROM inscripciones');$conn->query('DELETE FROM tf_push_outbox');$conn->query('DELETE FROM tf_notify_events');
$start2=$now->modify('+90 minutes');$h2=clase($conn,$start2,$days[(int)$start2->format('w')]);
$ins('Sara Gil','655111222',$h2,$start2->format('Y-m-d'),$now->modify('-30 minutes')->format('Y-m-d H:i:s'));
ck(tfPlanReminders($conn)===0,'clase en <2 h: no se crea recordatorio atrasado');
// clase cancelada / lejana
$conn->query('DELETE FROM inscripciones');$start3=$now->modify('+3 hours');$h3=clase($conn,$start3,$days[(int)$start3->format('w')]);
$ins('Sara Gil','655111222',$h3,$start3->format('Y-m-d'),$old);$conn->query("INSERT INTO clases_canceladas(horario_id,fecha) VALUES($h3,'".$start3->format('Y-m-d')."')");
ck(tfPlanReminders($conn)===0,'clase cancelada: sin recordatorio');
// tras cambiar la hora el recordatorio programado ya no coincide (lo detecta el remitente)
echo ($f?'RESULT: FAIL':'RESULT: PASS')." ($p ok, $f fallos)\n";exit($f?1:0);
