<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=UTF-8');
header('X-Content-Type-Options: nosniff');

require_once __DIR__ . '/conexion.php';
if (!($conn instanceof mysqli)) { http_response_code(500); echo json_encode(['ok'=>false,'error'=>'DB_CONN_VAR']); exit; }
$conn->set_charset('utf8mb4');

$fecha = isset($_GET['fecha']) ? trim((string)$_GET['fecha']) : '';
$horario_id = isset($_GET['horario_id']) ? (int)$_GET['horario_id'] : 0;
if ($fecha === '' || $horario_id <= 0) { echo json_encode(['ok'=>true,'data'=>[]]); exit; }

try {
  $stmt = $conn->prepare('SELECT id, nombre, telefono, DATE_FORMAT(creado_en, "%Y-%m-%d %H:%i:%s") as creado_en FROM inscripciones_cola WHERE horario_id=? AND fecha=? ORDER BY creado_en ASC, id ASC');
  $stmt->bind_param('is', $horario_id, $fecha);
  $stmt->execute();
  $res = $stmt->get_result();
  $out = [];
  while ($row = $res->fetch_assoc()) { $out[] = $row; }
  $stmt->close();
  echo json_encode(['ok'=>true,'data'=>$out], JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['ok'=>false,'error'=>'QUERY','msg'=>'SERVICE_ERROR']);
}
