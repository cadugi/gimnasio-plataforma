<?php
header('Content-Type: application/json');
require_once "conexion.php";
require_once dirname(__DIR__) . "/sso/offers.php";
$conn->set_charset("utf8mb4");
$fecha = $_GET['fecha'] ?? '';
if (!$fecha) { echo json_encode([]); exit; }
$stmt = $conn->prepare('SELECT horario_id, COUNT(*) as inscritos FROM inscripciones WHERE fecha=? GROUP BY horario_id');
$stmt->bind_param('s',$fecha);
$stmt->execute();
$res = $stmt->get_result();
$out = [];
while($r = $res->fetch_assoc()) { $out[$r['horario_id']] = intval($r['inscritos']); }
// Las plazas retenidas por ofertas pendientes cuentan como ocupadas.
$st2 = $conn->prepare("SELECT horario_id, COUNT(*) n FROM tf_offers WHERE fecha=? AND status='PENDING' GROUP BY horario_id"); $st2->bind_param('s',$fecha); $st2->execute(); $r2 = $st2->get_result();
while($x = $r2->fetch_assoc()) { $out[$x['horario_id']] = ($out[$x['horario_id']] ?? 0) + intval($x['n']); }
echo json_encode($out);
$conn->close();
?>