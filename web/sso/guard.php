<?php
declare(strict_types=1);
header('X-Content-Type-Options: nosniff');header('Cache-Control: no-store, private');header('Referrer-Policy: no-referrer');
if(is_file('/opt/topfitness-web/READ_ONLY')&&($_SERVER['REQUEST_METHOD']??'')==='POST'){http_response_code(503);exit;}
require_once __DIR__.'/sso/library.php';
ini_set('display_errors','0');
try{
$script=basename($_SERVER['SCRIPT_FILENAME']??'');
if(in_array($script,['portal.php','entrar.php','service.php'],true))return; // Each is explicitly authorised in its own controller.
$admin=!empty($_SERVER['REMOTE_USER']);
// QA_TOTAL: cuenta de Reservas nominal, revocable y con auditoría de cada petición PHP.
if(($_SERVER['REMOTE_USER']??'')==='qa_total'){
 require_once __DIR__.'/public/conexion.php';
 $qa=tfQuery($conn,"SELECT username FROM tf_staff_accounts WHERE username='qa_total' AND active=1 AND role='admin'");
 tfRequire((bool)$qa,'AUTH_REQUIRED',401);
 tfQuery($conn,'INSERT INTO tf_staff_audit(actor,action,script,method) VALUES(?,?,?,?)',
     ['qa_total','QA_REQUEST',$script,substr($_SERVER['REQUEST_METHOD']??'GET',0,10)]);
}
if(!$admin){
 require_once __DIR__.'/public/conexion.php';
 if(!tfSession($conn))tfJson(['success'=>false,'error'=>'AUTH_REQUIRED'],401);
 $public=['obtener_horarios_clase.php','comprobar_disponibilidad.php','obtener_limite_inscripciones.php','inscribir_cliente.php','identidad.php','mis_reservas.php'];
 if(!in_array($script,$public,true))tfJson(['success'=>false,'error'=>'ACCESS_DENIED'],403);
}
if(($_SERVER['REQUEST_METHOD']??'')==='POST'){
 if(!$admin)tfCheckCsrf();
 elseif(($_SERVER['HTTP_ORIGIN']??'')!==getenv('TF_PUBLIC_ORIGIN')||($_SERVER['HTTP_X_TOPFITNESS_REQUEST']??'')!=='1')tfJson(['success'=>false,'error'=>'REQUEST_NOT_ALLOWED'],403);
}
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}
catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
