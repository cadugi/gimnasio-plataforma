<?php
header('Content-Type: application/json; charset=UTF-8');
require_once 'conexion.php';

$horario_id = isset($_GET['horario_id']) ? intval($_GET['horario_id']) : 0;
if ($horario_id <= 0) {
    echo json_encode(['limite' => 0]);
    $conn->close();
    exit;
}

$stmt = $conn->prepare('SELECT limite FROM horarios WHERE id = ?');
$stmt->bind_param('i', $horario_id);
$stmt->execute();
$stmt->bind_result($limite);
$stmt->fetch();
$stmt->close();

$limite_max = is_null($limite) ? 0 : (int) $limite;
echo json_encode(['limite' => $limite_max]);
$conn->close();
?>
