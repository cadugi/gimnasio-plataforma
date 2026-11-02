<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
ini_set('display_errors', 0);
error_reporting(E_ALL);
set_error_handler(function($s,$m,$f,$l){
  http_response_code(500);
  echo json_encode(['success'=>false,'error'=>'PHP','message'=>$m,'file'=>$f,'line'=>$l]); exit;
});
set_exception_handler(function($e){
  http_response_code(500);
  echo json_encode(['success'=>false,'error'=>'EXCEPTION','message'=>'SERVICE_ERROR']); exit;
});

require_once dirname(__DIR__) . '/public/conexion.php';
require_once __DIR__ . '/offers.php';
if (!isset($conn) || !$conn instanceof mysqli) { echo json_encode(['success'=>false,'error'=>'NO_CONN']); exit; }


$id = isset($_POST['id']) ? (int)$_POST['id'] : 0;
if ($id<=0){ echo json_encode(['success'=>false,'error'=>'ID inválido']); exit; }

$conn->begin_transaction();$conn->query('SELECT id FROM tf_mutex WHERE id=1 FOR UPDATE');

$stmt = $conn->prepare('SELECT id, horario_id, fecha FROM inscripciones WHERE id=? FOR UPDATE');
$stmt->bind_param('i',$id); $stmt->execute(); $res=$stmt->get_result(); $row=$res->fetch_assoc(); $stmt->close();
if(!$row){ $conn->rollback(); echo json_encode(['success'=>false,'error'=>'No existe']); exit; }
$horario_id=(int)$row['horario_id']; $fecha=$row['fecha'];

$stmt=$conn->prepare('DELETE FROM inscripciones WHERE id=?');
$stmt->bind_param('i',$id);
if(!$stmt->execute()){ $err='SERVICE_ERROR'; $stmt->close(); $conn->rollback(); echo json_encode(['success'=>false,'error'=>"DELETE_FAIL: $err"]); exit; }
$stmt->close();

$stmt=$conn->prepare('SELECT limite FROM horarios WHERE id=? FOR UPDATE');
$stmt->bind_param('i',$horario_id); $stmt->execute(); $stmt->bind_result($limite); $stmt->fetch(); $stmt->close();

$promoted=null;
if($limite!==null){
  $stmt=$conn->prepare('SELECT COUNT(*) FROM inscripciones WHERE horario_id=? AND fecha=?');
  $stmt->bind_param('is',$horario_id,$fecha); $stmt->execute(); $stmt->bind_result($ocupadas); $stmt->fetch(); $stmt->close();

  if((int)$ocupadas < (int)$limite && tfLegacyPromotionAllowed($conn,(int)$horario_id,(string)$fecha)){   // en modo OFERTAS la plaza la ofrece el servicio de ofertas
    $stmt=$conn->prepare('SELECT id,nombre,telefono FROM inscripciones_cola WHERE horario_id=? AND fecha=? ORDER BY creado_en ASC, id ASC LIMIT 1 FOR UPDATE');
    $stmt->bind_param('is',$horario_id,$fecha); $stmt->execute(); $res=$stmt->get_result(); $wait=$res->fetch_assoc(); $stmt->close();
    if($wait){
      $stmt=$conn->prepare('INSERT INTO inscripciones (nombre,telefono,horario_id,fecha) VALUES (?,?,?,?)');
      $stmt->bind_param('ssis',$wait['nombre'],$wait['telefono'],$horario_id,$fecha);
      if(!$stmt->execute()){ $err='SERVICE_ERROR'; $stmt->close(); $conn->rollback(); echo json_encode(['success'=>false,'error'=>"PROMOTE_INSERT_FAIL: $err"]); exit; }
      $newid=$conn->insert_id; $stmt->close();

      $stmt=$conn->prepare('DELETE FROM inscripciones_cola WHERE id=?');
      $stmt->bind_param('i',$wait['id']);
      if(!$stmt->execute()){ $err='SERVICE_ERROR'; $stmt->close(); $conn->rollback(); echo json_encode(['success'=>false,'error'=>"PROMOTE_DEL_WAIT_FAIL: $err"]); exit; }
      $stmt->close();

      $promoted=['id_nueva'=>$newid,'nombre'=>$wait['nombre'],'telefono'=>$wait['telefono']];
    }
  }
}

tfAdminSync($conn);$conn->commit();
echo json_encode(['success'=>true,'promoted'=>$promoted], JSON_UNESCAPED_UNICODE);
