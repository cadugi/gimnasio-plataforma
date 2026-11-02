<?php
declare(strict_types=1);
mysqli_report(MYSQLI_REPORT_ERROR|MYSQLI_REPORT_STRICT);
date_default_timezone_set('Europe/Madrid');
try {
    $conn=new mysqli(getenv('TF_REAL_DB_HOST'),getenv('TF_REAL_DB_USER'),getenv('TF_REAL_DB_PASSWORD'),getenv('TF_REAL_DB_NAME'),3306);
    $conn->set_charset('utf8mb4');
    $conn->query("SET time_zone = '".date('P')."'");
} catch(Throwable $e){http_response_code(503);header('Content-Type: application/json');echo '{"success":false,"error":"SERVICE_UNAVAILABLE"}';exit;}
