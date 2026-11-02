<?php
declare(strict_types=1);
// Solo administración: cancela (o reactiva) una clase concreta en un día concreto.
// No borra el horario: solo deja de poder reservarse ese día.
header('Content-Type: application/json; charset=UTF-8');
if (empty($_SERVER['REMOTE_USER'])) { http_response_code(401); echo '{"success":false,"error":"AUTH_REQUIRED"}'; exit; }
require_once __DIR__ . '/conexion.php';
require_once dirname(__DIR__) . '/sso/offers.php';
try {
    $accion = (string)($_POST['accion'] ?? 'cancelar');
    $horario = (int)($_POST['horario_id'] ?? 0);
    $fecha = trim((string)($_POST['fecha'] ?? ''));
    $motivo = trim((string)($_POST['motivo'] ?? ''));
    $d = DateTimeImmutable::createFromFormat('!Y-m-d', $fecha);
    if ($horario <= 0 || !$d || $d->format('Y-m-d') !== $fecha || !in_array($accion, ['cancelar', 'reactivar'], true) || mb_strlen($motivo) > 200) {
        http_response_code(400); echo '{"success":false,"error":"PARAMS"}'; exit;
    }
    $stmt = $conn->prepare('SELECT dia FROM horarios WHERE id=?');
    $stmt->bind_param('i', $horario); $stmt->execute();
    $h = $stmt->get_result()->fetch_assoc(); $stmt->close();
    if (!$h) { http_response_code(404); echo '{"success":false,"error":"SCHEDULE_NOT_FOUND"}'; exit; }
    $dias = ['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
    if ($h['dia'] !== $dias[(int)$d->format('w')]) { echo '{"success":false,"error":"WRONG_WEEKDAY"}'; exit; }

    if ($accion === 'cancelar') {
        $por = substr((string)$_SERVER['REMOTE_USER'], 0, 80);
        $stmt = $conn->prepare('INSERT INTO clases_canceladas(horario_id,fecha,motivo,creado_por) VALUES(?,?,?,?) ON DUPLICATE KEY UPDATE motivo=VALUES(motivo), creado_por=VALUES(creado_por)');
        $m = $motivo === '' ? null : $motivo;
        $stmt->bind_param('isss', $horario, $fecha, $m, $por);
    } else {
        $stmt = $conn->prepare('DELETE FROM clases_canceladas WHERE horario_id=? AND fecha=?');
        $stmt->bind_param('is', $horario, $fecha);
    }
    $stmt->execute(); $stmt->close();
    if ($accion === 'cancelar') { tfAtomic($conn, function () use ($conn, $horario, $fecha, $por) { tfOffersCancelSession($conn, $horario, $fecha, 'staff:' . $por); tfNotifyClassCancelled($conn, $horario, $fecha); }); }   // invalida las ofertas y detiene la cadena
    $stmt = $conn->prepare('SELECT (SELECT COUNT(*) FROM inscripciones WHERE horario_id=? AND fecha=?) AS inscritos, (SELECT COUNT(*) FROM inscripciones_cola WHERE horario_id=? AND fecha=?) AS en_cola');
    $stmt->bind_param('isis', $horario, $fecha, $horario, $fecha); $stmt->execute();
    $n = $stmt->get_result()->fetch_assoc();
    echo json_encode(['success' => true, 'estado' => $accion === 'cancelar' ? 'cancelada' : 'activa', 'inscritos' => (int)$n['inscritos'], 'en_cola' => (int)$n['en_cola']]);
} catch (Throwable $e) { http_response_code(500); echo '{"success":false,"error":"SERVICE_ERROR"}'; }
