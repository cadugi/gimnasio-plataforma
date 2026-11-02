<?php
declare(strict_types=1);
// Recepción: dispositivos asociados, revocación y asociación expresa de socios que solo existen en Innux.
// guard.php exige sesión de recepción (REMOTE_USER) y Origin + X-TopFitness-Request en las escrituras.
require_once dirname(__DIR__).'/sso/offers.php';require_once __DIR__.'/conexion.php';
try{
 $actor=(string)($_SERVER['REMOTE_USER']??'');tfRequire($actor!=='','AUTH_REQUIRED',401);
 if(($_SERVER['REQUEST_METHOD']??'GET')==='GET'){
  $beat=fn(string $k)=>tfQuery($conn,'SELECT TIMESTAMPDIFF(SECOND,updated_at,NOW()) s FROM tf_notify_settings WHERE k=?',[$k])[0]['s']??null;
  tfJson(['success'=>true,
   'salud'=>['envio'=>tfNotifySwitch($conn,'PUSH_SEND_ENABLED'),'ofertas'=>tfOffersEnabled($conn),'remitente_seg'=>$beat('HB_PUSH')===null?null:(int)$beat('HB_PUSH'),'worker_ofertas_seg'=>$beat('HB_OFFERS')===null?null:(int)$beat('HB_OFFERS')],
   'devices'=>tfQuery($conn,"SELECT d.id,p.nombre,CONCAT('***',RIGHT(p.telefono,3)) telefono,d.platform,d.created_at,d.last_seen_at,(SELECT COUNT(*) FROM tf_push_subscriptions s WHERE s.device_id=d.id AND s.status='ACTIVE' AND s.test_confirmed_at IS NOT NULL) avisos FROM tf_devices d JOIN tf_people p ON p.id=d.person_id WHERE d.revoked_at IS NULL ORDER BY d.last_seen_at DESC LIMIT 200"),
   'ofertas'=>tfQuery($conn,"SELECT o.id,p.nombre,CONCAT('***',RIGHT(p.telefono,3)) telefono,h.clase,o.fecha,LEFT(h.hora,5) hora,SUBSTRING(o.expires_at,12,5) limite,TIMESTAMPDIFF(SECOND,NOW(),o.expires_at) segundos,(SELECT COUNT(*) FROM tf_push_subscriptions s JOIN tf_devices d ON d.id=s.device_id WHERE d.person_id=o.person_id AND d.revoked_at IS NULL AND s.status='ACTIVE') avisos FROM tf_offers o JOIN tf_people p ON p.id=o.person_id JOIN horarios h ON h.id=o.horario_id WHERE o.status='PENDING' ORDER BY o.expires_at LIMIT 100"),
   'incidencias'=>tfQuery($conn,"SELECT a.id,a.action,a.created_at,p.nombre,a.detail_json FROM tf_notify_audit a LEFT JOIN tf_people p ON p.id=a.person_id WHERE a.action IN ('PUSH_FAILED','OFFER_UNDELIVERABLE','OFFER_BLOCKED','IDENTIFY_REVIEW','IDENTIFY_SOURCE_DOWN','OFFER_FAILED') AND a.created_at>NOW() - INTERVAL 7 DAY ORDER BY a.id DESC LIMIT 60")]);
 }
 $r=json_decode((string)file_get_contents('php://input',false,null,0,4097),true);tfRequire(is_array($r),'INVALID_DATA',400);
 $action=(string)($r['action']??'');
 if($action==='revocar'){$id=(int)($r['device_id']??0);tfRequire($id>0,'INVALID_DATA',400);tfAtomic($conn,fn()=>tfDeviceRevoke($conn,$id,$actor));tfJson(['success'=>true]);}
 if($action==='confirmar_oferta'){   // a petición de la persona, con los mismos controles de plazo y aforo; queda auditado
  $id=(int)($r['offer_id']??0);tfRequire($id>0,'INVALID_DATA',400);$out=tfOfferAcceptByStaff($conn,$id,$actor);
  tfJson(['success'=>$out['ok'],'estado'=>$out['status'],'code'=>$out['code']??null,'ya'=>$out['already']??false],$out['ok']?200:409);
 }
 if($action==='asociar_innux'){
  // Recepción elige la ficha de Innux en su buscador; aquí solo se registra la asociación. No se crea ni modifica nada en Innux.
  $ref=(string)($r['innux_reference']??'');$name=trim((string)($r['nombre']??''));$phone=tfNormPhone((string)($r['telefono']??''));
  tfRequire(preg_match('/^INNUX:[1-9][0-9]{0,19}$/',$ref)===1&&mb_strlen($name)>=3&&mb_strlen($name)<=100&&$phone!=='','INVALID_DATA',400);
  $id=tfAtomic($conn,function()use($conn,$ref,$name,$phone,$actor){$id=tfPersonForRef($conn,$ref,$name,$phone);tfNotifyAudit($conn,$actor,'INNUX_LINKED',$id,null,['ref'=>$ref,'phone'=>tfMaskPhone($phone)]);return $id;});
  tfJson(['success'=>true,'person_id'=>$id]);
 }
 tfJson(['success'=>false,'error'=>'UNKNOWN_ACTION'],400);
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}
catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
