<?php
header('Content-Type: application/json; charset=UTF-8');
require_once 'conexion.php';

$dia = isset($_GET['dia']) ? trim($_GET['dia']) : '';
if ($dia === '') {
    echo json_encode([]);
    $conn->close();
    exit;
}

$stmt = $conn->prepare('SELECT id, clase, hora, limite FROM horarios WHERE dia = ? ORDER BY hora');
$stmt->bind_param('s', $dia);
$stmt->execute();
$res = $stmt->get_result();
$out = [];
while ($r = $res->fetch_assoc()) {
    $out[] = $r;
}
$stmt->close();

echo json_encode($out);
$conn->close();
?>
