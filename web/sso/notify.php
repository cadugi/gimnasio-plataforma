<?php
declare(strict_types=1);
// Identificación de móviles y avisos. La autorización de un móvil vale solo para las reservas de SU persona:
// nunca concede acceso a contratos, pagos ni administración. Aquí no hay datos personales en claro fuera de tf_people.
require_once __DIR__.'/library.php';

const TF_DEVICE_COOKIE='TF_MOVIL';
const TF_DEVICE_SECONDS=31536000;

function tfNotifyConfig():array{static $c=null;if($c!==null)return $c;$f=getenv('TF_NOTIFY_CONFIG')?:'/etc/topfitness-web/notify.json';$j=is_file($f)?json_decode((string)file_get_contents($f),true):null;return $c=is_array($j)?$j:[];}
function tfNotifyAudit(mysqli $db,string $actor,string $action,?int $person,?int $device,array $detail=[]):void{tfQuery($db,'INSERT INTO tf_notify_audit(actor,action,person_id,device_id,detail_json) VALUES(?,?,?,?,?)',[substr($actor,0,100),$action,$person===null?null:(string)$person,$device===null?null:(string)$device,json_encode($detail,JSON_UNESCAPED_UNICODE)]);}
function tfNotifySwitch(mysqli $db,string $key):bool{return (tfQuery($db,'SELECT v FROM tf_notify_settings WHERE k=?',[$key])[0]['v']??'0')==='1';}
function tfMaskPhone(string $phone):string{return '***'.substr(preg_replace('/\D/','',$phone),-3);}

/** Teléfono español de 9 cifras (6-9) tras quitar espacios, guiones, +34 y 0034; '' si no es válido. */
function tfNormPhone(string $raw):string{$d=preg_replace('/\D/','',$raw)??'';if(str_starts_with($d,'00'))$d=substr($d,2);if(strlen($d)===11&&str_starts_with($d,'34'))$d=substr($d,2);return preg_match('/^[6-9]\d{8}$/',$d)===1?$d:'';}
/** Minúsculas, espacios simples y sin tildes. Sin coincidencias aproximadas. */
function tfNormName(string $raw):string{$s=mb_strtolower(trim($raw),'UTF-8');$s=preg_replace('/\s+/u',' ',$s)??$s;return strtr($s,['á'=>'a','à'=>'a','ä'=>'a','â'=>'a','é'=>'e','è'=>'e','ë'=>'e','ê'=>'e','í'=>'i','ì'=>'i','ï'=>'i','î'=>'i','ó'=>'o','ò'=>'o','ö'=>'o','ô'=>'o','ú'=>'u','ù'=>'u','ü'=>'u','û'=>'u','ç'=>'c']);}

/** Límite de intentos por ventana fija. Lanza 429 al superarlo. */
function tfRateLimit(mysqli $db,string $bucket,int $max,int $seconds):void{
 $key=hash('sha256',$bucket);$win=intdiv(time(),$seconds)*$seconds;
 tfQuery($db,'DELETE FROM tf_rate_limits WHERE window_start<?',[(string)(time()-86400)]);
 tfQuery($db,'INSERT INTO tf_rate_limits(bucket,window_start,hits) VALUES(?,?,1) ON DUPLICATE KEY UPDATE hits=hits+1',[$key,(string)$win]);
 tfRequire((int)tfQuery($db,'SELECT hits FROM tf_rate_limits WHERE bucket=? AND window_start=?',[$key,(string)$win])[0]['hits']<=$max,'TOO_MANY_ATTEMPTS',429);
}
function tfClientKey():string{return (string)($_SERVER['REMOTE_ADDR']??'');}

/**
 * Pregunta a Altas por coincidencia exacta. Devuelve ['result'=>NONE|ONE|MANY,'ref'=>...].
 * Si Altas no responde lanza SOURCE_UNAVAILABLE (503): nunca se presenta como «no eres socio».
 */
function tfAltasMatch(string $name,string $phone):array{
 if(getenv('TF_SSO_TEST_MODE')==='1'&&isset($GLOBALS['tf_altas_stub']))return ($GLOBALS['tf_altas_stub'])($name,$phone);
 $c=tfNotifyConfig();tfRequire(!empty($c['altas_url'])&&!empty($c['altas_token']),'SOURCE_UNAVAILABLE',503);
 // Sin extensión curl (no está en este PHP): flujo HTTPS estándar, verificando el certificado contra el nombre público aunque se conecte a 127.0.0.1.
 $host=(string)($c['altas_host']??'');
 $ctx=stream_context_create(['http'=>['method'=>'POST','timeout'=>8,'ignore_errors'=>true,'follow_location'=>0,'content'=>json_encode(['name'=>$name,'phone'=>$phone]),
  'header'=>"Content-Type: application/json\r\nX-TF-Match: ".$c['altas_token']."\r\n".($host!==''?"Host: $host\r\n":'')],
  'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true]+($host!==''?['peer_name'=>$host]:[])]);
 try{$body=@file_get_contents($c['altas_url'],false,$ctx);}catch(Throwable $e){$body=false;}
 $code=0;foreach($http_response_header??[] as $line)if(preg_match('#^HTTP/\S+\s+(\d{3})#',$line,$m))$code=(int)$m[1];
 $j=is_string($body)?json_decode($body,true):null;
 tfRequire($code===200&&is_array($j)&&($j['ok']??false)===true&&in_array($j['data']['result']??'',['NONE','ONE','MANY'],true),'SOURCE_UNAVAILABLE',503);
 return $j['data'];
}

/** Persona de Reservas ligada a una ficha concreta (Altas o Innux elegida por recepción). Nunca por teléfono: compartir teléfono no fusiona personas. */
function tfPersonForRef(mysqli $db,string $ref,string $name,string $phone):int{
 $p=tfQuery($db,'SELECT id,active FROM tf_people WHERE external_reference=?',[$ref])[0]??null;
 if($p){tfRequire((int)$p['active']===1,'ACCESS_DENIED',403);return (int)$p['id'];}
 tfQuery($db,'INSERT INTO tf_people(nombre,telefono,external_reference) VALUES(?,?,?)',[mb_substr(trim($name),0,100),$phone,$ref]);return (int)$db->insert_id;
}

/**
 * Identificarse con nombre y teléfono. La ficha de socio es OPCIONAL: si coincide exactamente se liga a ella; si no hay ficha, hay varias o
 * Altas no responde, la persona queda como «sin ficha» (referencia GUEST propia de ese nombre + teléfono). Nunca se revela cuál fue el caso:
 * así no se puede averiguar quién es socio. Compartir teléfono no fusiona personas: la clave incluye el nombre.
 */
function tfIdentify(mysqli $db,string $name,string $phone):array{
 $n=tfNormName($name);$ph=tfNormPhone($phone);
 tfRequire(mb_strlen($n)>=3&&mb_strlen($n)<=120&&$ph!=='','INVALID_DATA',400);
 tfRateLimit($db,'identify-ip:'.tfClientKey(),12,600);tfRateLimit($db,'identify-phone:'.$ph,6,3600);
 try{$m=tfAltasMatch($n,$ph);}catch(WebError $e){if($e->getMessage()!=='SOURCE_UNAVAILABLE')throw $e;$m=['result'=>'UNKNOWN'];}
 $ref=null;
 if($m['result']==='ONE')$ref='ALTAS:'.$m['ref'];
 elseif($m['result']==='MANY')tfNotifyAudit($db,'public','IDENTIFY_REVIEW',null,null,['phone'=>tfMaskPhone($ph)]);   // recepción lo revisa; la persona sigue sin ficha
 elseif($m['result']==='UNKNOWN')tfNotifyAudit($db,'public','IDENTIFY_SOURCE_DOWN',null,null,['phone'=>tfMaskPhone($ph)]);
 if($ref===null){
  // Socios que solo existen en Innux: recepción registra la asociación de forma expresa.
  $hits=[];
  foreach(tfQuery($db,"SELECT external_reference r,nombre FROM tf_people WHERE active=1 AND external_reference LIKE 'INNUX:%' AND telefono=?",[$ph]) as $p)if(tfNormName($p['nombre'])===$n)$hits[]=$p['r'];
  $ref=count($hits)===1?$hits[0]:'GUEST:'.substr(hash('sha256',$n.'|'.$ph),0,40);
 }
 return ['status'=>'OK','person'=>tfAtomic($db,fn()=>tfPersonForRef($db,$ref,trim($name),$ph))];
}

/** Crea el móvil de la persona y devuelve el secreto para la cookie (solo se guarda su hash). */
function tfDeviceCreate(mysqli $db,int $person,string $platform):string{
 $platform=in_array($platform,['android','ios','other'],true)?$platform:'other';$secret=bin2hex(random_bytes(32));
 tfQuery($db,'INSERT INTO tf_devices(person_id,token_hash,platform,last_seen_at) VALUES(?,?,?,NOW())',[(string)$person,hash('sha256',$secret),$platform]);
 tfNotifyAudit($db,'person:'.$person,'DEVICE_LINKED',$person,(int)$db->insert_id,['platform'=>$platform]);return $secret;
}
/** Móvil actual a partir de la cookie, o null si no existe, fue revocado o la persona está desactivada. */
function tfDeviceCurrent(mysqli $db):?array{
 $t=(string)($_COOKIE[TF_DEVICE_COOKIE]??'');if(!preg_match('/^[a-f0-9]{64}$/',$t))return null;
 return tfQuery($db,'SELECT d.id,d.person_id,d.platform,p.nombre,p.telefono FROM tf_devices d JOIN tf_people p ON p.id=d.person_id WHERE d.token_hash=? AND d.revoked_at IS NULL AND p.active=1',[hash('sha256',$t)])[0]??null;
}
function tfDeviceRevoke(mysqli $db,int $device,string $by):void{
 $d=tfQuery($db,'SELECT person_id FROM tf_devices WHERE id=? AND revoked_at IS NULL',[(string)$device])[0]??null;if(!$d)return;
 tfQuery($db,'UPDATE tf_devices SET revoked_at=NOW(),revoked_by=? WHERE id=?',[substr($by,0,100),(string)$device]);
 tfQuery($db,"UPDATE tf_push_subscriptions SET status='REVOKED' WHERE device_id=? AND status='ACTIVE'",[(string)$device]);
 tfNotifyAudit($db,$by,'DEVICE_REVOKED',(int)$d['person_id'],$device);
}
function tfDeviceCookie(string $value,int $expires):void{setcookie(TF_DEVICE_COOKIE,$value,['expires'=>$expires,'path'=>'/reservas/','secure'=>true,'httponly'=>true,'samesite'=>'Lax']);}
/** CSRF del móvil: derivado del secreto de la cookie. Además se exige Origin propio y cabecera X-TopFitness-Request. */
function tfDeviceCsrf():string{return hash_hmac('sha256','topfitness-movil-csrf',(string)($_COOKIE[TF_DEVICE_COOKIE]??''));}
function tfDeviceCheckWrite(bool $needsToken):void{
 tfRequire(($_SERVER['HTTP_ORIGIN']??'')===getenv('TF_PUBLIC_ORIGIN')&&($_SERVER['HTTP_X_TOPFITNESS_REQUEST']??'')==='1','REQUEST_NOT_ALLOWED',403);
 if($needsToken)tfRequire(hash_equals(tfDeviceCsrf(),(string)($_SERVER['HTTP_X_CSRF_TOKEN']??'')),'CSRF_REQUIRED',403);
}
