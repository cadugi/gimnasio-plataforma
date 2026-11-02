<?php
header('Content-Type: application/json; charset=UTF-8');
require_once "conexion.php"; // $conn
$conn->set_charset("utf8mb4");

$fecha = isset($_GET['fecha']) ? trim($_GET['fecha']) : '';
$horario_id = isset($_GET['horario_id']) ? intval($_GET['horario_id']) : 0;
if ($fecha === '' || $horario_id <= 0) { echo json_encode([]); exit; }

$stmt = $conn->prepare('SELECT id, nombre, telefono, creado_en FROM inscripciones WHERE horario_id = ? AND fecha = ? ORDER BY creado_en ASC, id ASC');
$stmt->bind_param('is', $horario_id, $fecha);
$stmt->execute();
$res = $stmt->get_result();
$out = [];
while ($r = $res->fetch_assoc()) { $out[] = $r; }
echo json_encode($out);
?>