<?php
declare(strict_types=1);
require_once __DIR__.'/library.php';
/** Quita exactamente una espera. Nunca elimina una inscripción ni promueve personas. */
function tfRemoveWaitlist(mysqli $db,int $id,int $schedule,string $date,string $actor):array{
    tfRequire(trim($actor)!=='','AUTH_REQUIRED',401);
    tfRequire($id>0&&$schedule>0,'INVALID_SELECTION');
    $d=DateTimeImmutable::createFromFormat('!Y-m-d',$date);
    tfRequire($d&&$d->format('Y-m-d')===$date,'INVALID_SELECTION');
    return tfAtomic($db,function()use($db,$id,$schedule,$date,$actor){
        $row=tfQuery($db,'SELECT id FROM inscripciones_cola WHERE id=? AND horario_id=? AND fecha=? FOR UPDATE',[$id,$schedule,$date])[0]??null;
        tfRequire($row,'WAITLIST_CHANGED',409);
        $booking=tfQuery($db,'SELECT id,person_id,horario_id,fecha,estado FROM tf_bookings WHERE wait_id=? FOR UPDATE',[$id])[0]??null;
        if($booking){
            tfRequire($booking['estado']==='WAITLIST'&&(int)$booking['horario_id']===$schedule&&$booking['fecha']===$date,'WAITLIST_CHANGED',409);
            tfQuery($db,"UPDATE tf_bookings SET estado='CANCELLED',wait_id=NULL,version=version+1 WHERE id=? AND estado='WAITLIST'",[$booking['id']]);
        }
        $st=$db->prepare('DELETE FROM inscripciones_cola WHERE id=? AND horario_id=? AND fecha=?');
        $st->bind_param('iis',$id,$schedule,$date);$st->execute();$removed=$st->affected_rows;$st->close();
        tfRequire($removed===1,'WAITLIST_CHANGED',409);
        // La auditoría forma parte de la misma transacción: si falla, no se borra la espera.
        tfQuery($db,'INSERT INTO tf_identity_audit(actor,action,person_id,detail_json) VALUES(?,?,?,?)',[
            substr($actor,0,100),'ADMIN_WAITLIST_REMOVED',$booking?(int)$booking['person_id']:0,
            json_encode(['espera'=>$id,'horario_id'=>$schedule,'fecha'=>$date,'booking_id'=>$booking['id']??null],JSON_THROW_ON_ERROR)
        ]);
        return ['success'=>true,'removed_id'=>$id];
    });
}
