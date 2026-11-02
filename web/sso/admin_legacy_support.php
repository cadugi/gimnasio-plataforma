<?php
require_once __DIR__.'/library.php';
function tfAdminSync(mysqli $db):void{
 tfQuery($db,"UPDATE tf_bookings b LEFT JOIN inscripciones r ON r.id=b.reservation_id SET b.estado='CANCELLED',b.reservation_id=NULL,b.version=b.version+1 WHERE b.estado='RESERVED' AND b.reservation_id IS NOT NULL AND r.id IS NULL");
 $rows=tfQuery($db,"SELECT b.id,b.horario_id,b.fecha,p.nombre,p.telefono FROM tf_bookings b JOIN tf_people p ON p.id=b.person_id LEFT JOIN inscripciones_cola w ON w.id=b.wait_id WHERE b.estado='WAITLIST' AND b.wait_id IS NOT NULL AND w.id IS NULL");
 foreach($rows as $b){$found=tfQuery($db,'SELECT r.id FROM inscripciones r LEFT JOIN tf_bookings other ON other.reservation_id=r.id WHERE r.horario_id=? AND r.fecha=? AND r.nombre=? AND r.telefono=? AND other.id IS NULL',[$b['horario_id'],$b['fecha'],$b['nombre'],$b['telefono']]);
 if(count($found)===1)tfQuery($db,"UPDATE tf_bookings SET estado='RESERVED',reservation_id=?,wait_id=NULL,version=version+1 WHERE id=?",[$found[0]['id'],$b['id']]);
 elseif(!$found)tfQuery($db,"UPDATE tf_bookings SET estado='CANCELLED',wait_id=NULL,version=version+1 WHERE id=?",[$b['id']]);}
}
