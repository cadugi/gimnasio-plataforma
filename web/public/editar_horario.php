<?php
header("Content-Type: application/json; charset=UTF-8");
require_once "conexion.php";
require_once dirname(__DIR__) . "/sso/offers.php";

try {
    if (!isset($_POST["id"], $_POST["clase"], $_POST["dia"], $_POST["hora"])) {
        throw new Exception("Faltan parámetros obligatorios");
    }

    $id = intval($_POST["id"]);
    $clase = $_POST["clase"];
    $dia = $_POST["dia"];
    $hora = $_POST["hora"];
    $limite = isset($_POST["limite"]) && $_POST["limite"] !== '' ? intval($_POST["limite"]) : NULL;

    // El cambio y los avisos a quienes tienen reservas futuras van en la misma transacción.
    tfAtomic($conn, function () use ($conn, $id, $clase, $dia, $hora, $limite) {
        $old = tfQuery($conn, 'SELECT dia, hora FROM horarios WHERE id=? FOR UPDATE', [(string)$id])[0] ?? null;
        $stmt = $conn->prepare("UPDATE horarios SET clase = ?, dia = ?, hora = ?, limite = ? WHERE id = ?");
        $stmt->bind_param("sssii", $clase, $dia, $hora, $limite, $id);
        $stmt->execute();
        $stmt->close();
        if ($old && ($old['dia'] !== $dia || $old['hora'] !== $hora)) tfNotifyScheduleChanged($conn, $id, $dia, $hora);
    });
    echo json_encode(["success" => true]);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "success" => false,
        "error" => 'SERVICE_ERROR'
    ]);
}
?>