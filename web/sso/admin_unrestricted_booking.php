<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=UTF-8');
require_once dirname(__DIR__).'/public/conexion.php';require_once __DIR__.'/booking_identity.php';require_once __DIR__.'/offers.php';
try {
    $name=trim((string)($_POST['nombre']??''));$phone=trim((string)($_POST['telefono']??''));
    $schedule=(int)($_POST['horario_id']??0);$date=trim((string)($_POST['fecha']??''));
    if(!$name||!$phone||$schedule<=0||strlen($name)>100||strlen($phone)>15||!preg_match('/^\d{4}-\d{2}-\d{2}$/',$date)){
        http_response_code(400);echo '{"success":false,"error":"PARAMS"}';exit;
    }
    $conn->begin_transaction();$conn->query('SELECT id FROM tf_mutex WHERE id=1 FOR UPDATE');
    $stmt=$conn->prepare('SELECT limite FROM horarios WHERE id=? FOR UPDATE');$stmt->bind_param('i',$schedule);$stmt->execute();
    $h=$stmt->get_result()->fetch_assoc();if(!$h)throw new RuntimeException();
    $limit=(int)$h['limite'];
    $existing=tfIdFindInscription($conn,$schedule,$date,$name,$phone);
    $stmt=$conn->prepare('SELECT COUNT(*) AS n FROM inscripciones WHERE horario_id=? AND fecha=?');$stmt->bind_param('is',$schedule,$date);$stmt->execute();$count=(int)$stmt->get_result()->fetch_assoc()['n'];
    $held=tfHeld($conn,$schedule,$date);
    if($existing||$limit<=0||$count+$held<$limit){
        if(!$existing){
            $stmt=$conn->prepare('INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())');
            $stmt->bind_param('ssis',$name,$phone,$schedule,$date);$stmt->execute();$id=$conn->insert_id;$count++;
        }else $id=(int)$existing['id'];
        $conn->commit();echo json_encode(['success'=>true,'status'=>'INSCRIBED','id'=>$id,'inscritos'=>$count,'limite'=>$limit,'disponibles'=>$limit<=0?null:max(0,$limit-$count-$held)]);exit;
    }
    $stmt=$conn->prepare('SELECT id,fecha FROM inscripciones_cola WHERE horario_id=? AND telefono=? LIMIT 1');
    $stmt->bind_param('is',$schedule,$phone);$stmt->execute();$waiting=$stmt->get_result()->fetch_assoc();
    if($waiting && $waiting['fecha']!==$date){
        $conn->rollback();echo '{"success":false,"error":"WAITLIST_OTHER_DATE"}';exit;
    }
    if(!$waiting){
        try{tfRequireNoticesForWaitlist($conn,$schedule,$date,$name,$phone);}catch(WebError $e){$conn->rollback();http_response_code(409);echo '{"success":false,"error":"WAITLIST_REQUIRES_NOTICES"}';exit;}
        $stmt=$conn->prepare('INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())');
        $stmt->bind_param('ssis',$name,$phone,$schedule,$date);$stmt->execute();$waitId=$conn->insert_id;
    }else $waitId=(int)$waiting['id'];
    $stmt=$conn->prepare('SELECT COUNT(*) AS n FROM inscripciones_cola WHERE horario_id=? AND fecha=? AND (creado_en,id)<=(SELECT creado_en,id FROM inscripciones_cola WHERE id=?)');
    $stmt->bind_param('isi',$schedule,$date,$waitId);$stmt->execute();$position=(int)$stmt->get_result()->fetch_assoc()['n'];
    $conn->commit();echo json_encode(['success'=>true,'status'=>'WAITLIST','posicion'=>$position]);
}catch(Throwable $e){$conn->rollback();http_response_code(500);echo '{"success":false,"error":"SERVICE_ERROR"}';}
