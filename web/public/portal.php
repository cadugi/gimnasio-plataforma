<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/sso/library.php';
require_once __DIR__.'/conexion.php';
try{
 $method=$_SERVER['REQUEST_METHOD']??'GET';$script=basename($_SERVER['SCRIPT_FILENAME']);
 if($script==='entrar.php'){
  header('Referrer-Policy: no-referrer');header('Cache-Control: no-store');
  try{$r=tfRedeem($conn,(string)($_GET['t']??''));tfCookie($r['cookie'],$r['expires']);header('Location: /reservas/',true,303);exit;}
  catch(WebError $e){header('Location: /reservas/?acceso=caducado',true,303);exit;}
 }
 if($script==='portal.php'){
  header('Referrer-Policy: no-referrer');header('Cache-Control: no-store, private');header('Vary: User-Agent, Sec-CH-UA-Mobile');
  $session=tfSession($conn);$kiosk=is_file(dirname(__DIR__).'/PUBLIC_KIOSK');
  if(!$session&&!$kiosk){
   $phone=preg_replace('/\D/','',getenv('TF_WHATSAPP_NUMBER')?:(is_file(dirname(__DIR__).'/sso/whatsapp-number.txt')?file_get_contents(dirname(__DIR__).'/sso/whatsapp-number.txt'):''));$link=$phone?'https://wa.me/'.$phone.'?text=Reservar%20clases':'';
   header('Content-Type: text/html; charset=utf-8');echo '<!doctype html><html lang="es"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reservas · Top Fitness</title><style>body{margin:0;background:#101410;color:#fff;font:18px system-ui;display:grid;min-height:100vh;place-items:center}main{max-width:440px;padding:32px}h1{color:#64df36}a{display:block;padding:18px;background:#64df36;color:#10200a;text-align:center;text-decoration:none;margin-top:28px}p{line-height:1.6}</style><main><h1>TOP FITNESS</h1><h2>Tus clases, desde WhatsApp</h2><p>Abre el chat y pulsa «Reservar clases» para acceder a tu agenda sin contraseña.</p>';
   if(isset($_GET['acceso']))echo '<p>El enlace ha caducado o ya se ha utilizado. Pide uno nuevo en el chat.</p>';
   if($link)echo '<a href="'.htmlspecialchars($link,ENT_QUOTES).'">Abrir WhatsApp</a>';else echo '<p>Solicita tu enlace al número de prueba de WhatsApp.</p>';echo '</main></html>';exit;
  }
  $mobile=($_SERVER['HTTP_SEC_CH_UA_MOBILE']??'')==='?1'||(($_SERVER['HTTP_SEC_CH_UA_MOBILE']??'')!=='?0'&&preg_match('/Android|iPhone|iPad|Mobile/i',$_SERVER['HTTP_USER_AGENT']??''));
  $html=file_get_contents(__DIR__.($mobile?'/mobile.html':'/index.html'));$html=$session?str_replace('</head>','<script src="sso.js" defer></script></head>',$html):$html;header('Content-Type: text/html; charset=utf-8');echo $html;exit;
 }
 if($script==='service.php'){
  tfRequire($method==='POST','METHOD_NOT_ALLOWED',405);
  $secret=getenv('BACKEND_SECRET')?:'';tfRequire($secret&&hash_equals('Bearer '.$secret,$_SERVER['HTTP_AUTHORIZATION']??''),'SERVICE_AUTH_REQUIRED',401);
  tfRequire((int)($_SERVER['CONTENT_LENGTH']??0)<=8192,'REQUEST_TOO_LARGE',413);$r=json_decode(file_get_contents('php://input'),true,32,JSON_THROW_ON_ERROR);tfRequire(is_array($r),'INVALID_REQUEST');$principal=(string)($r['user_id']??'');
  tfRequire(tfQuery($conn,'SELECT person_id FROM tf_permissions WHERE principal=?',[$principal]),'ACCESS_DENIED',403);
  $action=$r['action']??'';$person=(int)($r['persona_id']??0);
  if($action==='people')tfJson(['ok'=>true,'people'=>array_map(fn($p)=>['id'=>(int)$p['id'],'nombre'=>$p['nombre']],tfQuery($conn,'SELECT p.id,p.nombre FROM tf_people p JOIN tf_permissions a ON a.person_id=p.id WHERE a.principal=? AND p.active=1 ORDER BY p.id',[$principal])),'mode'=>'official_vps','portable_features'=>true,'notifications_enabled'=>false]);
  tfAllowed($conn,$principal,$person);
  if($action==='web_link')tfJson(['ok'=>true]+tfMint($conn,$principal,$person));
  if(in_array($action,['reserve','cancel','leave_waitlist','reschedule'],true))tfJson(tfWrite($conn,$principal,$person,$r));
  require_once dirname(__DIR__).'/sso/reads.php';tfJson(tfRead($conn,$principal,$person,$r));
 }
 $session=tfSession($conn);tfRequire($session,'AUTH_REQUIRED',401);$person=(int)$session['person_id'];
 if($script==='identidad.php'){
  if($method==='POST'){tfCheckCsrf();$r=json_decode(file_get_contents('php://input'),true);tfRequire(($r['action']??'')==='logout','INVALID_ACTION');tfQuery($conn,'DELETE FROM tf_sessions WHERE token_hash=?',[$session['token_hash']]);tfCookie('',time()-3600);tfJson(['success'=>true]);}
  $p=tfPerson($conn,$person);$date=(string)($_GET['fecha']??tfNow()->format('Y-m-d'));tfJson(['success'=>true,'person'=>['id'=>$person,'nombre'=>$p['nombre'],'telefono'=>$p['telefono']],'csrf'=>tfCsrf(),'quota'=>tfQuota($conn,$person,$date),'legacy_pending'=>tfLegacyPending($conn,$p,$date)]);
 }
 if($script==='mis_reservas.php'){
  if($method==='POST'){tfCheckCsrf();$r=json_decode(file_get_contents('php://input'),true);tfJson(tfWrite($conn,$session['principal'],$person,['action'=>'cancel','booking_id'=>(int)($r['id']??0),'request_key'=>(string)($r['request_key']??'')]));}
  tfJson(['success'=>true,'bookings'=>array_map(fn($r)=>tfDescribe($conn,(int)$r['id']),tfQuery($conn,"SELECT id FROM tf_bookings WHERE person_id=? AND estado IN ('RESERVED','WAITLIST') AND fecha>=? ORDER BY fecha,horario_id",[$person,tfNow()->format('Y-m-d')]))]);
 }
 throw new WebError('NOT_FOUND',404);
}catch(WebError $e){tfJson(['ok'=>false,'success'=>false,'error'=>$e->getMessage()],$e->status);}
catch(Throwable $e){tfJson(['ok'=>false,'success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
