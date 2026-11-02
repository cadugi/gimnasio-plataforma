<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/sso/waitlist.php';
try{
    tfRequire(!empty($_SERVER['REMOTE_USER']),'AUTH_REQUIRED',401);
    tfRequire(($_SERVER['REQUEST_METHOD']??'')==='POST','METHOD_NOT_ALLOWED',405);
    tfRequire(($_SERVER['HTTP_ORIGIN']??'')===getenv('TF_PUBLIC_ORIGIN')&&($_SERVER['HTTP_X_TOPFITNESS_REQUEST']??'')==='1','REQUEST_NOT_ALLOWED',403);
    $id=filter_var($_POST['id']??null,FILTER_VALIDATE_INT,['options'=>['min_range'=>1]]);
    $schedule=filter_var($_POST['horario_id']??null,FILTER_VALIDATE_INT,['options'=>['min_range'=>1]]);
    tfRequire($id!==false&&$schedule!==false,'INVALID_SELECTION');
    $date=$_POST['fecha']??'';tfRequire(is_string($date),'INVALID_SELECTION');
    require_once __DIR__.'/conexion.php';
    tfJson(tfRemoveWaitlist($conn,$id,$schedule,$date,(string)$_SERVER['REMOTE_USER']));
}catch(WebError $e){
    $messages=['AUTH_REQUIRED'=>'Inicia sesión para gestionar la lista de espera.','METHOD_NOT_ALLOWED'=>'Esta acción requiere confirmación.','REQUEST_NOT_ALLOWED'=>'La petición no es válida. Recarga la página.','INVALID_SELECTION'=>'Selecciona una persona de una clase y fecha válidas.','WAITLIST_CHANGED'=>'Esa persona ya no está en esta lista de espera. La lista ha cambiado; vuelve a comprobarla.'];
    tfJson(['success'=>false,'code'=>$e->getMessage(),'error'=>$messages[$e->getMessage()]??'No se pudo quitar a esta persona de la lista de espera.'],$e->status);
}catch(Throwable $e){tfJson(['success'=>false,'error'=>'No se pudo quitar a esta persona. Inténtalo de nuevo.'],503);}
