<?php
declare(strict_types=1);
// «Mis clases»: reservas y esperas (con posición) de la persona de este móvil. Solo lectura; nunca devuelve teléfonos ni datos de otras personas.
require_once dirname(__DIR__).'/sso/offers.php';require_once __DIR__.'/conexion.php';
try{
 $d=tfDeviceCurrent($conn);tfRequire($d,'ACCESS_DENIED',403);
 $p=tfQuery($conn,'SELECT id,nombre,telefono FROM tf_people WHERE id=?',[(string)$d['person_id']])[0];
 if(($_SERVER['REQUEST_METHOD']??'GET')==='POST'){   // cancelar reserva / salir de la espera: escritura explícita con CSRF y referencia firmada de este móvil
  tfRequire(($_SERVER['HTTP_X_TF_MODO']??'')!=='compartido','SHARED_SCREEN',403);tfDeviceCheckWrite(true);tfRateLimit($conn,'misclases-w:'.$d['id'],30,600);
  $r=json_decode((string)file_get_contents('php://input',false,null,0,2049),true);tfRequire(is_array($r),'INVALID_DATA',400);
  $kind=match((string)($r['action']??'')){'cancelar'=>'r','salir'=>'w',default=>throw new WebError('UNKNOWN_ACTION',400)};
  $out=tfClientCancel($conn,$p,$kind,(string)($r['ref']??''));tfJson(['success'=>$out['ok'],'estado'=>$out['estado']??null,'code'=>$out['code']??null],$out['ok']?200:409);
 }
 tfRequire(($_SERVER['REQUEST_METHOD']??'GET')==='GET','METHOD_NOT_ALLOWED',405);
 tfRateLimit($conn,'misclases:'.$d['id'],120,600);
 tfJson(['success'=>true,'nombre'=>$p['nombre'],'avisos'=>tfAvisosStatus($conn,$d)['state']]+tfMyClasses($conn,$p));
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}
catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
