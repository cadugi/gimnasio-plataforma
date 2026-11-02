<?php
declare(strict_types=1);
// Oferta de plaza con enlace opaco. Consultar (GET) NO modifica nada; aceptar y rechazar son escrituras explícitas (POST).
// El token lo guarda la web en el fragmento de la dirección (no viaja a ningún registro) y vale solo para esa oferta.
require_once dirname(__DIR__).'/sso/offers.php';require_once __DIR__.'/conexion.php';
try{
 if(($_SERVER['REQUEST_METHOD']??'GET')==='GET'){
  tfRateLimit($conn,'offer-view:'.tfClientKey(),60,600);
  tfJson(['success'=>true]+tfOfferView($conn,(string)($_SERVER['HTTP_X_OFFER_TOKEN']??'')));
 }
 tfRequire(($_SERVER['REQUEST_METHOD']??'')==='POST','METHOD_NOT_ALLOWED',405);
 tfRequire(($_SERVER['HTTP_ORIGIN']??'')===getenv('TF_PUBLIC_ORIGIN')&&($_SERVER['HTTP_X_TOPFITNESS_REQUEST']??'')==='1','REQUEST_NOT_ALLOWED',403);
 tfRateLimit($conn,'offer-act:'.tfClientKey(),20,600);
 $r=json_decode((string)file_get_contents('php://input',false,null,0,2049),true);tfRequire(is_array($r),'INVALID_DATA',400);$token=(string)($r['token']??'');
 $out=match((string)($r['action']??'')){'aceptar'=>tfOfferAccept($conn,$token),'rechazar'=>tfOfferDecline($conn,$token),default=>throw new WebError('UNKNOWN_ACTION',400)};
 tfJson(['success'=>$out['ok'],'estado'=>$out['status'],'ya'=>$out['already']??false,'code'=>$out['code']??null],$out['ok']?200:409);
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}
catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
