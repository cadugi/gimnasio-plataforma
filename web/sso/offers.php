<?php
declare(strict_types=1);
// Ofertas de plaza desde la lista de espera. TODA la lógica vive aquí: ninguna ruta promueve por su cuenta cuando la sesión está en modo OFERTAS.
// Las funciones que escriben deben llamarse dentro de tfAtomic() (bloqueo compartido tf_mutex). El reloj es el del servidor (Europe/Madrid).
require_once __DIR__.'/avisos.php';require_once __DIR__.'/admin_legacy_support.php';

// Plazo para aceptar una plaza: 10 minutos si la clase es HOY; 1 hora si es otro día. En ambos casos termina antes si la clase empieza antes.
const TF_OFFER_MINUTES_SAME_DAY=10;
const TF_OFFER_MINUTES_OTHER_DAY=60;
/** Fin del descanso nocturno si AHORA estamos dentro de él (por defecto 23:00-08:00, hora de Madrid); null si no hay descanso. */
function tfQuietEnd(mysqli $db,DateTimeImmutable $now):?DateTimeImmutable{
 $from=tfSetting($db,'OFFERS_QUIET_FROM');$to=tfSetting($db,'OFFERS_QUIET_TO');
 if(!preg_match('/^(\d{1,2}):(\d{2})$/',$from,$f)||!preg_match('/^(\d{1,2}):(\d{2})$/',$to,$t))return null;
 $mins=(int)$now->format('H')*60+(int)$now->format('i');$a=(int)$f[1]*60+(int)$f[2];$b=(int)$t[1]*60+(int)$t[2];
 $end=fn(DateTimeImmutable $d)=>$d->setTime((int)$t[1],(int)$t[2],0);
 if($a>$b){if($mins>=$a)return $end($now->modify('+1 day'));if($mins<$b)return $end($now);return null;}   // ventana que cruza la medianoche
 return ($mins>=$a&&$mins<$b)?$end($now):null;
}
function tfOfferMinutes(string $classDate,DateTimeImmutable $now):int{return $classDate===$now->format('Y-m-d')?TF_OFFER_MINUTES_SAME_DAY:TF_OFFER_MINUTES_OTHER_DAY;}

function tfOffersEnabled(mysqli $db):bool{return tfNotifySwitch($db,'OFFERS_ENABLED');}
function tfSetting(mysqli $db,string $k):string{return (string)(tfQuery($db,'SELECT v FROM tf_notify_settings WHERE k=?',[$k])[0]['v']??'');}

/** Plazas retenidas por ofertas pendientes. Cuentan como ocupadas en TODAS las consultas y operaciones. */
function tfHeld(mysqli $db,int $schedule,string $date):int{return (int)tfQuery($db,"SELECT COUNT(*) n FROM tf_offers WHERE horario_id=? AND fecha=? AND status='PENDING'",[(string)$schedule,$date])[0]['n'];}
/** Reservas confirmadas + plazas retenidas. */
function tfOccupied(mysqli $db,int $schedule,string $date):int{return (int)tfQuery($db,'SELECT COUNT(*) n FROM inscripciones WHERE horario_id=? AND fecha=?',[(string)$schedule,$date])[0]['n']+tfHeld($db,$schedule,$date);}

/**
 * OFFERS: la espera se resuelve con ofertas. LEGACY: comportamiento anterior (promoción automática).
 * Una sesión con espera heredada (creada antes de OFFERS_SINCE) sigue en LEGACY hasta que esa cola desaparezca; nadie se borra ni se salta.
 * Mientras haya ofertas pendientes la sesión cuenta como OFFERS aunque el interruptor se apague: las ofertas se resuelven antes de reactivar la promoción antigua.
 */
function tfSessionMode(mysqli $db,int $schedule,string $date):string{
 if(tfHeld($db,$schedule,$date)>0)return 'OFFERS';
 if(!tfOffersEnabled($db))return 'LEGACY';
 $since=tfSetting($db,'OFFERS_SINCE');if($since==='')return 'LEGACY';   // sin fecha de activación no hay modo nuevo
 $only=tfSetting($db,'OFFERS_ONLY_HORARIOS');   // ofertas acotadas a ciertos horarios (pruebas): el resto sigue como antes
 if($only!==''&&!in_array((string)$schedule,preg_split('/\D+/',$only,-1,PREG_SPLIT_NO_EMPTY)?:[],true))return 'LEGACY';
 return tfQuery($db,'SELECT id FROM inscripciones_cola WHERE horario_id=? AND fecha=? AND creado_en<? LIMIT 1',[(string)$schedule,$date,$since])?'LEGACY':'OFFERS';
}
/** ¿Puede una ruta antigua promover automáticamente en esta sesión? Solo en modo LEGACY. */
function tfLegacyPromotionAllowed(mysqli $db,int $schedule,string $date):bool{return tfSessionMode($db,$schedule,$date)==='LEGACY';}

/** Nueva espera: en modo OFERTAS exige avisos activados y probados. Comprobado en el servidor para todas las rutas, recepción incluida. */
function tfRequireNoticesForWaitlist(mysqli $db,int $schedule,string $date,string $name,string $phone):void{
 if(tfSessionMode($db,$schedule,$date)!=='OFFERS')return;
 foreach(tfPeopleForReservation($db,$name,$phone) as $p)if(tfPersonHasConfirmedPush($db,$p))return;
 throw new WebError('WAITLIST_REQUIRES_NOTICES',409);
}

function tfOfferAudit(mysqli $db,string $actor,string $action,array $o,array $extra=[]):void{tfNotifyAudit($db,$actor,$action,(int)$o['person_id'],null,['offer'=>(int)$o['id'],'horario_id'=>(int)$o['horario_id'],'fecha'=>$o['fecha']]+$extra);}

/** Retira esa entrada de la espera de esa clase (la persona podrá apuntarse otra vez, al final). */
function tfOfferRemoveEntry(mysqli $db,int $waitId):void{
 tfQuery($db,'DELETE FROM inscripciones_cola WHERE id=?',[(string)$waitId]);
 tfQuery($db,"UPDATE tf_bookings SET estado='CANCELLED',wait_id=NULL,version=version+1 WHERE wait_id=? AND estado='WAITLIST'",[(string)$waitId]);
}
function tfOfferClassState(mysqli $db,array $o):string{   // OK | CANCELLED | STARTED
 if(tfQuery($db,'SELECT id FROM clases_canceladas WHERE horario_id=? AND fecha=?',[(string)$o['horario_id'],$o['fecha']]))return 'CANCELLED';
 $h=tfQuery($db,'SELECT hora FROM horarios WHERE id=?',[(string)$o['horario_id']])[0]??null;
 if(!$h||!preg_match('/^\d{2}:\d{2}-\d{2}:\d{2}$/',$h['hora']))return 'CANCELLED';
 return tfClassStart($o['fecha'],$h['hora'])<=tfNow()?'STARTED':'OK';
}
function tfOfferClose(mysqli $db,int $id,string $status,string $by):void{tfQuery($db,"UPDATE tf_offers SET status=?,resolved_at=NOW(),resolved_by=? WHERE id=? AND status='PENDING'",[$status,substr($by,0,100),(string)$id]);}

/**
 * Caduca u invalida ofertas. Se llama desde el worker (≤5 s) y antes de cualquier operación que mire el aforo.
 * Devuelve las sesiones [horario,fecha] cuya cadena hay que continuar.
 */
function tfOffersSweep(mysqli $db):array{
 $touch=[];$now=tfNow();
 foreach(tfQuery($db,"SELECT * FROM tf_offers WHERE status='PENDING' FOR UPDATE") as $o){
  $state=tfOfferClassState($db,$o);
  if($state==='CANCELLED'){tfOfferClose($db,(int)$o['id'],'CANCELLED','system:class_cancelled');tfOfferAudit($db,'system','OFFER_CANCELLED',$o,['why'=>'class_cancelled']);continue;}   // cadena detenida
  if($state==='STARTED'||$o['expires_at']<=$now->format('Y-m-d H:i:s')){
   tfOfferClose($db,(int)$o['id'],'EXPIRED','system:expired');tfOfferRemoveEntry($db,(int)$o['wait_id']);tfOfferAudit($db,'system','OFFER_EXPIRED',$o);
   $touch[$o['horario_id'].'|'.$o['fecha']]=[(int)$o['horario_id'],$o['fecha']];
  }
 }
 return array_values($touch);
}

/** Persona de una entrada de espera: por el vínculo de Reservas o, si no existe, por coincidencia exacta nombre+teléfono. null si no hay una única. */
function tfQueueEntryPerson(mysqli $db,array $w):?array{
 $b=tfQuery($db,'SELECT id,person_id FROM tf_bookings WHERE wait_id=?',[(string)$w['id']])[0]??null;
 if($b)return ['person'=>(int)$b['person_id'],'booking'=>(int)$b['id']];
 $ph=tfNormPhone((string)$w['telefono']);if($ph==='')return null;$hits=[];
 foreach(tfQuery($db,'SELECT id,nombre FROM tf_people WHERE active=1 AND telefono=?',[$ph]) as $p)if(tfNormName($p['nombre'])===tfNormName((string)$w['nombre']))$hits[]=(int)$p['id'];
 return count($hits)===1?['person'=>$hits[0],'booking'=>null]:null;
}

/**
 * Crea las ofertas que quepan (una por plaza libre, a las primeras entradas por creado_en,id sin oferta). Solo en modo OFERTAS y con el interruptor OFFERS_ENABLED activo.
 * Varias plazas libres generan varias ofertas a la vez sin superar el aforo ni ofrecer dos plazas a la misma entrada.
 */
function tfOffersFill(mysqli $db,int $schedule,string $date):int{
 if(!tfOffersEnabled($db)||tfSessionMode($db,$schedule,$date)!=='OFFERS')return 0;
 $h=tfQuery($db,'SELECT id,limite,hora FROM horarios WHERE id=? FOR UPDATE',[(string)$schedule])[0]??null;if(!$h||(int)$h['limite']<=0)return 0;
 $probe=['horario_id'=>$schedule,'fecha'=>$date];if(tfOfferClassState($db,$probe)!=='OK')return 0;
 $free=(int)$h['limite']-tfOccupied($db,$schedule,$date);if($free<=0)return 0;
 $now=tfNow();$start=tfClassStart($date,$h['hora']);// De madrugada la plaza se RETIENE ya (nadie puede saltarse la cola), pero el aviso y el plazo empiezan al acabar el descanso, salvo que la clase empiece antes de poder ofrecerla.
 $quietEnd=tfQuietEnd($db,$now);$begin=($quietEnd&&$start>$quietEnd->modify('+'.TF_OFFER_MINUTES_SAME_DAY.' minutes'))?$quietEnd:$now;
 $expires=min($begin->modify('+'.tfOfferMinutes($date,$begin).' minutes'),$start);   // si la clase empieza antes, el plazo termina al empezar
 $made=0;
 $rows=tfQuery($db,"SELECT w.* FROM inscripciones_cola w WHERE w.horario_id=? AND w.fecha=? AND NOT EXISTS (SELECT 1 FROM tf_offers o WHERE o.wait_id=w.id AND o.status='PENDING') ORDER BY w.creado_en,w.id LIMIT ".(int)$free." FOR UPDATE",[(string)$schedule,$date]);
 foreach($rows as $w){
  $who=tfQueueEntryPerson($db,$w);
  if(!$who){   // incidencia para recepción; no se confirma nada ni se borra a nadie
   $seen=tfQuery($db,"SELECT id FROM tf_notify_audit WHERE action='OFFER_BLOCKED' AND detail_json LIKE ? LIMIT 1",['%"wait":'.(int)$w['id'].',%']);
   if(!$seen)tfNotifyAudit($db,'system','OFFER_BLOCKED',null,null,['wait'=>(int)$w['id'],'horario_id'=>$schedule,'fecha'=>$date,'why'=>'persona no identificada']);
   continue;
  }
  $token=bin2hex(random_bytes(32));
  tfQuery($db,'INSERT INTO tf_offers(wait_id,booking_id,person_id,horario_id,fecha,token_hash,expires_at) VALUES(?,?,?,?,?,?,?)',[(string)$w['id'],$who['booking']===null?null:(string)$who['booking'],(string)$who['person'],(string)$schedule,$date,hash('sha256',$token),$expires->format('Y-m-d H:i:s')]);
  $offer=(int)$db->insert_id;$ttl=max(1,$expires->getTimestamp()-$now->getTimestamp());
  tfNotifyEmit($db,'OFFER',$who['person'],'OFFER:'.$offer,$ttl,['offer_id'=>$offer,'horario_id'=>$schedule,'fecha'=>$date,'link_token'=>$token],null,$begin->format('Y-m-d H:i:s'));
  $o=['id'=>$offer,'person_id'=>$who['person'],'horario_id'=>$schedule,'fecha'=>$date];tfOfferAudit($db,'system','OFFER_CREATED',$o,['desde'=>$begin->format('H:i'),'expires'=>$expires->format('H:i')]);
  if(!tfQuery($db,"SELECT o.id FROM tf_push_outbox o JOIN tf_notify_events e ON e.id=o.event_id WHERE e.dedupe_key=? LIMIT 1",['OFFER:'.$offer]))   // sin buzón activo: la oferta existe (recepción puede confirmarla a petición) pero se avisa
   tfOfferAudit($db,'system','OFFER_UNDELIVERABLE',$o);
  $made++;
 }
 return $made;
}

/** Un paso completo del worker: caducar → continuar cadenas → ofrecer plazas libres de las sesiones con espera próximas. */
function tfOffersTick(mysqli $db):array{
 $r=['expired'=>0,'created'=>0];
 $touch=tfAtomic($db,fn()=>tfOffersSweep($db));$r['expired']=count($touch);
 if(tfOffersEnabled($db)){
  $now=tfNow();$sessions=[];foreach($touch as $s)$sessions[$s[0].'|'.$s[1]]=$s;
  foreach(tfQuery($db,'SELECT DISTINCT horario_id,fecha FROM inscripciones_cola WHERE fecha BETWEEN ? AND ?',[$now->format('Y-m-d'),$now->modify('+6 days')->format('Y-m-d')]) as $x)$sessions[$x['horario_id'].'|'.$x['fecha']]=[(int)$x['horario_id'],$x['fecha']];
  foreach($sessions as [$h,$d])$r['created']+=tfAtomic($db,fn()=>tfOffersFill($db,$h,$d));
 }
 return $r;
}

/** Consulta de solo lectura (no modifica nada). */
function tfOfferView(mysqli $db,string $token):array{
 tfRequire(preg_match('/^[a-f0-9]{64}$/',$token)===1,'OFFER_NOT_FOUND',404);
 $o=tfQuery($db,'SELECT o.id,o.status,o.expires_at,o.fecha,h.clase,LEFT(h.hora,5) hora,(o.expires_at>NOW()) live FROM tf_offers o JOIN horarios h ON h.id=o.horario_id WHERE o.token_hash=?',[hash('sha256',$token)])[0]??null;
 tfRequire($o,'OFFER_NOT_FOUND',404);
 $status=$o['status']==='PENDING'&&!$o['live']?'EXPIRED':$o['status'];
 return ['clase'=>$o['clase'],'fecha'=>$o['fecha'],'hora'=>$o['hora'],'limite'=>substr($o['expires_at'],11,5),'estado'=>$status];
}

/** Núcleo de la aceptación (token o recepción). Devuelve ['ok'=>bool,'code'=>..]; NO lanza para que los cambios de estado (caducar, cancelar) se confirmen. */
function tfOfferAcceptLocked(mysqli $db,array $o,string $actor):array{
 if($o['status']==='ACCEPTED')return ['ok'=>true,'already'=>true,'status'=>'ACCEPTED'];                // doble pulsación o dos dispositivos
 if($o['status']!=='PENDING')return ['ok'=>false,'code'=>'OFFER_CLOSED','status'=>$o['status']];
 $state=tfOfferClassState($db,$o);
 if($state==='CANCELLED'){tfOfferClose($db,(int)$o['id'],'CANCELLED','system:class_cancelled');tfOfferAudit($db,$actor,'OFFER_CANCELLED',$o);return ['ok'=>false,'code'=>'SESSION_CANCELLED','status'=>'CANCELLED'];}
 if($state==='STARTED'||$o['expires_at']<=tfNow()->format('Y-m-d H:i:s')){
  tfOfferClose($db,(int)$o['id'],'EXPIRED','system:expired');tfOfferRemoveEntry($db,(int)$o['wait_id']);tfOfferAudit($db,$actor,'OFFER_EXPIRED',$o);tfOffersFill($db,(int)$o['horario_id'],$o['fecha']);
  return ['ok'=>false,'code'=>'OFFER_EXPIRED','status'=>'EXPIRED'];
 }
 $w=tfQuery($db,'SELECT * FROM inscripciones_cola WHERE id=? FOR UPDATE',[(string)$o['wait_id']])[0]??null;
 if(!$w){tfOfferClose($db,(int)$o['id'],'CANCELLED','system:entry_removed');tfOfferAudit($db,$actor,'OFFER_CANCELLED',$o,['why'=>'entry_removed']);return ['ok'=>false,'code'=>'OFFER_CLOSED','status'=>'CANCELLED'];}
 $h=tfQuery($db,'SELECT limite FROM horarios WHERE id=? FOR UPDATE',[(string)$o['horario_id']])[0];
 $others=tfOccupied($db,(int)$o['horario_id'],$o['fecha'])-1;                                              // lo ocupado sin contar la plaza retenida para esta oferta
 if((int)$h['limite']>0&&$others>=(int)$h['limite']){tfOfferClose($db,(int)$o['id'],'FAILED','system:no_capacity');tfOfferAudit($db,$actor,'OFFER_FAILED',$o,['why'=>'aforo']);return ['ok'=>false,'code'=>'NO_CAPACITY','status'=>'FAILED'];}
 $dup=tfIdFindInscriptionLocal($db,(int)$o['horario_id'],$o['fecha'],(string)$w['nombre'],(string)$w['telefono']);
 if($dup)$res=(int)$dup;
 else{tfQuery($db,'INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())',[$w['nombre'],$w['telefono'],(string)$o['horario_id'],$o['fecha']]);$res=(int)$db->insert_id;}
 tfQuery($db,'DELETE FROM inscripciones_cola WHERE id=?',[(string)$w['id']]);
 $b=tfQuery($db,'SELECT id FROM tf_bookings WHERE wait_id=? FOR UPDATE',[(string)$w['id']])[0]??null;
 if($b)tfQuery($db,"UPDATE tf_bookings SET estado='RESERVED',reservation_id=?,wait_id=NULL,version=version+1 WHERE id=?",[(string)$res,(string)$b['id']]);
 else tfQuery($db,"INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,reservation_id,wait_id) VALUES(?,?,?,'RESERVED',?,NULL) ON DUPLICATE KEY UPDATE estado='RESERVED',reservation_id=VALUES(reservation_id),wait_id=NULL,version=version+1",[(string)$o['person_id'],(string)$o['horario_id'],$o['fecha'],(string)$res]);
 tfQuery($db,"UPDATE tf_offers SET status='ACCEPTED',resolved_at=NOW(),resolved_by=?,reservation_id=? WHERE id=?",[substr($actor,0,100),(string)$res,(string)$o['id']]);
 tfNotifyEmit($db,'OFFER_ACCEPTED',(int)$o['person_id'],'OFFERACC:'.$o['id'],3600,['offer_id'=>(int)$o['id'],'horario_id'=>(int)$o['horario_id'],'fecha'=>$o['fecha']]);
 tfOfferAudit($db,$actor,'OFFER_ACCEPTED',$o);
 return ['ok'=>true,'already'=>false,'status'=>'ACCEPTED'];
}
/** Misma persona (nombre+teléfono normalizados) ya inscrita en la sesión → id, o null. */
function tfIdFindInscriptionLocal(mysqli $db,int $schedule,string $date,string $name,string $phone):?int{
 foreach(tfQuery($db,'SELECT id,nombre,telefono FROM inscripciones WHERE horario_id=? AND fecha=?',[(string)$schedule,$date]) as $r)
  if(tfNormName($r['nombre'])===tfNormName($name)&&tfNormPhone($r['telefono'])===tfNormPhone($phone)&&tfNormPhone($phone)!=='')return (int)$r['id'];
 return null;
}

function tfOfferAccept(mysqli $db,string $token):array{
 tfRequire(preg_match('/^[a-f0-9]{64}$/',$token)===1,'OFFER_NOT_FOUND',404);
 return tfAtomic($db,function()use($db,$token){
  $o=tfQuery($db,'SELECT * FROM tf_offers WHERE token_hash=? FOR UPDATE',[hash('sha256',$token)])[0]??null;tfRequire($o,'OFFER_NOT_FOUND',404);
  return tfOfferAcceptLocked($db,$o,'offer-link:'.$o['id']);
 });
}
function tfOfferDeclineLocked(mysqli $db,array $o,string $actor):array{
 if($o['status']==='DECLINED')return ['ok'=>true,'already'=>true,'status'=>'DECLINED'];
 if($o['status']!=='PENDING')return ['ok'=>false,'code'=>'OFFER_CLOSED','status'=>$o['status']];
 tfOfferClose($db,(int)$o['id'],'DECLINED',$actor);tfOfferRemoveEntry($db,(int)$o['wait_id']);tfOfferAudit($db,$actor,'OFFER_DECLINED',$o);
 tfOffersFill($db,(int)$o['horario_id'],$o['fecha']);                                                       // ofrece la plaza al siguiente
 return ['ok'=>true,'already'=>false,'status'=>'DECLINED'];
}
function tfOfferDecline(mysqli $db,string $token):array{
 tfRequire(preg_match('/^[a-f0-9]{64}$/',$token)===1,'OFFER_NOT_FOUND',404);
 return tfAtomic($db,function()use($db,$token){
  $o=tfQuery($db,'SELECT * FROM tf_offers WHERE token_hash=? FOR UPDATE',[hash('sha256',$token)])[0]??null;tfRequire($o,'OFFER_NOT_FOUND',404);
  return tfOfferDeclineLocked($db,$o,'offer-link:'.$o['id']);
 });
}
/** Recepción confirma una oferta vigente a petición de la persona: mismos controles de plazo y aforo, con auditoría. */
function tfOfferAcceptByStaff(mysqli $db,int $offerId,string $staff):array{
 return tfAtomic($db,function()use($db,$offerId,$staff){
  $o=tfQuery($db,'SELECT * FROM tf_offers WHERE id=? FOR UPDATE',[(string)$offerId])[0]??null;tfRequire($o,'OFFER_NOT_FOUND',404);
  return tfOfferAcceptLocked($db,$o,'staff:'.$staff);
 });
}
/** Cancelación de clase: invalida las ofertas pendientes y detiene la cadena. */
function tfOffersCancelSession(mysqli $db,int $schedule,string $date,string $by):int{
 $n=0;foreach(tfQuery($db,"SELECT * FROM tf_offers WHERE horario_id=? AND fecha=? AND status='PENDING' FOR UPDATE",[(string)$schedule,$date]) as $o){tfOfferClose($db,(int)$o['id'],'CANCELLED',$by);tfOfferAudit($db,$by,'OFFER_CANCELLED',$o,['why'=>'class_cancelled']);$n++;}
 return $n;
}

/** Promoción heredada (sesión en modo LEGACY): la primera espera ocupa la plaza libre, igual que cuando cancela recepción. */
function tfLegacyPromoteNext(mysqli $db,int $schedule,string $date):void{
 $h=tfQuery($db,'SELECT limite FROM horarios WHERE id=? FOR UPDATE',[(string)$schedule])[0]??null;if(!$h)return;
 if((int)$h['limite']>0&&(int)tfQuery($db,'SELECT COUNT(*) n FROM inscripciones WHERE horario_id=? AND fecha=?',[(string)$schedule,$date])[0]['n']<(int)$h['limite']){
  $w=tfQuery($db,'SELECT id,nombre,telefono FROM inscripciones_cola WHERE horario_id=? AND fecha=? ORDER BY creado_en,id LIMIT 1 FOR UPDATE',[(string)$schedule,$date])[0]??null;
  if($w){tfQuery($db,'INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())',[$w['nombre'],$w['telefono'],(string)$schedule,$date]);tfQuery($db,'DELETE FROM inscripciones_cola WHERE id=?',[(string)$w['id']]);}
 }
 tfAdminSync($db);
}
/** La plaza liberada pasa a la siguiente persona: por oferta (modo OFERTAS) o por la promoción de siempre (modo LEGACY). */
function tfAfterFreed(mysqli $db,int $schedule,string $date):void{if(tfLegacyPromotionAllowed($db,$schedule,$date))tfLegacyPromoteNext($db,$schedule,$date);else tfOffersFill($db,$schedule,$date);}

/**
 * El cliente cancela SU reserva ('r') o sale de SU espera ('w') desde «Mis clases». Idempotente. Comprueba la referencia firmada de este móvil y que la fila sea de esa
 * persona (nombre + teléfono normalizados). No se cancela una clase ya empezada. Devuelve ['ok'=>bool,'estado'=>...,'code'=>...].
 */
function tfClientCancel(mysqli $db,array $person,string $kind,string $ref):array{
 tfRequire(in_array($kind,['r','w'],true),'INVALID_DATA',400);$id=tfClientRefId($kind,$ref);tfRequire($id>0,'ACCESS_DENIED',403);
 return tfAtomic($db,function()use($db,$person,$kind,$id){
  $table=$kind==='r'?'inscripciones':'inscripciones_cola';
  $row=tfQuery($db,"SELECT * FROM $table WHERE id=? FOR UPDATE",[(string)$id])[0]??null;
  if(!$row)return ['ok'=>true,'estado'=>'YA_CANCELADA'];                                                       // doble pulsación o ya hecha por recepción
  tfRequire(tfNormName((string)$row['nombre'])===tfNormName((string)$person['nombre'])&&tfPhoneKey((string)$row['telefono'])===tfPhoneKey((string)$person['telefono']),'ACCESS_DENIED',403);
  $h=tfQuery($db,'SELECT hora FROM horarios WHERE id=?',[(string)$row['horario_id']])[0]??null;
  if(!$h||!preg_match('/^\d{2}:\d{2}-\d{2}:\d{2}$/',$h['hora'])||tfClassStart($row['fecha'],$h['hora'])<=tfNow())return ['ok'=>false,'code'=>'CLASS_STARTED'];
  $actor='person:'.$person['id'];$sched=(int)$row['horario_id'];$date=$row['fecha'];
  if($kind==='r'){
   tfQuery($db,'DELETE FROM inscripciones WHERE id=?',[(string)$id]);
   tfQuery($db,"UPDATE tf_bookings SET estado='CANCELLED',reservation_id=NULL,version=version+1 WHERE reservation_id=?",[(string)$id]);
   tfNotifyAudit($db,$actor,'CLIENT_CANCELLED',(int)$person['id'],null,['horario_id'=>$sched,'fecha'=>$date]);
   tfAfterFreed($db,$sched,$date);return ['ok'=>true,'estado'=>'CANCELADA'];
  }
  $offer=tfQuery($db,"SELECT * FROM tf_offers WHERE wait_id=? AND status='PENDING' FOR UPDATE",[(string)$id])[0]??null;
  if($offer)tfOfferDeclineLocked($db,$offer,$actor);                                                           // rechaza la oferta y la plaza pasa a la siguiente
  else tfOfferRemoveEntry($db,$id);
  tfNotifyAudit($db,$actor,'CLIENT_LEFT_WAITLIST',(int)$person['id'],null,['horario_id'=>$sched,'fecha'=>$date]);
  return ['ok'=>true,'estado'=>'FUERA_DE_LA_ESPERA'];
 });
}
