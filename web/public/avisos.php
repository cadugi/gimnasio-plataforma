<?php
declare(strict_types=1);
// Avisos del móvil: estado, activar/desactivar, prueba y consulta de avisos propios. Solo con móvil identificado.
require_once dirname(__DIR__).'/sso/avisos.php';require_once __DIR__.'/conexion.php';
try{
 $d=tfDeviceCurrent($conn);tfRequire($d,'ACCESS_DENIED',403);
 if(($_SERVER['REQUEST_METHOD']??'GET')==='GET'){
  $c=tfNotifyConfig();
  tfJson(['success'=>true,'avisos'=>tfAvisosStatus($conn,$d),'vapid_public'=>(string)($c['vapid_public']??''),'envio_activo'=>tfSendingEnabledFor($conn,(int)$d['person_id']),'mis_avisos'=>tfMyNotices($conn,(int)$d['person_id'])]);
 }
 tfRequire(($_SERVER['REQUEST_METHOD']??'')==='POST','METHOD_NOT_ALLOWED',405);tfRequire(($_SERVER['HTTP_X_TF_MODO']??'')!=='compartido','SHARED_SCREEN',403);tfDeviceCheckWrite(true);
 $r=json_decode((string)file_get_contents('php://input',false,null,0,4097),true);tfRequire(is_array($r),'INVALID_DATA',400);
 $out=match((string)($r['action']??'')){
  'suscribir'=>tfSubscribe($conn,$d,$r),'desactivar'=>tfUnsubscribe($conn,$d),'probar'=>tfRequestTest($conn,$d),'confirmar_prueba'=>tfConfirmTest($conn,$d),
  default=>throw new WebError('UNKNOWN_ACTION',400)};
 tfJson(['success'=>true,'avisos'=>$out]);
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}
catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
