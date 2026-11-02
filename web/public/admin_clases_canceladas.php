<?php
declare(strict_types=1);
// Solo administración: lista las clases canceladas desde una fecha, con cuántas personas siguen apuntadas.
header('Content-Type: application/json; charset=UTF-8');
if (empty($_SERVER['REMOTE_USER'])) { http_response_code(401); echo '{"ok":false,"error":"AUTH_REQUIRED"}'; exit; }
require_once __DIR__ . '/conexion.php';
try {
    $desde = isset($_GET['desde']) ? trim((string)$_GET['desde']) : date('Y-m-d');
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $desde)) { http_response_code(400); echo '{"ok":false,"error":"PARAMS"}'; exit; }
    $stmt = $conn->prepare("SELECT c.horario_id, DATE_FORMAT(c.fecha,'%Y-%m-%d') AS fecha, c.motivo,
        (SELECT COUNT(*) FROM inscripciones i WHERE i.horario_id=c.horario_id AND i.fecha=DATE_FORMAT(c.fecha,'%Y-%m-%d')) AS inscritos,
        (SELECT COUNT(*) FROM inscripciones_cola w WHERE w.horario_id=c.horario_id AND w.fecha=DATE_FORMAT(c.fecha,'%Y-%m-%d')) AS en_cola
        FROM clases_canceladas c WHERE c.fecha >= ? ORDER BY c.fecha, c.horario_id");
    $stmt->bind_param('s', $desde);
    $stmt->execute();
    $out = [];
    foreach ($stmt->get_result() as $r) {
        $out[] = ['horario_id' => (int)$r['horario_id'], 'fecha' => $r['fecha'], 'motivo' => $r['motivo'], 'inscritos' => (int)$r['inscritos'], 'en_cola' => (int)$r['en_cola']];
    }
    echo json_encode(['ok' => true, 'data' => $out], JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) { http_response_code(500); echo '{"ok":false,"error":"SERVICE_ERROR"}'; }
