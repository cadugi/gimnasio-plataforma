<?php
declare(strict_types=1);
// Suscripciones push, aviso de prueba y alta de eventos. Los eventos se escriben dentro de la transacción del llamador;
// el envío de red lo hace después el remitente aislado (push_sender.py), nunca aquí.
require_once __DIR__.'/notify.php';

/** Solo servicios push conocidos, por HTTPS y puerto 443: el remitente no puede usarse para llegar a servicios internos. */
function tfPushEndpointOk(string $url):bool{
 if(strlen($url)>600||!preg_match('#^https://([a-z0-9.-]+)(:443)?/[^\s]*$#i',$url,$m))return false;
 $host=strtolower($m[1]);if(filter_var($host,FILTER_VALIDATE_IP))return false;
 foreach(['fcm.googleapis.com','updates.push.services.mozilla.com','push.apple.com','notify.windows.com','push.services.mozilla.com'] as $ok)
  if($host===$ok||str_ends_with($host,'.'.$ok))return true;
 return false;
}
function tfBase64Url(string $v,int $min,int $max):bool{return preg_match('/^[A-Za-z0-9_-]+$/',$v)===1&&strlen($v)>=$min&&strlen($v)<=$max;}

function tfSubscribe(mysqli $db,array $device,array $r):array{
 $endpoint=(string)($r['endpoint']??'');$k=(array)($r['keys']??[]);$p=(string)($k['p256dh']??'');$a=(string)($k['auth']??'');
 tfRequire(tfPushEndpointOk($endpoint)&&tfBase64Url($p,80,100)&&tfBase64Url($a,16,30),'INVALID_SUBSCRIPTION',400);
 tfRateLimit($db,'subscribe:'.$device['id'],10,3600);
 return tfAtomic($db,function()use($db,$device,$endpoint,$p,$a){
  $h=hash('sha256',$endpoint);
  // El mismo navegador puede haber cambiado de persona: la suscripción pasa a este móvil y exige probar de nuevo.
  tfQuery($db,"INSERT INTO tf_push_subscriptions(device_id,endpoint_hash,endpoint,p256dh,auth_secret) VALUES(?,?,?,?,?) ON DUPLICATE KEY UPDATE device_id=VALUES(device_id),endpoint=VALUES(endpoint),p256dh=VALUES(p256dh),auth_secret=VALUES(auth_secret),status='ACTIVE',failure_count=0,last_error=NULL,test_sent_at=NULL,test_confirmed_at=NULL",[(string)$device['id'],$h,$endpoint,$p,$a]);
  tfQuery($db,"UPDATE tf_push_subscriptions SET status='REVOKED' WHERE device_id=? AND endpoint_hash<>? AND status='ACTIVE'",[(string)$device['id'],$h]);   // un móvil, un buzón
  tfNotifyAudit($db,'person:'.$device['person_id'],'PUSH_SUBSCRIBED',(int)$device['person_id'],(int)$device['id']);
  return tfAvisosStatus($db,$device);
 });
}
function tfUnsubscribe(mysqli $db,array $device):array{
 return tfAtomic($db,function()use($db,$device){
  tfQuery($db,"UPDATE tf_push_subscriptions SET status='REVOKED' WHERE device_id=? AND status='ACTIVE'",[(string)$device['id']]);
  tfNotifyAudit($db,'person:'.$device['person_id'],'PUSH_UNSUBSCRIBED',(int)$device['person_id'],(int)$device['id']);
  return tfAvisosStatus($db,$device);
 });
}
/** ACTIVATED = suscripción activa + prueba confirmada · NONE = nunca activó avisos · REVIEW = hay algo que revisar. */
function tfAvisosStatus(mysqli $db,array $device):array{
 $s=tfQuery($db,"SELECT id,status,test_sent_at,test_confirmed_at,last_error FROM tf_push_subscriptions WHERE device_id=? ORDER BY id DESC LIMIT 1",[(string)$device['id']])[0]??null;
 $state=!$s?'NONE':(($s['status']==='ACTIVE'&&$s['test_confirmed_at']!==null)?'ACTIVATED':'REVIEW');
 return ['state'=>$state,'subscribed'=>$s&&$s['status']==='ACTIVE','test_sent'=>$s&&$s['test_sent_at']!==null,'test_confirmed'=>$s&&$s['test_confirmed_at']!==null,'problem'=>$s&&$s['status']!=='ACTIVE'?$s['status']:null];
}
/** ¿Esta persona tiene algún móvil con avisos activados y probados? (requisito de la lista de espera, comprobado en servidor). */
function tfPersonHasConfirmedPush(mysqli $db,int $person):bool{
 return (bool)tfQuery($db,"SELECT s.id FROM tf_push_subscriptions s JOIN tf_devices d ON d.id=s.device_id WHERE d.person_id=? AND d.revoked_at IS NULL AND s.status='ACTIVE' AND s.test_confirmed_at IS NOT NULL LIMIT 1",[(string)$person]);
}

/**
 * Registra un evento y un envío por cada suscripción activa de la persona (o solo $onlySub). Llamar dentro de tfAtomic.
 * dedupe_key evita duplicados. Devuelve el id del evento, o 0 si ya existía.
 */
function tfNotifyEmit(mysqli $db,string $kind,int $person,string $dedupe,int $ttlSeconds,array $x=[],?int $onlySub=null,?string $notBefore=null):int{
 $now=tfNow();$ttl=$now->modify("+$ttlSeconds seconds")->format('Y-m-d H:i:s');
 tfQuery($db,'INSERT IGNORE INTO tf_notify_events(kind,person_id,booking_id,offer_id,horario_id,fecha,dedupe_key,not_before,ttl_at,link_token) VALUES(?,?,?,?,?,?,?,?,?,?)',
  [$kind,(string)$person,isset($x['booking_id'])?(string)$x['booking_id']:null,isset($x['offer_id'])?(string)$x['offer_id']:null,isset($x['horario_id'])?(string)$x['horario_id']:null,$x['fecha']??null,substr($dedupe,0,120),$notBefore??$now->format('Y-m-d H:i:s'),$ttl,$x['link_token']??null]);
 $id=(int)$db->insert_id;if($id<=0)return 0;
 $sql="SELECT s.id FROM tf_push_subscriptions s JOIN tf_devices d ON d.id=s.device_id WHERE d.person_id=? AND d.revoked_at IS NULL AND s.status='ACTIVE'";$args=[(string)$person];
 if($onlySub!==null){$sql.=' AND s.id=?';$args[]=(string)$onlySub;}
 foreach(tfQuery($db,$sql,$args) as $s)tfQuery($db,'INSERT INTO tf_push_outbox(event_id,subscription_id,next_attempt_at) VALUES(?,?,?)',[(string)$id,$s['id'],$notBefore??$now->format('Y-m-d H:i:s')]);
 return $id;
}
function tfRequestTest(mysqli $db,array $device):array{
 tfRateLimit($db,'test:'.$device['id'],5,3600);
 return tfAtomic($db,function()use($db,$device){
  $s=tfQuery($db,"SELECT id FROM tf_push_subscriptions WHERE device_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1 FOR UPDATE",[(string)$device['id']])[0]??null;
  tfRequire($s,'PUSH_NOT_ACTIVE',409);
  tfQuery($db,'UPDATE tf_push_subscriptions SET test_sent_at=NULL,test_confirmed_at=NULL WHERE id=?',[$s['id']]);
  tfNotifyEmit($db,'TEST',(int)$device['person_id'],'TEST:'.$s['id'].':'.bin2hex(random_bytes(6)),300,[],(int)$s['id']);
  return tfAvisosStatus($db,$device);
 });
}
/** La persona confirma que vio el aviso de prueba. Solo vale si el servidor llegó a enviarlo. Comprueba ese momento, no el futuro. */
function tfConfirmTest(mysqli $db,array $device):array{
 return tfAtomic($db,function()use($db,$device){
  tfRequire(tfQuery($db,"SELECT id FROM tf_push_subscriptions WHERE device_id=? AND status='ACTIVE' AND test_sent_at IS NOT NULL",[(string)$device['id']]),'TEST_NOT_SENT',409);
  tfQuery($db,"UPDATE tf_push_subscriptions SET test_confirmed_at=NOW() WHERE device_id=? AND status='ACTIVE' AND test_sent_at IS NOT NULL",[(string)$device['id']]);
  tfNotifyAudit($db,'person:'.$device['person_id'],'PUSH_TEST_CONFIRMED',(int)$device['person_id'],(int)$device['id']);
  return tfAvisosStatus($db,$device);
 });
}
/** Avisos propios: qué se envió y si el servicio push lo aceptó. «Aceptado» no significa «leído». */
function tfMyNotices(mysqli $db,int $person):array{
 return tfQuery($db,"SELECT e.kind,e.created_at,h.clase,e.fecha,LEFT(h.hora,5) hora,CASE MAX(o.status='ACCEPTED') WHEN 1 THEN 'ENVIADO' ELSE IF(e.status='EXPIRED','CADUCADO',IF(e.status='PENDING','PENDIENTE','NO_ENVIADO')) END estado FROM tf_notify_events e LEFT JOIN horarios h ON h.id=e.horario_id LEFT JOIN tf_push_outbox o ON o.event_id=e.id WHERE e.person_id=? AND e.kind<>'TEST' GROUP BY e.id ORDER BY e.id DESC LIMIT 20",[(string)$person]);
}

/** Personas con avisos activos cuyo nombre normalizado y teléfono normalizado coinciden EXACTAMENTE con una reserva. Compartir teléfono no mezcla fichas. */
function tfPeopleForReservation(mysqli $db,string $name,string $phone):array{
 $ph=tfNormPhone($phone);if($ph==='')return [];$n=tfNormName($name);$out=[];
 foreach(tfQuery($db,"SELECT p.id,p.nombre FROM tf_people p WHERE p.active=1 AND p.telefono=? AND EXISTS (SELECT 1 FROM tf_devices d JOIN tf_push_subscriptions s ON s.device_id=d.id WHERE d.person_id=p.id AND d.revoked_at IS NULL AND s.status='ACTIVE')",[$ph]) as $p)
  if(tfNormName($p['nombre'])===$n)$out[]=(int)$p['id'];
 return $out;
}
function tfClassStart(string $date,string $hora):DateTimeImmutable{return new DateTimeImmutable($date.' '.substr($hora,0,5),new DateTimeZone('Europe/Madrid'));}

/**
 * Programa el recordatorio de 2 h para reservas CONFIRMADAS de los próximos 2 días (inscripciones; nunca la cola).
 * No crea recordatorios atrasados: si la reserva se hizo con menos de 2 h de antelación, o ya pasó el momento, no hay recordatorio.
 * El remitente vuelve a comprobar reserva, clase y horario justo antes de enviar.
 */
function tfPlanReminders(mysqli $db):int{
 $now=tfNow();$n=0;
 $rows=tfQuery($db,"SELECT i.id,i.nombre,i.telefono,i.horario_id,i.fecha,i.creado_en,h.hora FROM inscripciones i JOIN horarios h ON h.id=i.horario_id WHERE i.fecha BETWEEN ? AND ? AND NOT EXISTS (SELECT 1 FROM clases_canceladas c WHERE c.horario_id=i.horario_id AND c.fecha=i.fecha)",[$now->format('Y-m-d'),$now->modify('+2 days')->format('Y-m-d')]);
 foreach($rows as $r){
  if(!preg_match('/^\d{2}:\d{2}-\d{2}:\d{2}$/',$r['hora']))continue;
  $start=tfClassStart($r['fecha'],$r['hora']);$due=$start->modify('-2 hours');
  if($start<=$now||$now>$due->modify('+10 minutes'))continue;                       // clase empezada o recordatorio ya atrasado
  if(new DateTimeImmutable($r['creado_en'],new DateTimeZone('Europe/Madrid'))>$due)continue;   // reservada con menos de 2 h: sin recordatorio
  foreach(tfPeopleForReservation($db,$r['nombre'],$r['telefono']) as $person)
   $n+=tfAtomic($db,fn()=>tfNotifyEmit($db,'REMINDER',$person,'REM:'.$r['id'].':'.$person,(int)($start->getTimestamp()-$now->getTimestamp()),['booking_id'=>(int)$r['id'],'horario_id'=>(int)$r['horario_id'],'fecha'=>$r['fecha']],null,$due->format('Y-m-d H:i:s')))>0?1:0;
 }
 return $n;
}

/** ¿Se enviará realmente a esta persona? Interruptor general o lista de personas de prueba. */
function tfSendingEnabledFor(mysqli $db,int $person):bool{
 if(tfNotifySwitch($db,'PUSH_SEND_ENABLED'))return true;
 $allow=(string)(tfQuery($db,"SELECT v FROM tf_notify_settings WHERE k='PUSH_ALLOW_PERSONS'")[0]['v']??'');
 return in_array((string)$person,preg_split('/\D+/',$allow,-1,PREG_SPLIT_NO_EMPTY)?:[],true);
}

/** Reserva hecha en recepción: avisa a los móviles asociados a ESA persona (nombre + teléfono exactos). Devuelve cuántas personas recibirán el aviso; 0 = «sin avisos». */
function tfNotifyReceptionBooking(mysqli $db,string $name,string $phone,int $schedule,string $date,int $reservation):int{
 $n=0;$h=tfQuery($db,'SELECT hora FROM horarios WHERE id=?',[(string)$schedule])[0]??null;if(!$h)return 0;
 $ttl=max(60,tfClassStart($date,$h['hora'])->getTimestamp()-tfNow()->getTimestamp());
 foreach(tfPeopleForReservation($db,$name,$phone) as $person)if(tfNotifyEmit($db,'RECEPTION_BOOKING',$person,'RB:'.$reservation.':'.$person,min($ttl,86400),['booking_id'=>$reservation,'horario_id'=>$schedule,'fecha'=>$date])>0)$n++;
 return $n;
}
/** Clase cancelada: avisa a quienes tenían reserva confirmada. Las entradas de espera no reciben este aviso (su oferta ya se invalida). */
function tfNotifyClassCancelled(mysqli $db,int $schedule,string $date):int{
 $n=0;$h=tfQuery($db,'SELECT hora FROM horarios WHERE id=?',[(string)$schedule])[0]??null;if(!$h)return 0;
 $ttl=max(300,min(86400,tfClassStart($date,$h['hora'])->getTimestamp()-tfNow()->getTimestamp()));
 foreach(tfQuery($db,'SELECT id,nombre,telefono FROM inscripciones WHERE horario_id=? AND fecha=?',[(string)$schedule,$date]) as $r)
  foreach(tfPeopleForReservation($db,$r['nombre'],$r['telefono']) as $person)if(tfNotifyEmit($db,'CLASS_CANCELLED',$person,'CC:'.$r['id'].':'.$person,$ttl,['booking_id'=>(int)$r['id'],'horario_id'=>$schedule,'fecha'=>$date])>0)$n++;
 return $n;
}
/** Cambio de día u hora de un horario: avisa a quienes tienen reservas FUTURAS de ese horario. dedupe incluye el nuevo horario para no repetir. */
function tfNotifyScheduleChanged(mysqli $db,int $schedule,string $dia,string $hora):int{
 $n=0;$sig=substr(md5($dia.'|'.$hora),0,10);$today=tfNow()->format('Y-m-d');
 foreach(tfQuery($db,'SELECT id,nombre,telefono,fecha FROM inscripciones WHERE horario_id=? AND fecha>=?',[(string)$schedule,$today]) as $r)
  foreach(tfPeopleForReservation($db,$r['nombre'],$r['telefono']) as $person)if(tfNotifyEmit($db,'SCHEDULE_CHANGED',$person,'SC:'.$r['id'].':'.$person.':'.$sig,172800,['booking_id'=>(int)$r['id'],'horario_id'=>$schedule,'fecha'=>$r['fecha']])>0)$n++;
 return $n;
}

/** Referencia opaca de una reserva/espera para ESTE móvil: id + HMAC con el secreto de su cookie. No se puede adivinar ni usar desde otro dispositivo. */
function tfClientRef(string $kind,int $id):string{return $id.'.'.substr(hash_hmac('sha256',$kind.':'.$id,(string)($_COOKIE[TF_DEVICE_COOKIE]??'')),0,24);}
function tfClientRefId(string $kind,string $ref):int{if(!preg_match('/^(\d{1,10})\.([a-f0-9]{24})$/',$ref,$m))return 0;return hash_equals(tfClientRef($kind,(int)$m[1]),$ref)?(int)$m[1]:0;}

/** «Mis clases» de una persona: sus reservas confirmadas y esperas futuras (por nombre + teléfono normalizados, también las hechas en recepción) con la posición en la cola. Solo clase, día y hora. */
function tfMyClasses(mysqli $db,array $person):array{
 $today=tfNow()->format('Y-m-d');$key=tfPhoneKey((string)$person['telefono']);$name=tfNormName((string)$person['nombre']);$phone=tfPhoneSql('x.telefono');
 $base="SELECT x.id,x.nombre,x.fecha,h.clase,LEFT(h.hora,5) hora,h.id horario,(SELECT COUNT(*) FROM clases_canceladas c WHERE c.horario_id=x.horario_id AND c.fecha=x.fecha) cancelada";
 $res=[];$wait=[];
 foreach(tfQuery($db,"$base FROM inscripciones x JOIN horarios h ON h.id=x.horario_id WHERE x.fecha>=? AND $phone=? ORDER BY x.fecha,h.hora LIMIT 80",[$today,$key]) as $r)
  if(tfNormName($r['nombre'])===$name)$res[]=['clase'=>$r['clase'],'fecha'=>$r['fecha'],'hora'=>$r['hora'],'cancelada'=>(int)$r['cancelada']>0,'puede'=>(int)$r['cancelada']===0&&tfClassStart($r['fecha'],$r['hora'])>tfNow(),'ref'=>tfClientRef('r',(int)$r['id'])];
 foreach(tfQuery($db,"$base,(SELECT COUNT(*) FROM inscripciones_cola w WHERE w.horario_id=x.horario_id AND w.fecha=x.fecha AND (w.creado_en,w.id)<=(x.creado_en,x.id)) posicion,(SELECT COUNT(*) FROM inscripciones_cola w WHERE w.horario_id=x.horario_id AND w.fecha=x.fecha) total,(SELECT SUBSTRING(o.expires_at,12,5) FROM tf_offers o JOIN tf_notify_events ev ON ev.offer_id=o.id AND ev.kind='OFFER' WHERE o.wait_id=x.id AND o.status='PENDING' AND ev.not_before<=NOW() LIMIT 1) oferta FROM inscripciones_cola x JOIN horarios h ON h.id=x.horario_id WHERE x.fecha>=? AND $phone=? ORDER BY x.fecha,h.hora LIMIT 80",[$today,$key]) as $r)
  if(tfNormName($r['nombre'])===$name)$wait[]=['clase'=>$r['clase'],'fecha'=>$r['fecha'],'hora'=>$r['hora'],'cancelada'=>(int)$r['cancelada']>0,'posicion'=>(int)$r['posicion'],'total'=>(int)$r['total'],'oferta_hasta'=>$r['oferta'],'puede'=>(int)$r['cancelada']===0&&tfClassStart($r['fecha'],$r['hora'])>tfNow(),'ref'=>tfClientRef('w',(int)$r['id'])];
 return ['reservas'=>$res,'espera'=>$wait];
}
