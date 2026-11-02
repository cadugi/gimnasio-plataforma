<?php
header("Content-Type: application/json; charset=UTF-8");
require_once "conexion.php";

try {
    $sql = "SELECT id, clase, dia, hora, limite FROM horarios";
    $result = $conn->query($sql);

    if (!$result) {
        throw new Exception("Error SQL: " . 'SERVICE_ERROR');
    }

    $horarios = [];
    while ($row = $result->fetch_assoc()) {
        $horarios[] = $row;
    }

    echo json_encode($horarios);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "success" => false,
        "error" => 'SERVICE_ERROR'
    ]);
}
?>
