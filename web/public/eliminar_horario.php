<?php
header("Content-Type: application/json; charset=UTF-8");
require_once "conexion.php";

try {
    if (!isset($_POST["id"])) {
        throw new Exception("ID no recibido");
    }

    $id = (int) $_POST["id"];
    $sql = "DELETE FROM horarios WHERE id=$id";

    if ($conn->query($sql)) {
        echo json_encode(["success" => true]);
    } else {
        throw new Exception("Error SQL: " . 'SERVICE_ERROR');
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "success" => false,
        "error" => 'SERVICE_ERROR'
    ]);
}
?>
