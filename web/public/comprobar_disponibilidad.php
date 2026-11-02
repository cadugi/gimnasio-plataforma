<?php
// comprobar_disponibilidad.php — versión corregida
declare(strict_types=1);
header('Content-Type: application/json; charset=UTF-8');
header('X-Content-Type-Options: nosniff');

require_once __DIR__ . '/conexion.php'; // $conn
require_once dirname(__DIR__) . '/sso/offers.php';
if (!($conn instanceof mysqli)) {
    http_response_code(500);
    echo json_encode(['success'=>false,'error'=>'DB_CONN_VAR']);
    exit;
}
$conn->set_charset('utf8mb4');

$horario_id = isset($_GET['horario_id']) ? (int)$_GET['horario_id'] : 0;
$fecha = isset($_GET['fecha']) ? trim((string)$_GET['fecha']) : '';

if ($horario_id <= 0 || $fecha === '') {
    echo json_encode(['success'=>false,'error'=>'PARAMS']);
    exit;
}

try {
    // Capacidad máxima del horario
    $limite_max = 0;
    $stmt = $conn->prepare('SELECT limite FROM horarios WHERE id=?');
    $stmt->bind_param('i',$horario_id);
    $stmt->execute();
    $stmt->bind_result($lim);
    if ($stmt->fetch()) { $limite_max = (int)$lim; }
    $stmt->close();

    // Inscritos actuales para esa fecha
    $inscritos = 0;
    $stmt = $conn->prepare('SELECT COUNT(*) FROM inscripciones WHERE horario_id=? AND fecha=?');
    $stmt->bind_param('is',$horario_id,$fecha);
    $stmt->execute();
    $stmt->bind_result($ins);
    if ($stmt->fetch()) { $inscritos = (int)$ins; }
    $stmt->close();

    $retenidas = tfHeld($conn, $horario_id, $fecha); // plazas retenidas por ofertas pendientes
    $disponibles = max(0, $limite_max - $inscritos - $retenidas);
    // contar cola
    $stmt2 = $conn->prepare('SELECT COUNT(*) FROM inscripciones_cola WHERE horario_id=? AND fecha=?');
    $stmt2->bind_param('is', $horario_id, $fecha);
    $stmt2->execute();
    $stmt2->bind_result($en_cola);
    $stmt2->fetch();
    $stmt2->close();

    // Clase cancelada ese día (p. ej. no viene el profesor)
    $stmt3 = $conn->prepare('SELECT id FROM clases_canceladas WHERE horario_id=? AND fecha=?');
    $stmt3->bind_param('is', $horario_id, $fecha);
    $stmt3->execute();
    $cancelada = (bool)$stmt3->get_result()->fetch_assoc();
    $stmt3->close();

    echo json_encode([
        'cancelada' => $cancelada,
        'success' => ($inscritos + $retenidas < $limite_max && !$cancelada),
        'disponibles' => $disponibles,
        'limite' => $disponibles, // compatibilidad
        'limite_max' => $limite_max,
        'inscritos' => $inscritos,
        'retenidas' => $retenidas,
        'en_cola' => intval($en_cola)
    ], JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['success'=>false,'error'=>'QUERY','msg'=>'SERVICE_ERROR']);
}
