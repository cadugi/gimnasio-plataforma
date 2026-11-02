<?php
declare(strict_types=1);
// Cancelar reserva / salir de la espera desde «Mis clases» contra tf_test_reservas (nunca producción).
$W=getenv('TF_WEB_ROOT')?:dirname(__DIR__).'/web';require $W.'/sso/offers.php';require $W.'/public/conexion.php';
$f=0;$p=0;function ck(bool $c,string $m):void{global $f,$p;if($c){$p++;return;}$f++;echo "FAIL $m\n";}
function code(callable $fn):string{try{$r=$fn();return $r['ok']?'OK:'.$r['estado']:'NO:'.($r['code']??'');}catch(WebError $e){return 'ERR:'.$e->getMessage();}}
if(!str_contains(getenv('TF_REAL_DB_NAME')?:'','test'))exit(2);
$_COOKIE[TF_DEVICE_COOKIE]=str_repeat('a',64);
function reset_db():void{global $conn;foreach(['tf_push_outbox','tf_notify_events','tf_offers','tf_push_subscriptions','tf_devices','tf_notify_audit','tf_bookings','tf_people','inscripciones','inscripciones_cola','clases_canceladas','horarios'] as $t)$conn->query("DELETE FROM $t");$conn->query("UPDATE tf_notify_settings SET v='0' WHERE k IN ('OFFERS_ENABLED','PUSH_SEND_ENABLED')");$conn->query("UPDATE tf_notify_settings SET v='' WHERE k IN ('OFFERS_ONLY_HORARIOS','PUSH_ALLOW_PERSONS','OFFERS_SINCE','OFFERS_QUIET_FROM','OFFERS_QUIET_TO')");}
function clase(int $lim,int $min=1500):array{global $conn;$d=['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];$s=tfNow()->modify(($min>=0?"+":"").$min." minutes");$s=$s->setTime((int)$s->format('H'),(int)$s->format('i'),0);
 $conn->query("INSERT INTO horarios(clase,dia,hora,limite) VALUES('Yoga','{$d[(int)$s->format('w')]}','".$s->format('H:i').'-'.$s->modify('+1 hour')->format('H:i')."',$lim)");return ['id'=>$conn->insert_id,'fecha'=>$s->format('Y-m-d')];}
function persona(string $n,string $t):array{global $conn;$conn->query("INSERT INTO tf_people(nombre,telefono) VALUES('$n','$t')");return ['id'=>$conn->insert_id,'nombre'=>$n,'telefono'=>$t];}
function ins(array $c,string $n,string $t):int{global $conn;$conn->query("INSERT INTO inscripciones(nombre,telefono,horario_id,fecha) VALUES('$n','$t',{$c['id']},'{$c['fecha']}')");return $conn->insert_id;}
function esp(array $c,string $n,string $t,int $ago):int{global $conn;$conn->query("INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha,creado_en) VALUES('$n','$t',{$c['id']},'{$c['fecha']}',NOW() - INTERVAL $ago MINUTE)");return $conn->insert_id;}
function n(string $sql):int{global $conn;return (int)$conn->query($sql)->fetch_row()[0];}

reset_db();$c=clase(1);$ana=persona('Ana Pérez','612345678');$otra=persona('Otra Persona','699999999');
$mia=ins($c,'ana PEREZ','+34 612 345 678');$e1=esp($c,'Primero Esp','611111111',10);$e2=esp($c,'Segundo Esp','622222222',5);
$mc=tfMyClasses($conn,$ana);ck(count($mc['reservas'])===1&&$mc['reservas'][0]['puede']===true&&preg_match('/^\d+\.[a-f0-9]{24}$/',$mc['reservas'][0]['ref'])===1,'Mis clases ofrece referencia y permiso de cancelar');
$ref=$mc['reservas'][0]['ref'];
ck(code(fn()=>tfClientCancel($conn,$ana,'r',$ref.'0'))==='ERR:ACCESS_DENIED','referencia manipulada: denegada');
ck(code(fn()=>tfClientCancel($conn,$ana,'w',$ref))==='ERR:ACCESS_DENIED','referencia de reserva usada como espera: denegada');
$_COOKIE[TF_DEVICE_COOKIE]=str_repeat('b',64);ck(code(fn()=>tfClientCancel($conn,$ana,'r',$ref))==='ERR:ACCESS_DENIED','referencia de otro móvil: denegada');$_COOKIE[TF_DEVICE_COOKIE]=str_repeat('a',64);
ck(code(fn()=>tfClientCancel($conn,$otra,'r',$ref))==='ERR:ACCESS_DENIED'&&n("SELECT COUNT(*) FROM inscripciones WHERE id=$mia")===1,'otra persona con la referencia: denegada y la reserva sigue');
ck(code(fn()=>tfClientCancel($conn,$ana,'r',$ref))==='OK:CANCELADA','el dueño cancela su reserva');
ck(n("SELECT COUNT(*) FROM inscripciones WHERE nombre='Primero Esp'")===1&&n("SELECT COUNT(*) FROM inscripciones WHERE horario_id={$c['id']}")===1&&n("SELECT COUNT(*) FROM inscripciones_cola WHERE horario_id={$c['id']}")===1,'modo heredado: la plaza liberada pasa a la primera de la espera, y solo a una');
ck(code(fn()=>tfClientCancel($conn,$ana,'r',$ref))==='OK:YA_CANCELADA','repetir (doble pulsación) es idempotente y no promueve a nadie más');ck(n("SELECT COUNT(*) FROM inscripciones WHERE horario_id={$c['id']}")===1,'sigue habiendo exactamente 1 reserva');
ck(n("SELECT COUNT(*) FROM tf_notify_audit WHERE action='CLIENT_CANCELLED'")===1,'auditoría de la cancelación');

// clase empezada
reset_db();$c=clase(2,-30);$ana=persona('Ana Pérez','612345678');$mia=ins($c,'Ana Pérez','612345678');$r=tfClientRef('r',$mia);
ck(code(fn()=>tfClientCancel($conn,$ana,'r',$r))==='NO:CLASS_STARTED'&&n("SELECT COUNT(*) FROM inscripciones")===1,'clase ya empezada: no se cancela');
ck(tfMyClasses($conn,$ana)['reservas'][0]['puede']===false,'clase empezada: sin botón');
// clase cancelada por el gimnasio: sin botón
reset_db();$c=clase(2);$ana=persona('Ana Pérez','612345678');ins($c,'Ana Pérez','612345678');$conn->query("INSERT INTO clases_canceladas(horario_id,fecha) VALUES({$c['id']},'{$c['fecha']}')");
ck(tfMyClasses($conn,$ana)['reservas'][0]['puede']===false,'clase cancelada por el gimnasio: sin botón');

// modo OFERTAS: la plaza liberada se ofrece (no se promueve directa)
reset_db();$conn->query("UPDATE tf_notify_settings SET v='1' WHERE k='OFFERS_ENABLED'");$conn->query("UPDATE tf_notify_settings SET v=DATE_FORMAT(NOW() - INTERVAL 1 DAY,'%Y-%m-%d %H:%i:%s') WHERE k='OFFERS_SINCE'");
$c=clase(1);$ana=persona('Ana Pérez','612345678');$b=persona('Beto B','622222222');$mia=ins($c,'Ana Pérez','612345678');$wb=esp($c,'Beto B','622222222',5);$conn->query("INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,wait_id) VALUES({$b['id']},{$c['id']},'{$c['fecha']}','WAITLIST',$wb)");
ck(code(fn()=>tfClientCancel($conn,$ana,'r',tfClientRef('r',$mia)))==='OK:CANCELADA','modo ofertas: cancela');
ck(n("SELECT COUNT(*) FROM inscripciones")===0&&n("SELECT COUNT(*) FROM tf_offers WHERE status='PENDING' AND person_id={$b['id']}")===1,'modo ofertas: la plaza se ofrece a Beto (retenida), no se le apunta sola');
// salir de la espera con oferta pendiente → se rechaza y pasa a la siguiente
$c2=$c;$g=persona('Gus G','633333333');$wg=esp($c,'Gus G','633333333',1);$conn->query("INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,wait_id) VALUES({$g['id']},{$c['id']},'{$c['fecha']}','WAITLIST',$wg)");
ck(code(fn()=>tfClientCancel($conn,$b,'w',tfClientRef('w',$wb)))==='OK:FUERA_DE_LA_ESPERA','Beto sale de la espera teniendo una oferta pendiente');
ck(n("SELECT COUNT(*) FROM inscripciones_cola WHERE id=$wb")===0&&n("SELECT COUNT(*) FROM tf_offers WHERE person_id={$b['id']} AND status='DECLINED'")===1&&n("SELECT COUNT(*) FROM tf_offers WHERE person_id={$g['id']} AND status='PENDING'")===1,'su oferta queda rechazada y la plaza pasa a Gus');
ck(n("SELECT COUNT(*) FROM tf_bookings WHERE person_id={$b['id']} AND estado='CANCELLED'")===1,'tf_bookings sincronizado');
// salir de una espera normal; no se puede salir de la de otra persona
reset_db();$c=clase(1);$ana=persona('Ana Pérez','612345678');$otra=persona('Otra P','699999999');ins($c,'Fijo','600000001');$w=esp($c,'Ana Pérez','612345678',3);
ck(code(fn()=>tfClientCancel($conn,$otra,'w',tfClientRef('w',$w)))==='ERR:ACCESS_DENIED'&&n("SELECT COUNT(*) FROM inscripciones_cola")===1,'no se puede sacar a otra persona de la espera');
ck(code(fn()=>tfClientCancel($conn,$ana,'w',tfClientRef('w',$w)))==='OK:FUERA_DE_LA_ESPERA'&&n("SELECT COUNT(*) FROM inscripciones_cola")===0,'sale de la espera');
echo ($f?'RESULT: FAIL':'RESULT: PASS')." ($p ok, $f fallos)\n";exit($f?1:0);
