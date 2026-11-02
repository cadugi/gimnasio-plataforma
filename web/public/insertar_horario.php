<?php
require __DIR__ . '/conexion.php';
header('Content-Type: application/json; charset=utf-8');

try {
    if (!isset($_POST["clase"], $_POST["dia"], $_POST["hora"])) {
        throw new Exception("Faltan parámetros obligatorios");
    }

    $clase = $_POST["clase"];
    $dia = $_POST["dia"];
    $hora = $_POST["hora"];
    $limite = isset($_POST["limite"]) && $_POST["limite"] !== '' ? intval($_POST["limite"]) : NULL;

    $stmt = $conn->prepare("INSERT INTO horarios (clase, dia, hora, limite) VALUES (?, ?, ?, ?)");
    $stmt->bind_param("sssi", $clase, $dia, $hora, $limite);
    if ($stmt->execute()) {
        echo json_encode(["success" => true, "id" => $stmt->insert_id]);
    } else {
        throw new Exception("Error SQL: " . 'SERVICE_ERROR');
    }
    $stmt->close();
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "success" => false,
        "error" => 'SERVICE_ERROR'
    ]);
}
