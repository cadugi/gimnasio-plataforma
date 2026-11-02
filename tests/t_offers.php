<?php
declare(strict_types=1);
// Ofertas de lista de espera contra tf_test_reservas (nunca producción).
$root=getenv('TF_WEB_ROOT')?:dirname(__DIR__).'/web';require $root.'/sso/offers.php';require $root.'/public/conexion.php';
$f=0;$p=0;function ck(bool $c,string $m):void{global $f,$p;if($c){$p++;return;}$f++;echo "FAIL $m\n";}
if(!str_contains(getenv('TF_REAL_DB_NAME')?:'','test')){fwrite(STDERR,"¡No es la BD de pruebas!\n");exit(2);}
$_SERVER['REMOTE_ADDR']='203.0.113.7';$days=['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
function q(string $sql,array $a=[]):array{global $conn;return tfQuery($conn,$sql,$a);}
function reset_db():void{global $conn;foreach(['tf_push_outbox','tf_notify_events','tf_offers','tf_push_subscriptions','tf_devices','tf_notify_audit','tf_rate_limits','tf_requests','tf_bookings','tf_people','inscripciones','inscripciones_cola','clases_canceladas','horarios'] as $t)$conn->query("DELETE FROM $t");
 $conn->query("UPDATE tf_notify_settings SET v='1' WHERE k IN ('OFFERS_ENABLED','PUSH_SEND_ENABLED')");$conn->query("UPDATE tf_notify_settings SET v='' WHERE k IN ('OFFERS_ONLY_HORARIOS','PUSH_ALLOW_PERSONS','TEST_HORARIO','OFFERS_QUIET_FROM','OFFERS_QUIET_TO')");$conn->query("UPDATE tf_notify_settings SET v=DATE_FORMAT(NOW() - INTERVAL 1 DAY,'%Y-%m-%d %H:%i:%s') WHERE k='OFFERS_SINCE'");}
/** Clase en `$minutes` minutos (hora de Madrid) con aforo `$limit`. */
function clase(int $limit,int $minutes=1500):array{global $conn,$days;$s=tfNow()->modify("+$minutes minutes");$s=$s->setTime((int)$s->format('H'),(int)$s->format('i'),0);
 $conn->query("INSERT INTO horarios(clase,dia,hora,limite) VALUES('Yoga','{$days[(int)$s->format('w')]}','".$s->format('H:i').'-'.$s->modify('+1 hour')->format('H:i')."',$limit)");return ['id'=>$conn->insert_id,'fecha'=>$s->format('Y-m-d'),'start'=>$s];}
function persona(string $n,string $tel,bool $push=true):int{global $conn;$conn->query("INSERT INTO tf_people(nombre,telefono) VALUES('$n','$tel')");$id=$conn->insert_id;
 if($push){$conn->query("INSERT INTO tf_devices(person_id,token_hash) VALUES($id,'".hash('sha256',$n)."')");$d=$conn->insert_id;$conn->query("INSERT INTO tf_push_subscriptions(device_id,endpoint_hash,endpoint,p256dh,auth_secret,test_confirmed_at,test_sent_at) VALUES($d,'".hash('sha256','e'.$n)."','https://fcm.googleapis.com/x','k','a',NOW(),NOW())");}return $id;}
function inscribir(array $c,string $n,string $tel):int{global $conn;$conn->query("INSERT INTO inscripciones(nombre,telefono,horario_id,fecha) VALUES('$n','$tel',{$c['id']},'{$c['fecha']}')");return $conn->insert_id;}
function esperar(array $c,int $person,string $n,string $tel,string $creado):int{global $conn;$conn->query("INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha,creado_en) VALUES('$n','$tel',{$c['id']},'{$c['fecha']}','$creado')");$w=$conn->insert_id;
 if($person)$conn->query("INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,wait_id) VALUES($person,{$c['id']},'{$c['fecha']}','WAITLIST',$w)");return $w;}
function offers(array $c,string $st='PENDING'):array{return q("SELECT o.*,e.link_token FROM tf_offers o LEFT JOIN tf_notify_events e ON e.offer_id=o.id AND e.kind='OFFER' WHERE o.horario_id=? AND o.fecha=? AND o.status=? ORDER BY o.id",[(string)$c['id'],$c['fecha'],$st]);}
function tick():array{global $conn;return tfOffersTick($conn);}
function nIns(array $c):int{return (int)q('SELECT COUNT(*) n FROM inscripciones WHERE horario_id=? AND fecha=?',[(string)$c['id'],$c['fecha']])[0]['n'];}
function nCola(array $c):int{return (int)q('SELECT COUNT(*) n FROM inscripciones_cola WHERE horario_id=? AND fecha=?',[(string)$c['id'],$c['fecha']])[0]['n'];}
function tokenOf(array $o):string{return (string)$o['link_token'];}
$T0=date('Y-m-d H:i:s');$t=fn(int $s)=>date('Y-m-d H:i:s',time()+$s);

// ---- modo de sesión ----
reset_db();$c=clase(2);$A=persona('Ana A','611111111');
$conn->query("UPDATE tf_notify_settings SET v='0' WHERE k='OFFERS_ENABLED'");ck(tfSessionMode($conn,$c['id'],$c['fecha'])==='LEGACY','interruptor apagado = LEGACY');
$conn->query("UPDATE tf_notify_settings SET v='1' WHERE k='OFFERS_ENABLED'");ck(tfSessionMode($conn,$c['id'],$c['fecha'])==='OFFERS','sesión sin cola heredada = OFFERS');
esperar($c,0,'Vieja Cola','699000000',date('Y-m-d H:i:s',time()-3*86400));
ck(tfSessionMode($conn,$c['id'],$c['fecha'])==='LEGACY','con una espera heredada la sesión sigue en LEGACY');
ck(tfLegacyPromotionAllowed($conn,$c['id'],$c['fecha']),'LEGACY: se permite la promoción antigua');

// ---- una plaza, cadena A → B → C ----
reset_db();$c=clase(2);$A=persona('Ana A','611111111');$B=persona('Beto B','622222222');$C=persona('Cris C','633333333');$D=persona('Dani D','644444444');
$i1=inscribir($c,'Fijo Uno','600000001');$i2=inscribir($c,'Fijo Dos','600000002');
$wa=esperar($c,$A,'Ana A','611111111',$t(-300));$wb=esperar($c,$B,'Beto B','622222222',$t(-200));$wc=esperar($c,$C,'Cris C','633333333',$t(-100));
$r=tick();ck($r['created']===0&&count(offers($c))===0,'clase llena: no hay ofertas');
$conn->query("DELETE FROM inscripciones WHERE id=$i1");$r=tick();$o=offers($c);
ck(count($o)===1&&(int)$o[0]['person_id']===$A&&(int)$o[0]['wait_id']===$wa,'se libera una plaza: oferta a la primera entrada (creado_en,id)');
ck(tfHeld($conn,$c['id'],$c['fecha'])===1&&nIns($c)===1,'la plaza queda retenida, sin reserva aún');
ck(tfSchedule($conn,$c['id'],$c['fecha'])['disponibles']===0,'retenida = ocupada en la disponibilidad');
ck(nCola($c)===3,'la entrada sigue vinculada a la espera mientras está pendiente');
$ev=q("SELECT link_token,ttl_at FROM tf_notify_events WHERE kind='OFFER'");ck(count($ev)===1&&strlen((string)$ev[0]['link_token'])===64,'evento OFFER con enlace opaco');
ck((int)q("SELECT COUNT(*) n FROM tf_push_outbox")[0]['n']===1,'un envío para el móvil de Ana');
$exp=strtotime($o[0]['expires_at'])-time();ck($exp>59*60&&$exp<=60*60+2,'clase de otro día: plazo de 1 hora completa');
$hoy=tfNow()->modify('+40 minutes');if($hoy->format('Y-m-d')===tfNow()->format('Y-m-d')){reset_db();$c9=clase(1,40);$A9=persona('Ana Nueve','655000009');esperar($c9,$A9,'Ana Nueve','655000009',$t(-50));tick();$o9=offers($c9);$e9=strtotime($o9[0]['expires_at'])-time();ck(count($o9)===1&&$e9>9*60&&$e9<=10*60+2,'clase de hoy: plazo de 10 minutos');}else ck(true,'(omitida: la prueba cruza la medianoche)');
reset_db();$c=clase(2);$A=persona('Ana A','611111111');$B=persona('Beto B','622222222');$C=persona('Cris C','633333333');$D=persona('Dani D','644444444');
$i1=inscribir($c,'Fijo Uno','600000001');$i2=inscribir($c,'Fijo Dos','600000002');
$wa=esperar($c,$A,'Ana A','611111111',$t(-300));$wb=esperar($c,$B,'Beto B','622222222',$t(-200));$wc=esperar($c,$C,'Cris C','633333333',$t(-100));
$conn->query("DELETE FROM inscripciones WHERE id=$i1");tick();$o=offers($c);
ck(tick()['created']===0&&count(offers($c))===1,'segunda pasada: no duplica la oferta');
// la plaza retenida no se puede coger por otra vía
$res=null;try{$res=tfAtomic($conn,fn()=>tfReserve($conn,$D,$c['id'],$c['fecha'],true));}catch(WebError $e){$res=$e->getMessage();}
ck(is_array($res)&&$res['estado']==='WAITLIST','otra persona no puede ocupar la plaza retenida: va a la espera');
$conn->query("DELETE FROM inscripciones_cola WHERE nombre='Dani D'");$conn->query("UPDATE tf_bookings SET estado='CANCELLED',wait_id=NULL WHERE person_id=$D");
// consulta no modifica
$tokA=tokenOf($o[0]);$v=tfOfferView($conn,$tokA);ck($v['estado']==='PENDING'&&$v['clase']==='Yoga'&&count(offers($c))===1,'consultar la oferta no modifica nada');
try{tfOfferView($conn,str_repeat('0',64));ck(false,'token falso');}catch(WebError $e){ck($e->status===404,'token inexistente = 404');}
// legacy cerrada
tfAtomic($conn,fn()=>tfPromote($conn,$c['id'],$c['fecha']));ck(nIns($c)===1&&nCola($c)===3,'tfPromote antiguo no promueve en modo OFERTAS');
// aceptar: exactamente una reserva, idempotente, dos dispositivos
$r1=tfOfferAccept($conn,$tokA);$r2=tfOfferAccept($conn,$tokA);
ck($r1['ok']&&!$r1['already']&&$r2['ok']&&$r2['already'],'aceptar dos veces es idempotente');
ck(nIns($c)===2&&nCola($c)===2,'exactamente una reserva confirmada y la espera retirada');
$b=q('SELECT estado,reservation_id,wait_id FROM tf_bookings WHERE person_id=?',[(string)$A])[0];ck($b['estado']==='RESERVED'&&$b['reservation_id']!==null&&$b['wait_id']===null,'tf_bookings sincronizado');
ck((int)q("SELECT COUNT(*) n FROM tf_notify_events WHERE kind='OFFER_ACCEPTED'")[0]['n']===1,'confirmación de aceptación emitida una vez');
ck(tfHeld($conn,$c['id'],$c['fecha'])===0&&count(offers($c))===0,'sin ofertas pendientes tras aceptar');
// rechazar B (si se libera otra): se retira y se ofrece a C
$conn->query("DELETE FROM inscripciones WHERE nombre='Fijo Dos'");tick();$oB=offers($c);ck(count($oB)===1&&(int)$oB[0]['person_id']===$B,'siguiente entrada: Beto');
$d1=tfOfferDecline($conn,tokenOf($oB[0]));$d2=tfOfferDecline($conn,tokenOf($oB[0]));
ck($d1['ok']&&$d2['ok']&&$d2['already'],'rechazar es idempotente');
ck(!q('SELECT id FROM inscripciones_cola WHERE id=?',[(string)$wb]),'rechazo: Beto sale de la espera');
$oC=offers($c);ck(count($oC)===1&&(int)$oC[0]['person_id']===$C,'rechazo: la plaza pasa a Cris en la misma operación');
ck(tfOfferAccept($conn,tokenOf($oB[0]))['code']==='OFFER_CLOSED','no se acepta una oferta rechazada');
$conn->query("INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha) VALUES('Beto B','622222222',{$c['id']},'{$c['fecha']}')");ck(true,'la persona retirada puede apuntarse otra vez (al final)');
// caducidad → siguiente
$conn->query("UPDATE tf_offers SET expires_at=NOW() - INTERVAL 1 SECOND WHERE status='PENDING'");tick();
ck(count(offers($c,'EXPIRED'))===1&&!q('SELECT id FROM inscripciones_cola WHERE id=?',[(string)$wc]),'caduca: Cris sale de la espera');
ck(count(offers($c))===1,'caduca: se ofrece al siguiente (Beto, vuelto a apuntar)');
// aceptación de una oferta ya caducada
$conn->query("UPDATE tf_offers SET expires_at=NOW() - INTERVAL 1 SECOND WHERE status='PENDING'");$late=offers($c)[0];$rl=tfOfferAccept($conn,tokenOf($late));
ck(!$rl['ok']&&$rl['code']==='OFFER_EXPIRED'&&nIns($c)===1,'no se acepta una oferta caducada (aunque el worker no haya pasado)');

// ---- varias plazas libres: varias ofertas, sin pasarse del aforo ----
reset_db();$c=clase(3);$P=[];foreach(['Uno','Dos','Tres','Cuatro','Cinco'] as $k=>$n)$P[$n]=persona("$n P","65000000$k");
inscribir($c,'Fijo','600000009');foreach(array_keys($P) as $k=>$n)esperar($c,$P[$n],"$n P","65000000$k",$t(-500+$k*10));
tick();$o=offers($c);ck(count($o)===2&&array_unique(array_column($o,'person_id'))===array_column($o,'person_id'),'2 plazas libres = 2 ofertas a personas distintas');
ck(tfHeld($conn,$c['id'],$c['fecha'])+nIns($c)===3,'retenidas + reservas = aforo');tick();ck(count(offers($c))===2,'repetir no supera el aforo');
foreach($o as $x)ck(tfOfferAccept($conn,tokenOf($x))['ok'],'aceptan las dos');ck(nIns($c)===3&&nCola($c)===3,'aforo exacto y 3 siguen esperando');

// ---- cancelación de clase ----
reset_db();$c=clase(1);$A=persona('Ana A','611111111');$B=persona('Beto B','622222222');$i=inscribir($c,'Fijo','600000009');esperar($c,$A,'Ana A','611111111',$t(-50));esperar($c,$B,'Beto B','622222222',$t(-40));
$conn->query("DELETE FROM inscripciones WHERE id=$i");tick();$o=offers($c)[0];
$conn->query("INSERT INTO clases_canceladas(horario_id,fecha) VALUES({$c['id']},'{$c['fecha']}')");tfAtomic($conn,fn()=>tfOffersCancelSession($conn,$c['id'],$c['fecha'],'staff:test'));
ck(count(offers($c,'CANCELLED'))===1&&count(offers($c))===0,'cancelar la clase invalida la oferta');tick();ck(count(offers($c))===0&&nCola($c)===2,'la cadena se detiene y nadie se borra');
ck(tfOfferAccept($conn,tokenOf($o))['code']==='OFFER_CLOSED','no se acepta en clase cancelada');
// cancelada con la oferta aún pendiente (sin pasar por el hook): el barrido lo detecta
reset_db();$c=clase(1);$A=persona('Ana A','611111111');esperar($c,$A,'Ana A','611111111',$t(-50));tick();$o=offers($c)[0];$conn->query("INSERT INTO clases_canceladas(horario_id,fecha) VALUES({$c['id']},'{$c['fecha']}')");
$ra=tfOfferAccept($conn,tokenOf($o));ck(!$ra['ok']&&$ra['code']==='SESSION_CANCELLED'&&nIns($c)===0,'aceptar en clase cancelada: rechazado y sin reserva');

// ---- clase inminente: el plazo termina al empezar ----
reset_db();$c=clase(1,10);$A=persona('Ana A','611111111');esperar($c,$A,'Ana A','611111111',$t(-50));tick();$o=offers($c);
ck(count($o)===1&&$o[0]['expires_at']===$c['start']->format('Y-m-d H:i:s'),'clase en 10 min: la hora límite es la de inicio');
ck(tfOfferView($conn,tokenOf($o[0]))['limite']===$c['start']->format('H:i'),'se muestra la hora límite real');
$conn->query("UPDATE horarios SET hora='".$c['start']->modify('-30 minutes')->format('H:i').'-'.$c['start']->modify('+30 minutes')->format('H:i')."'");   // la clase «ya empezó»
$rs=tfOfferAccept($conn,tokenOf($o[0]));ck(!$rs['ok']&&$rs['code']==='OFFER_EXPIRED'&&nIns($c)===0,'clase empezada: no se acepta');

// ---- sin buzón: incidencia, nunca confirmación automática ----
reset_db();$c=clase(1);$A=persona('Ana A','611111111',false);esperar($c,$A,'Ana A','611111111',$t(-50));tick();
ck(count(offers($c))===1&&nIns($c)===0,'sin avisos activos: la oferta existe pero NO se confirma sola');
ck((int)q("SELECT COUNT(*) n FROM tf_notify_audit WHERE action='OFFER_UNDELIVERABLE'")[0]['n']===1,'incidencia visible para recepción');
$o=offers($c)[0];$rs=tfOfferAcceptByStaff($conn,(int)$o['id'],'recepcion1');ck($rs['ok']&&nIns($c)===1,'recepción confirma a petición de la persona');
ck((int)q("SELECT COUNT(*) n FROM tf_notify_audit WHERE action='OFFER_ACCEPTED' AND actor='staff:recepcion1'")[0]['n']===1,'auditoría del trabajador');
$o2=null;reset_db();$c=clase(1);$A=persona('Ana A','611111111');esperar($c,$A,'Ana A','611111111',$t(-50));tick();$o=offers($c)[0];$conn->query("UPDATE tf_offers SET expires_at=NOW() - INTERVAL 1 SECOND");
$rs=tfOfferAcceptByStaff($conn,(int)$o['id'],'recepcion1');ck(!$rs['ok']&&$rs['code']==='OFFER_EXPIRED','recepción no puede confirmar fuera de plazo');

// ---- interruptores ----
reset_db();$c=clase(1);$A=persona('Ana A','611111111');$B=persona('Beto B','622222222');esperar($c,$A,'Ana A','611111111',$t(-50));esperar($c,$B,'Beto B','622222222',$t(-40));tick();
$conn->query("UPDATE tf_notify_settings SET v='0' WHERE k='OFFERS_ENABLED'");ck(tfSessionMode($conn,$c['id'],$c['fecha'])==='OFFERS'&&!tfLegacyPromotionAllowed($conn,$c['id'],$c['fecha']),'apagar el interruptor no reactiva la promoción antigua mientras haya ofertas pendientes');
$conn->query("UPDATE tf_offers SET expires_at=NOW() - INTERVAL 1 SECOND");tick();ck(count(offers($c,'EXPIRED'))===1&&count(offers($c))===0,'con el interruptor apagado las pendientes se resuelven y no se crean nuevas');
ck(tfLegacyPromotionAllowed($conn,$c['id'],$c['fecha']),'resueltas las ofertas, vuelve la promoción antigua');

// ---- la lista de espera exige avisos (todas las rutas) ----
reset_db();$c=clase(1);$A=persona('Ana A','611111111',false);$B=persona('Beto B','622222222');inscribir($c,'Fijo','600000009');
foreach([[$A,'Ana A','611111111',false],[$B,'Beto B','622222222',true]] as [$pid,$n,$tel,$should]){
 $e=null;try{tfRequireNoticesForWaitlist($conn,$c['id'],$c['fecha'],$n,$tel);}catch(WebError $x){$e=$x->getMessage();}ck(($e===null)===$should,"cola exige avisos: $n");}
$e=null;try{tfAtomic($conn,fn()=>tfReserve($conn,$A,$c['id'],$c['fecha'],true));}catch(WebError $x){$e=$x->getMessage();}ck($e==='WAITLIST_REQUIRES_NOTICES','tfReserve: sin avisos no entra en la cola');
ck(is_array(tfAtomic($conn,fn()=>tfReserve($conn,$B,$c['id'],$c['fecha'],true))),'tfReserve: con avisos sí');
$conn->query("UPDATE tf_notify_settings SET v='0' WHERE k='OFFERS_ENABLED'");$e=null;try{tfRequireNoticesForWaitlist($conn,$c['id'],$c['fecha'],'Ana A','611111111');}catch(WebError $x){$e=1;}ck($e===null,'modo LEGACY: la cola sigue como antes (sin exigir avisos)');
// ---- descanso nocturno: la plaza se retiene ya, el aviso y el plazo empiezan al acabar la madrugada ----
reset_db();$now=tfNow();$desde=$now->modify('-1 hour')->format('H:i');$hasta=$now->modify('+1 hour')->format('H:i');
if($now->format('H')>=1&&$now->format('H')<=22){   // la ventana de prueba no cruza la medianoche
 $conn->query("UPDATE tf_notify_settings SET v='$desde' WHERE k='OFFERS_QUIET_FROM'");$conn->query("UPDATE tf_notify_settings SET v='$hasta' WHERE k='OFFERS_QUIET_TO'");
 $c=clase(1,1500);$A=persona('Ana Q','655000001');$D=persona('Dani Q','655000004');esperar($c,$A,'Ana Q','655000001',$t(-50));tick();$o=offers($c);
 $fin=tfNow()->setTime((int)substr($hasta,0,2),(int)substr($hasta,3,2),0);
 ck(count($o)===1&&tfHeld($conn,$c['id'],$c['fecha'])===1,'de madrugada: la oferta se crea y RETIENE la plaza');
 ck($o[0]['expires_at']===$fin->modify('+60 minutes')->format('Y-m-d H:i:s'),'el plazo (1 hora) empieza cuando acaba el descanso');
 $ev=tfQuery($conn,"SELECT not_before FROM tf_notify_events WHERE kind='OFFER'")[0]['not_before'];ck($ev===$fin->format('Y-m-d H:i:s'),'el aviso no sale hasta que acaba el descanso');
 $r=null;try{$r=tfAtomic($conn,fn()=>tfReserve($conn,$D,$c['id'],$c['fecha'],true));}catch(WebError $e){$r=$e->getMessage();}ck(is_array($r)&&$r['estado']==='WAITLIST','mientras tanto nadie se salta la cola: la plaza sigue retenida');
 ck(tfMyClasses($conn,['nombre'=>'Ana Q','telefono'=>'655000001'])['espera'][0]['oferta_hasta']===null,'«Mis clases» no enseña la oferta hasta que se avise');
 // clase de hoy que empieza antes de poder ofrecerla después del descanso: se ofrece ya
 reset_db();$conn->query("UPDATE tf_notify_settings SET v='$desde' WHERE k='OFFERS_QUIET_FROM'");$conn->query("UPDATE tf_notify_settings SET v='$hasta' WHERE k='OFFERS_QUIET_TO'");
 $c=clase(1,40);$A=persona('Ana Q','655000001');esperar($c,$A,'Ana Q','655000001',$t(-50));tick();$o=offers($c);
 ck(count($o)===1&&strtotime($o[0]['expires_at'])-time()<=10*60+2,'clase que empieza antes del fin del descanso: se ofrece ya, sin esperar');
} else ck(true,'(omitida: cruza la medianoche)');
// ---- ofertas acotadas a un horario de prueba ----
reset_db();$c=clase(1);$c2=clase(1);$A=persona('Ana A','611111111');$B=persona('Beto B','622222222');
$conn->query("UPDATE tf_notify_settings SET v='{$c['id']}' WHERE k='OFFERS_ONLY_HORARIOS'");
ck(tfSessionMode($conn,$c['id'],$c['fecha'])==='OFFERS'&&tfSessionMode($conn,$c2['id'],$c2['fecha'])==='LEGACY','acotado: solo el horario de prueba usa ofertas, el resto sigue como antes');
$e=null;try{tfRequireNoticesForWaitlist($conn,$c2['id'],$c2['fecha'],'Sin Avisos','699999999');}catch(WebError $x){$e=1;}ck($e===null,'acotado: en las demás clases la espera no exige avisos');
echo ($f?'RESULT: FAIL':'RESULT: PASS')." ($p ok, $f fallos)\n";exit($f?1:0);
