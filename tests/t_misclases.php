<?php
declare(strict_types=1);
// «Mis clases» contra tf_test_reservas (nunca producción).
$W=getenv('TF_WEB_ROOT')?:dirname(__DIR__).'/web';require $W.'/sso/offers.php';require $W.'/public/conexion.php';
$f=0;$p=0;function ck(bool $c,string $m):void{global $f,$p;if($c){$p++;return;}$f++;echo "FAIL $m\n";}
if(!str_contains(getenv('TF_REAL_DB_NAME')?:'','test'))exit(2);
foreach(['tf_push_outbox','tf_notify_events','tf_offers','tf_push_subscriptions','tf_devices','tf_notify_audit','tf_bookings','tf_people','inscripciones','inscripciones_cola','clases_canceladas','horarios'] as $t)$conn->query("DELETE FROM $t");
$conn->query("UPDATE tf_notify_settings SET v='' WHERE k IN ('OFFERS_ONLY_HORARIOS','PUSH_ALLOW_PERSONS')");
$d1=tfNow()->modify('+1 day')->format('Y-m-d');$d2=tfNow()->modify('+2 days')->format('Y-m-d');$old=tfNow()->modify('-3 days')->format('Y-m-d');
$conn->query("INSERT INTO horarios(clase,dia,hora,limite) VALUES('Yoga','lunes','18:00-19:00',2),('Pilates','martes','10:00-11:00',5),('Core','jueves','09:00-10:00',5)");$y=$conn->insert_id;$pi=$y+1;$co=$y+2;
$conn->query("INSERT INTO tf_people(nombre,telefono) VALUES('Ana Pérez','612345678'),('Hijo Pérez','612345678')");$ana=['nombre'=>'Ana Pérez','telefono'=>'612345678'];
$ins=fn($n,$t,$h,$d,$c='NOW()')=>$conn->query("INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES('$n','$t',$h,'$d',$c)");
$ins('ana PEREZ','+34 612 345 678',$y,$d1);               // hecha en recepción con otra forma de escribir
$ins('Ana Pérez','612345678',$pi,$d2);
$ins('Ana Pérez','612345678',$co,$old);                   // pasada
$ins('Hijo Pérez','612345678',$y,$d1);                    // mismo teléfono, otra persona
$ins('Otro Nombre','699999999',$y,$d1);
$conn->query("INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha,creado_en) VALUES('Primero Esp','611111111',$y,'$d2',NOW() - INTERVAL 5 MINUTE),('Ana Pérez','612345678',$y,'$d2',NOW() - INTERVAL 2 MINUTE),('Tercero Esp','633333333',$y,'$d2',NOW())");
$w=(int)$conn->query("SELECT id FROM inscripciones_cola WHERE nombre='Ana Pérez'")->fetch_row()[0];
$r=tfMyClasses($conn,$ana);
ck(count($r['reservas'])===2,'dos reservas futuras (incluida la hecha en recepción con otro formato de nombre)');
ck($r['reservas'][0]['clase']==='Yoga'&&$r['reservas'][1]['clase']==='Pilates','ordenadas por fecha');
ck(!array_filter($r['reservas'],fn($x)=>$x['clase']==='Core'),'las clases pasadas no salen');
ck(count($r['espera'])===1&&$r['espera'][0]['posicion']===2&&$r['espera'][0]['total']===3,'posición en la cola: 2 de 3');
$j=json_encode($r);ck(!str_contains($j,'612345678')&&!str_contains($j,'Hijo')&&!str_contains($j,'Otro')&&!str_contains($j,'Primero'),'sin teléfonos ni datos de otras personas');
$h=tfMyClasses($conn,['nombre'=>'Hijo Pérez','telefono'=>'612345678']);ck(count($h['reservas'])===1&&count($h['espera'])===0,'teléfono compartido: cada persona ve solo lo suyo');
$conn->query("INSERT INTO clases_canceladas(horario_id,fecha) VALUES($pi,'$d2')");$r=tfMyClasses($conn,$ana);ck($r['reservas'][1]['cancelada']===true,'clase cancelada marcada');
$conn->query("UPDATE tf_notify_settings SET v='1' WHERE k='OFFERS_ENABLED'");$conn->query("INSERT INTO tf_offers(wait_id,person_id,horario_id,fecha,token_hash,expires_at) VALUES($w,1,$y,'$d2','".str_repeat('a',64)."',NOW() + INTERVAL 10 MINUTE)");$oid=$conn->insert_id;$conn->query("INSERT INTO tf_notify_events(kind,person_id,offer_id,horario_id,fecha,dedupe_key,not_before,ttl_at) VALUES('OFFER',1,$oid,$y,'$d2','OFFER:$oid',NOW() - INTERVAL 1 MINUTE,NOW() + INTERVAL 10 MINUTE)");
$r=tfMyClasses($conn,$ana);ck(preg_match('/^\d\d:\d\d$/',(string)$r['espera'][0]['oferta_hasta'])===1,'oferta pendiente con hora límite');
$conn->query("UPDATE tf_notify_settings SET v='0' WHERE k='OFFERS_ENABLED'");
$x=tfMyClasses($conn,['nombre'=>'Desconocido','telefono'=>'600000000']);ck(!$x['reservas']&&!$x['espera'],'persona sin clases: listas vacías');
echo ($f?'RESULT: FAIL':'RESULT: PASS')." ($p ok, $f fallos)\n";exit($f?1:0);
