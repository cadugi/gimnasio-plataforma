<?php
declare(strict_types=1);
// Móvil personal: identificarse, ver estado y olvidar. Autoriza solo las funciones de reservas de esa persona.
// guard.php deja pasar este script: la autorización se resuelve aquí, con la cookie TF_MOVIL.
require_once dirname(__DIR__).'/sso/notify.php';require_once __DIR__.'/conexion.php';
try{
 $method=$_SERVER['REQUEST_METHOD']??'GET';
 if($method==='GET'){
  $d=tfDeviceCurrent($conn);
  if(!$d)tfJson(['success'=>true,'linked'=>false]);
  tfQuery($conn,'UPDATE tf_devices SET last_seen_at=NOW() WHERE id=?',[(string)$d['id']]);
  tfJson(['success'=>true,'linked'=>true,'nombre'=>$d['nombre'],'telefono'=>$d['telefono'],'csrf'=>tfDeviceCsrf()]);
 }
 tfRequire($method==='POST','METHOD_NOT_ALLOWED',405);
 $r=json_decode((string)file_get_contents('php://input',false,null,0,4097),true);tfRequire(is_array($r),'INVALID_DATA',400);
 $action=(string)($r['action']??'');
 if($action==='identificar'){
  tfRequire(($_SERVER['HTTP_X_TF_MODO']??'')!=='compartido','SHARED_SCREEN',403);   // pantalla compartida declarada: no se vincula nada
  tfDeviceCheckWrite(false);
  $res=tfIdentify($conn,(string)($r['nombre']??''),(string)($r['telefono']??''));
  if($res['status']!=='OK')tfJson(['success'=>false,'code'=>'NO_MATCH'],200);   // mismo mensaje para «no existe» y «revisión en recepción»
  $secret=tfAtomic($conn,function()use($conn,$res,$r){
   if($old=tfDeviceCurrent($conn))tfDeviceRevoke($conn,(int)$old['id'],'person:'.$old['person_id']);   // cambiar de persona = nuevo vínculo
   return tfDeviceCreate($conn,$res['person'],(string)($r['plataforma']??'other'));
  });
  $_COOKIE[TF_DEVICE_COOKIE]=$secret;tfDeviceCookie($secret,time()+TF_DEVICE_SECONDS);
  tfJson(['success'=>true,'linked'=>true,'csrf'=>tfDeviceCsrf()]);
 }
 if($action==='olvidar'){
  $d=tfDeviceCurrent($conn);tfRequire($d,'ACCESS_DENIED',403);tfDeviceCheckWrite(true);
  tfAtomic($conn,fn()=>tfDeviceRevoke($conn,(int)$d['id'],'person:'.$d['person_id']));
  tfDeviceCookie('',time()-3600);tfJson(['success'=>true,'linked'=>false]);
 }
 tfJson(['success'=>false,'error'=>'UNKNOWN_ACTION'],400);
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}
catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
