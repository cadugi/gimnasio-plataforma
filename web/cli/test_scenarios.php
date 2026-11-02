<?php
declare(strict_types=1);
// Escenarios de prueba con móviles propios. SOLO toca una clase de prueba (dia='PRUEBA', no aparece en el horario público) y personas
// de la lista PUSH_ALLOW_PERSONS. Nunca crea ni modifica reservas de socios reales. Uso: test_scenarios.php COMANDO [ID_PERSONA]
if(PHP_SAPI!=='cli')exit(1);
require_once dirname(__DIR__).'/sso/offers.php';
mysqli_report(MYSQLI_REPORT_ERROR|MYSQLI_REPORT_STRICT);date_default_timezone_set('Europe/Madrid');
$conn=new mysqli(getenv('TF_REAL_DB_HOST'),getenv('TF_REAL_DB_USER'),getenv('TF_REAL_DB_PASSWORD'),getenv('TF_REAL_DB_NAME'),3306);$conn->set_charset('utf8mb4');$conn->query("SET time_zone = '".date('P')."'");
$cmd=$argv[1]??'ayuda';$pid=(int)($argv[2]??0);
function out(string $s):void{echo $s,"\n";}
function set_(string $k,string $v):void{global $conn;tfQuery($conn,'UPDATE tf_notify_settings SET v=? WHERE k=?',[$v,$k]);}
function allowed(int $pid):array{global $conn;$allow=preg_split('/\D+/',tfSetting($conn,'PUSH_ALLOW_PERSONS'),-1,PREG_SPLIT_NO_EMPTY)?:[];
 if(!in_array((string)$pid,$allow,true)){out("La persona $pid no está en la lista de prueba (PUSH_ALLOW_PERSONS). Ejecuta: scripts/push_deploy.sh switch test-persons \"$pid\" --yes");exit(1);}
 return tfQuery($conn,'SELECT id,nombre,telefono FROM tf_people WHERE id=? AND active=1',[(string)$pid])[0]??(function(){out('Persona no encontrada');exit(1);})();}
function horario():array{global $conn;$id=tfSetting($conn,'TEST_HORARIO');if($id!==''){$h=tfQuery($conn,"SELECT * FROM horarios WHERE id=? AND dia='PRUEBA'",[$id])[0]??null;if($h)return $h;}
 $s=tfNow()->modify('+3 hours');tfQuery($conn,"INSERT INTO horarios(clase,dia,hora,limite) VALUES('PRUEBA AVISOS','PRUEBA',?,1)",[$s->format('H:i').'-'.$s->modify('+1 hour')->format('H:i')]);$id=(string)$conn->insert_id;set_('TEST_HORARIO',$id);
 return tfQuery($conn,'SELECT * FROM horarios WHERE id=?',[$id])[0];}
function ponerHora(array $h,DateTimeImmutable $start):array{global $conn;tfQuery($conn,'UPDATE horarios SET hora=? WHERE id=?',[$start->format('H:i').'-'.$start->modify('+1 hour')->format('H:i'),(string)$h['id']]);return ['fecha'=>$start->format('Y-m-d'),'start'=>$start];}
function inscribir(array $h,array $p,string $fecha):int{global $conn;tfQuery($conn,'DELETE FROM inscripciones WHERE horario_id=?',[(string)$h['id']]);
 tfQuery($conn,'INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW() - INTERVAL 1 DAY)',[$p['nombre'],$p['telefono'],(string)$h['id'],$fecha]);return (int)$conn->insert_id;}
function minuto(DateTimeImmutable $d):DateTimeImmutable{return $d->setTime((int)$d->format('H'),(int)$d->format('i'),0);}
function audit(string $what,int $pid):void{global $conn;tfNotifyAudit($conn,'test-scenarios','TEST_SCENARIO',$pid,null,['escenario'=>$what]);}

switch($cmd){
 case 'personas':
  foreach(tfQuery($conn,"SELECT p.id,p.nombre,RIGHT(p.telefono,3) t,d.platform,(SELECT COUNT(*) FROM tf_push_subscriptions s WHERE s.device_id=d.id AND s.status='ACTIVE' AND s.test_confirmed_at IS NOT NULL) ok FROM tf_people p JOIN tf_devices d ON d.person_id=p.id AND d.revoked_at IS NULL ORDER BY d.id DESC LIMIT 30") as $r)
   out("id={$r['id']}  {$r['nombre']} (***{$r['t']})  {$r['platform']}  avisos ".($r['ok']?'activados y probados':'SIN activar/probar'));
  out('Lista de prueba actual: '.(tfSetting($conn,'PUSH_ALLOW_PERSONS')?:'(vacía)'));break;
 case 'recordatorio':
  $p=allowed($pid);$h=horario();$t=ponerHora($h,minuto(tfNow()->modify('+2 hours')));$ins=inscribir($h,$p,$t['fecha']);
  tfAtomic($conn,fn()=>tfNotifyEmit($conn,'REMINDER',$pid,'TESTREM:'.bin2hex(random_bytes(5)),3600,['booking_id'=>$ins,'horario_id'=>(int)$h['id'],'fecha'=>$t['fecha']],null,$t['start']->modify('-2 hours')->format('Y-m-d H:i:s')));
  audit('recordatorio',$pid);out('Recordatorio enviado en unos segundos: «PRUEBA AVISOS» a las '.$t['start']->format('H:i').'. Debe llegar con la web cerrada.');break;
 case 'recepcion':
  $p=allowed($pid);$h=horario();$t=ponerHora($h,minuto(tfNow()->modify('+3 hours')));$ins=inscribir($h,$p,$t['fecha']);
  $n=tfAtomic($conn,fn()=>tfNotifyReceptionBooking($conn,$p['nombre'],$p['telefono'],(int)$h['id'],$t['fecha'],$ins));audit('recepcion',$pid);out("Aviso de reserva en recepción para $n persona(s).");break;
 case 'cambio':
  $p=allowed($pid);$h=horario();$ins=tfQuery($conn,'SELECT fecha FROM inscripciones WHERE horario_id=? LIMIT 1',[(string)$h['id']])[0]??null;if(!$ins){out('Primero ejecuta: recepcion '.$pid);exit(1);}
  $start=minuto(tfClassStart($ins['fecha'],$h['hora'])->modify('+1 hour'));ponerHora($h,$start);
  $n=tfAtomic($conn,fn()=>tfNotifyScheduleChanged($conn,(int)$h['id'],'PRUEBA',$start->format('H:i').'-'.$start->modify('+1 hour')->format('H:i')));audit('cambio',$pid);out("Aviso de cambio de horario a $n persona(s) (ahora a las ".$start->format('H:i').').');break;
 case 'cancelar':
  $p=allowed($pid);$h=horario();$ins=tfQuery($conn,'SELECT fecha FROM inscripciones WHERE horario_id=? LIMIT 1',[(string)$h['id']])[0]??null;if(!$ins){out('Primero ejecuta: recepcion '.$pid);exit(1);}
  tfQuery($conn,'INSERT IGNORE INTO clases_canceladas(horario_id,fecha,motivo,creado_por) VALUES(?,?,?,?)',[(string)$h['id'],$ins['fecha'],'prueba','test-scenarios']);
  $n=tfAtomic($conn,function()use($conn,$h,$ins){tfOffersCancelSession($conn,(int)$h['id'],$ins['fecha'],'test');return tfNotifyClassCancelled($conn,(int)$h['id'],$ins['fecha']);});audit('cancelar',$pid);out("Aviso de clase cancelada a $n persona(s).");break;
 case 'oferta':   // prepara: clase llena (1 plaza ocupada) y la persona en espera; ofertas acotadas SOLO a la clase de prueba. Opcional: «manana» pone la clase mañana (plazo de 1 hora)
  $p=allowed($pid);$h=horario();$t=ponerHora($h,minuto(tfNow()->modify(($argv[3]??'')==='manana'?'+1 day':'+3 hours')));tfQuery($conn,'DELETE FROM clases_canceladas WHERE horario_id=?',[(string)$h['id']]);
  foreach(tfQuery($conn,'SELECT id FROM inscripciones_cola WHERE horario_id=?',[(string)$h['id']]) as $w)tfQuery($conn,'UPDATE tf_bookings SET wait_id=NULL,estado=\'CANCELLED\' WHERE wait_id=?',[$w['id']]);
  tfQuery($conn,'DELETE FROM tf_offers WHERE horario_id=?',[(string)$h['id']]);tfQuery($conn,'DELETE FROM inscripciones_cola WHERE horario_id=?',[(string)$h['id']]);tfQuery($conn,'DELETE FROM inscripciones WHERE horario_id=?',[(string)$h['id']]);
  set_('OFFERS_ONLY_HORARIOS',(string)$h['id']);set_('OFFERS_SINCE',tfNow()->modify('-1 minute')->format('Y-m-d H:i:s'));set_('OFFERS_ENABLED','1');
  tfQuery($conn,"INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES('Ocupante Prueba','600000001',?,?,NOW() - INTERVAL 1 DAY)",[(string)$h['id'],$t['fecha']]);
  tfQuery($conn,'INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())',[$p['nombre'],$p['telefono'],(string)$h['id'],$t['fecha']]);$w=(int)$conn->insert_id;
  tfQuery($conn,"INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,wait_id) VALUES(?,?,?,'WAITLIST',?) ON DUPLICATE KEY UPDATE estado='WAITLIST',wait_id=VALUES(wait_id),reservation_id=NULL",[(string)$pid,(string)$h['id'],$t['fecha'],(string)$w]);
  audit('oferta-preparar',$pid);out("Preparado: la clase de prueba está llena y {$p['nombre']} está en la espera. Ahora ejecuta: liberar");break;
 case 'liberar':   // simula que alguien cancela: se libera la plaza y el worker crea la oferta
  $h=horario();tfQuery($conn,"DELETE FROM inscripciones WHERE horario_id=? AND nombre='Ocupante Prueba'",[(string)$h['id']]);$r=tfOffersTick($conn);$o=tfQuery($conn,"SELECT TIMESTAMPDIFF(MINUTE,NOW(),expires_at) m FROM tf_offers WHERE horario_id=? AND status='PENDING' ORDER BY id DESC LIMIT 1",[(string)$h['id']])[0]??null;out('Plaza liberada. Ofertas creadas ahora: '.$r['created'].'. El aviso llega en unos segundos'.($o?'; tienes unos '.((int)$o['m']+1).' minutos (10 si la clase es hoy, 60 si es otro día).':'.'));break;
 case 'estado':
  $h=horario();out("Clase de prueba id={$h['id']} ({$h['clase']}, hora {$h['hora']})");
  foreach(tfQuery($conn,'SELECT id,status,expires_at,resolved_by FROM tf_offers WHERE horario_id=? ORDER BY id',[(string)$h['id']]) as $o)out("  oferta {$o['id']}: {$o['status']} (hasta {$o['expires_at']}) {$o['resolved_by']}");
  out('  reservas en la clase: '.tfQuery($conn,'SELECT COUNT(*) n FROM inscripciones WHERE horario_id=?',[(string)$h['id']])[0]['n'].'  esperando: '.tfQuery($conn,'SELECT COUNT(*) n FROM inscripciones_cola WHERE horario_id=?',[(string)$h['id']])[0]['n']);
  foreach(tfQuery($conn,"SELECT e.kind,o.status,o.http_status,o.last_error,e.created_at FROM tf_notify_events e LEFT JOIN tf_push_outbox o ON o.event_id=e.id ORDER BY e.id DESC LIMIT 8") as $e)out("  aviso {$e['kind']} {$e['created_at']}: ".($e['status']??'sin envío').($e['http_status']?" (HTTP {$e['http_status']})":'').($e['last_error']?" {$e['last_error']}":''));break;
 case 'limpiar':
  $id=tfSetting($conn,'TEST_HORARIO');
  if($id!==''&&tfQuery($conn,"SELECT id FROM horarios WHERE id=? AND dia='PRUEBA'",[$id])){
   foreach(tfQuery($conn,'SELECT id FROM tf_notify_events WHERE horario_id=?',[$id]) as $e)tfQuery($conn,'DELETE FROM tf_push_outbox WHERE event_id=?',[$e['id']]);
   tfQuery($conn,'DELETE FROM tf_notify_events WHERE horario_id=?',[$id]);tfQuery($conn,'DELETE FROM tf_offers WHERE horario_id=?',[$id]);
   foreach(tfQuery($conn,'SELECT id FROM inscripciones_cola WHERE horario_id=?',[$id]) as $w)tfQuery($conn,"UPDATE tf_bookings SET wait_id=NULL,estado='CANCELLED' WHERE wait_id=?",[$w['id']]);
   tfQuery($conn,'DELETE FROM tf_bookings WHERE horario_id=?',[$id]);tfQuery($conn,'DELETE FROM inscripciones_cola WHERE horario_id=?',[$id]);tfQuery($conn,'DELETE FROM inscripciones WHERE horario_id=?',[$id]);
   tfQuery($conn,'DELETE FROM clases_canceladas WHERE horario_id=?',[$id]);tfQuery($conn,"DELETE FROM horarios WHERE id=? AND dia='PRUEBA'",[$id]);}
  set_('TEST_HORARIO','');set_('OFFERS_ENABLED','0');set_('OFFERS_ONLY_HORARIOS','');set_('OFFERS_SINCE','');out('Limpio: clase de prueba borrada y ofertas apagadas. (La lista de prueba de personas no se ha tocado.)');break;
 default: out("Comandos: personas | recordatorio ID | recepcion ID | cambio ID | cancelar ID | oferta ID [manana] | liberar | estado | limpiar");
}
