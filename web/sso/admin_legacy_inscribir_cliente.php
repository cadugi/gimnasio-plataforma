<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=UTF-8');
require_once dirname(__DIR__).'/public/conexion.php';require_once __DIR__.'/public_phone.php';require_once __DIR__.'/booking_identity.php';require_once __DIR__.'/public_booking_rules.php';require_once __DIR__.'/offers.php';
$admin=!empty($_SERVER['REMOTE_USER']);
function tfPublicError(int $status,string $code,string $message):never{global $conn;try{$conn->rollback();}catch(Throwable){}http_response_code($status);echo json_encode(['success'=>false,'code'=>$code,'error'=>$message]);exit;}
try {
    $name=trim((string)($_POST['nombre']??''));$phone=trim((string)($_POST['telefono']??''));
    $schedule=(int)($_POST['horario_id']??0);$date=trim((string)($_POST['fecha']??''));
    if(!$name||!$phone||$schedule<=0||strlen($name)>100||strlen($phone)>24||!preg_match('/^\d{4}-\d{2}-\d{2}$/',$date)){
        http_response_code(400);echo '{"success":false,"error":"PARAMS"}';exit;
    }
    // El público necesita un móvil español real; recepción conserva su validación de contacto flexible.
    $clean=tfPublicPhone($phone);
    if(!$admin&&$clean===null)tfPublicError(400,'PHONE_INVALID','Escribe tu número de móvil completo: 9 cifras que empiecen por 6, 7 u 8.');
    if($clean!==null)$phone=$clean;
    if(strlen($phone)>15){http_response_code(400);echo '{"success":false,"error":"PARAMS"}';exit;}
    $stmt=$conn->prepare('SELECT id FROM clases_canceladas WHERE horario_id=? AND fecha=?');$stmt->bind_param('is',$schedule,$date);$stmt->execute();
    if($stmt->get_result()->fetch_assoc()&&!$admin){echo '{"success":false,"error":"CLASE_CANCELADA"}';exit;}
    $stmt->close();
    $conn->begin_transaction();$conn->query('SELECT id FROM tf_mutex WHERE id=1 FOR UPDATE');
    $stmt=$conn->prepare('SELECT limite,dia,hora FROM horarios WHERE id=? FOR UPDATE');$stmt->bind_param('i',$schedule);$stmt->execute();
    $h=$stmt->get_result()->fetch_assoc();if(!$h)throw new RuntimeException();
    $limit=(int)$h['limite'];
    if(!$admin)tfPublicValidateSchedule($h,$date);
    // El aforo también se respeta en recepción. La antigua confirmación de exceso
    // no autoriza a saltárselo: una clase llena continúa por la lista de espera.
    if($admin){
        $dup=tfIdFindInscription($conn,$schedule,$date,$name,$phone);
        if($dup){$conn->rollback();http_response_code(409);echo json_encode(['success'=>false,'error'=>'YA_INSCRITO','id'=>(int)$dup['id']]);exit;}
    }

    $existing=tfIdFindInscription($conn,$schedule,$date,$name,$phone);     // misma persona = teléfono normalizado + nombre normalizado
    $stmt=$conn->prepare('SELECT COUNT(*) AS n FROM inscripciones WHERE horario_id=? AND fecha=?');$stmt->bind_param('is',$schedule,$date);$stmt->execute();$count=(int)$stmt->get_result()->fetch_assoc()['n'];$held=tfHeld($conn,$schedule,$date);   // las plazas retenidas por ofertas cuentan como ocupadas
    $overQuota=fn()=>!$admin&&tfPublicWeekCount($conn,$phone,$date)>=TF_PUBLIC_WEEKLY_LIMIT;
    $quotaMessage='Has alcanzado las '.TF_PUBLIC_WEEKLY_LIMIT.' clases de esta semana con este teléfono. Las reservas y la lista de espera cuentan; si cancelas una, se libera.';
    if($existing||$limit<=0||$count+$held<$limit){
        if(!$existing){
            if($overQuota())tfPublicError(409,'WEEKLY_PERSON_LIMIT',$quotaMessage);
            $stmt=$conn->prepare('INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())');
            $stmt->bind_param('ssis',$name,$phone,$schedule,$date);$stmt->execute();$id=$conn->insert_id;$count++;
            if($admin){tfIdAudit($conn,'ADMIN_RESERVATION_ADDED',['horario_id'=>$schedule,'fecha'=>$date,'inscripcion'=>$id]);$notified=tfNotifyReceptionBooking($conn,$name,$phone,$schedule,$date,(int)$id);}
        }else $id=(int)$existing['id'];
        $conn->commit();echo json_encode(['success'=>true,'status'=>'INSCRIBED','avisos'=>isset($notified)?$notified>0:null,'id'=>$id,'already'=>(bool)$existing,'inscritos'=>$count,'limite'=>$limit,'disponibles'=>$limit<=0?null:max(0,$limit-$count-$held)]);exit;
    }
    // La misma persona en esta sesión conserva su turno. Compartir teléfono no une a dos personas distintas.
    $waiting=tfIdFindWaiting($conn,$schedule,$date,$phone);
    if($waiting&&!tfIdSame($name,$phone,(string)$waiting['nombre'],(string)$waiting['telefono']))
        tfPublicError(409,'WAITLIST_IDENTITY_CONFLICT','Este teléfono ya tiene otra persona en la lista de espera. Comprueba el nombre y el teléfono.');
    if(!$waiting){
        if($overQuota())tfPublicError(409,'WEEKLY_PERSON_LIMIT',$quotaMessage);
        try{tfRequireNoticesForWaitlist($conn,$schedule,$date,$name,$phone);}catch(WebError $e){tfPublicError(409,'WAITLIST_REQUIRES_NOTICES','Para apuntarte a la lista de espera necesitas activar los avisos en tu móvil y comprobar el aviso de prueba.');}
        $stmt=$conn->prepare('INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())');
        $stmt->bind_param('ssis',$name,$phone,$schedule,$date);$stmt->execute();$waitId=$conn->insert_id;
        if($admin)tfIdAudit($conn,'ADMIN_WAITLIST_ADDED',['horario_id'=>$schedule,'fecha'=>$date,'espera'=>$waitId]);
    }else $waitId=(int)$waiting['id'];
    $stmt=$conn->prepare('SELECT COUNT(*) AS n FROM inscripciones_cola WHERE horario_id=? AND fecha=? AND (creado_en,id)<=(SELECT creado_en,id FROM inscripciones_cola WHERE id=?)');
    $stmt->bind_param('isi',$schedule,$date,$waitId);$stmt->execute();$position=(int)$stmt->get_result()->fetch_assoc()['n'];
    $conn->commit();echo json_encode(['success'=>true,'status'=>'WAITLIST','already'=>(bool)$waiting,'posicion'=>$position]);
}catch(InvalidArgumentException $e){tfPublicError(400,'INVALID_SESSION',$e->getMessage());}catch(Throwable $e){$conn->rollback();http_response_code(500);echo '{"success":false,"error":"SERVICE_ERROR"}';}
