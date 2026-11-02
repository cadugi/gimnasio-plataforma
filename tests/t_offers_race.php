<?php
declare(strict_types=1);
// Concurrencia de ofertas con procesos PHP reales. Modos: setup | accept TOKEN | reserve PERSON | check. Solo BD de pruebas.
$root=getenv('TF_WEB_ROOT')?:dirname(__DIR__).'/web';require $root.'/sso/offers.php';require $root.'/public/conexion.php';
if(!str_contains(getenv('TF_REAL_DB_NAME')?:'','test'))exit(2);$_SERVER['REMOTE_ADDR']='203.0.113.8';
$mode=$argv[1]??'';$days=['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
$state='/tmp/tf-race-state.json';
if($mode==='setup'){
 foreach(['tf_push_outbox','tf_notify_events','tf_offers','tf_push_subscriptions','tf_devices','tf_notify_audit','tf_rate_limits','tf_requests','tf_bookings','tf_people','inscripciones','inscripciones_cola','clases_canceladas','horarios'] as $t)$conn->query("DELETE FROM $t");
 $conn->query("UPDATE tf_notify_settings SET v='1' WHERE k='OFFERS_ENABLED'");$conn->query("UPDATE tf_notify_settings SET v='' WHERE k IN ('OFFERS_ONLY_HORARIOS','OFFERS_QUIET_FROM','OFFERS_QUIET_TO')");$conn->query("UPDATE tf_notify_settings SET v=DATE_FORMAT(NOW() - INTERVAL 1 DAY,'%Y-%m-%d %H:%i:%s') WHERE k='OFFERS_SINCE'");
 $s=tfNow()->modify('+1500 minutes');$conn->query("INSERT INTO horarios(clase,dia,hora,limite) VALUES('Yoga','{$days[(int)$s->format('w')]}','".$s->format('H:i').'-'.$s->modify('+1 hour')->format('H:i')."',1)");$h=$conn->insert_id;$d=$s->format('Y-m-d');
 $mk=function(string $n,string $tel)use($conn){$conn->query("INSERT INTO tf_people(nombre,telefono) VALUES('$n','$tel')");$id=$conn->insert_id;$conn->query("INSERT INTO tf_devices(person_id,token_hash) VALUES($id,'".hash('sha256',$n)."')");$dv=$conn->insert_id;$conn->query("INSERT INTO tf_push_subscriptions(device_id,endpoint_hash,endpoint,p256dh,auth_secret,test_confirmed_at,test_sent_at) VALUES($dv,'".hash('sha256','e'.$n)."','https://fcm.googleapis.com/x','k','a',NOW(),NOW())");return $id;};
 $A=$mk('Ana A','611111111');$others=[];foreach(range(1,6) as $k)$others[]=$mk("Otro $k","6222222$k$k");
 $conn->query("INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha,creado_en) VALUES('Ana A','611111111',$h,'$d',NOW() - INTERVAL 5 MINUTE)");$w=$conn->insert_id;$conn->query("INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,wait_id) VALUES($A,$h,'$d','WAITLIST',$w)");
 tfOffersTick($conn);$tok=tfQuery($conn,"SELECT link_token FROM tf_notify_events WHERE kind='OFFER'")[0]['link_token'];
 file_put_contents($state,json_encode(['h'=>$h,'d'=>$d,'tok'=>$tok,'others'=>$others]));echo "ok\n";exit(0);
}
$S=json_decode((string)file_get_contents($state),true);
if($mode==='accept'){$r=tfOfferAccept($conn,$S['tok']);echo json_encode(['ok'=>$r['ok'],'already'=>$r['already']??null]),"\n";exit(0);}
if($mode==='reserve'){try{$r=tfAtomic($conn,fn()=>tfReserve($conn,(int)$argv[2],$S['h'],$S['d'],true));echo json_encode(['estado'=>$r['estado']]),"\n";}catch(WebError $e){echo json_encode(['err'=>$e->getMessage()]),"\n";}exit(0);}
if($mode==='check'){
 $n=(int)tfQuery($conn,'SELECT COUNT(*) n FROM inscripciones WHERE horario_id=? AND fecha=?',[(string)$S['h'],$S['d']])[0]['n'];
 $res=tfQuery($conn,"SELECT person_id FROM tf_bookings WHERE estado='RESERVED'");$off=tfQuery($conn,'SELECT status FROM tf_offers');
 echo json_encode(['inscripciones'=>$n,'reserved_bookings'=>count($res),'offers'=>array_column($off,'status')]),"\n";exit(0);
}
