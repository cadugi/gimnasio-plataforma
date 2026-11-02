<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=UTF-8');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
ini_set('display_errors', 0);
error_reporting(E_ALL);

require_once __DIR__ . '/conexion.php';

if (!isset($conn) || !($conn instanceof mysqli)) {
    http_response_code(500);
    echo json_encode([
        'ok' => false,
        'error' => 'DB_CONNECTION_ERROR',
        'data' => []
    ]);
    exit;
}

$conn->set_charset('utf8mb4');

try {
    $clase = isset($_GET['clase']) ? trim((string)$_GET['clase']) : '';
    
    if (empty($clase)) {
        $sql = "SELECT id, clase, dia, hora, limite 
                FROM horarios 
                ORDER BY FIELD(dia, 'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'), 
                         hora ASC";
        $result = $conn->query($sql);
    } else {
        // Búsqueda case-insensitive
        $claseBusqueda = '%' . $clase . '%';
        $stmt = $conn->prepare(
            "SELECT id, clase, dia, hora, limite 
             FROM horarios 
             WHERE UPPER(REPLACE(clase, ' ', '')) LIKE UPPER(REPLACE(?, ' ', ''))
             ORDER BY FIELD(dia, 'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'), 
                      hora ASC"
        );
        
        if (!$stmt) {
            throw new Exception("Prepare failed: " . 'SERVICE_ERROR');
        }
        
        $stmt->bind_param('s', $claseBusqueda);
        
        if (!$stmt->execute()) {
            throw new Exception("Execute failed: " . 'SERVICE_ERROR');
        }
        
        $result = $stmt->get_result();
    }

    $data = [];
    while ($row = $result->fetch_assoc()) {
        $data[] = [
            'id' => (int)$row['id'],
            'clase' => $row['clase'],
            'dia' => $row['dia'],
            'hora' => $row['hora'],
            'limite' => is_null($row['limite']) ? null : (int)$row['limite']
        ];
    }

    if (isset($stmt)) {
        $stmt->close();
    }

    // Clases canceladas de hoy en adelante (para no ofrecerlas)
    $canceladas = [];
    $resC = $conn->query("SELECT horario_id, DATE_FORMAT(fecha, '%Y-%m-%d') AS fecha FROM clases_canceladas WHERE fecha >= CURDATE() AND fecha <= DATE_ADD(CURDATE(), INTERVAL 14 DAY)");
    while ($c = $resC->fetch_assoc()) {
        $canceladas[] = ['horario_id' => (int)$c['horario_id'], 'fecha' => $c['fecha']];
    }

    echo json_encode([
        'ok' => true,
        'data' => $data,
        'canceladas' => $canceladas
    ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode([
        'ok' => false,
        'error' => 'SERVICE_ERROR',
        'data' => []
    ], JSON_UNESCAPED_UNICODE);
}