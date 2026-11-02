<?php
declare(strict_types=1);
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');
$public=['obtener_horarios_clase.php','comprobar_disponibilidad.php','obtener_limite_inscripciones.php','inscribir_cliente.php'];
$script=basename($_SERVER['SCRIPT_FILENAME']??'');
if(!in_array($script,$public,true) && empty($_SERVER['REMOTE_USER'])){
    http_response_code(401);header('Content-Type: application/json');echo '{"success":false,"error":"AUTH_REQUIRED"}';exit;
}
if(($_SERVER['REQUEST_METHOD']??'')==='POST'){
    $origin=$_SERVER['HTTP_ORIGIN']??'';
    if($origin!==getenv('TF_PUBLIC_ORIGIN') || ($_SERVER['HTTP_X_TOPFITNESS_REQUEST']??'')!=='1'){
        http_response_code(403);header('Content-Type: application/json');echo '{"success":false,"error":"REQUEST_NOT_ALLOWED"}';exit;
    }
}
