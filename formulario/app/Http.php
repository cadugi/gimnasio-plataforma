<?php
declare(strict_types=1);
function startHttp(Service $s):void{
    ini_set('display_errors','0');ini_set('session.use_strict_mode','1');ini_set('session.use_only_cookies','1');
    $secure=($_SERVER['HTTPS']??'')==='on';$remote=$_SERVER['REMOTE_ADDR']??'';if(in_array($remote,$s->config['trusted_proxy_ips']??[],true)&&($_SERVER['HTTP_X_FORWARDED_PROTO']??'')==='https')$secure=true;
    if(!$s->demo()){ensure($secure,'HTTPS es obligatorio en producción.',426);ensure(empty($s->config['demo_loopback_login'])&&str_starts_with($s->config['public_origin']??'','https://'),'Revisa la configuración de producción y desactiva el acceso demo.',503);}
    $origin=$_SERVER['HTTP_ORIGIN']??'';if($origin!==''){$expected=$s->config['public_origin']??'';if($expected==='')$expected=($secure?'https://':'http://').($_SERVER['HTTP_HOST']??'');ensure(hash_equals($expected,$origin),'Origen no autorizado.',403);}
    $portal='';
    if(($s->config['separate_portals']??false)===true){
        $portal=(string)($_SERVER['TF_PORTAL']??'');ensure(in_array($portal,['client','admin'],true),'Portal no configurado.',503);
        $s->config['request_portal']=$portal;$s->config['session_name']=$portal==='client'?'TF_ALTAS_CLIENT':'TF_ALTAS_ADMIN';$s->config['cookie_path']=$portal==='client'?'/alta/':'/alta/admin/';
        $s->config['session_directory']=($s->config['session_directory']??$s->root.'/.private/sessions').'/'.$portal;
    }
    $dir=$s->config['session_directory']??$s->root.'/.private/sessions';if(!is_dir($dir))mkdir($dir,0700,true);session_save_path($dir);session_name($s->config['session_name']??'TF_CONTRACTS');$tablet=(int)($s->config['tablet_device_seconds']??28800);session_set_cookie_params(['lifetime'=>$portal==='client'?$tablet:0,'path'=>$s->config['cookie_path']??'/','secure'=>$secure||!$s->demo(),'httponly'=>true,'samesite'=>'Strict']);session_start();
    $timeout=($_SESSION['mode']??'')==='kiosk'?(int)($s->config['kiosk_idle_seconds']??300):(int)($s->config['session_idle_seconds']??1800);
    if(isset($_SESSION['last_activity'])&&time()-(int)$_SESSION['last_activity']>$timeout){$mode=$_SESSION['mode']??'';if($mode==='kiosk')$s->sql('DELETE FROM drafts WHERE session_hash=?',[$s->vault->fingerprint('draft:'.session_id())]);$device=array_intersect_key($_SESSION,array_flip(['device_actor','device_expires_at']));$_SESSION=$mode==='kiosk'?array_merge($device,['mode'=>'kiosk','kiosk_locked'=>true,'csrf'=>$_SESSION['csrf']??uuid()]):['csrf'=>uuid()];session_regenerate_id(true);$_SESSION['expired']=true;}
    if($portal==='client'&&(!empty($_SESSION['user_id'])||((($_SESSION['mode']??'')==='kiosk')&&(int)($_SESSION['device_expires_at']??0)<=time()))){
        $s->sql('DELETE FROM drafts WHERE session_hash=?',[$s->vault->fingerprint('draft:'.session_id())]);$_SESSION=['csrf'=>uuid()];session_regenerate_id(true);
    }
    if($portal==='client'&&($_SESSION['mode']??'')==='kiosk'&&isset($_SESSION['device_expires_at'])){$_SESSION['device_expires_at']=time()+$tablet;setcookie(session_name(),session_id(),['expires'=>$_SESSION['device_expires_at'],'path'=>$s->config['cookie_path']??'/','secure'=>$secure||!$s->demo(),'httponly'=>true,'samesite'=>'Strict']);}
    if($portal==='admin'&&($_SESSION['mode']??'')==='kiosk'){$_SESSION=['csrf'=>uuid()];session_regenerate_id(true);}
    // This opt-in belongs exclusively to the isolated HTTPS LAN demo config.
    // It grants kiosk permissions, never an employee/admin session.
    if(($s->config['demo_lan_reception']??false)===true&&$s->config['environment']==='demo'&&$secure&&empty($_SESSION['mode'])){
        session_regenerate_id(true);
        $_SESSION=['mode'=>'kiosk','kiosk_locked'=>true,'device_actor'=>'lan-demo','csrf'=>uuid()];
    }
    $_SESSION['csrf']??=uuid();if(($_GET['action']??'')!=='ping'||($_GET['active']??'')==='1')$_SESSION['last_activity']=time();
}
function secureHeaders():void{header('Cache-Control: no-store, private');header('Pragma: no-cache');header('X-Content-Type-Options: nosniff');header('Referrer-Policy: no-referrer');header('X-Frame-Options: SAMEORIGIN');header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'");header('Permissions-Policy: camera=(), microphone=(), geolocation=()');if(($_SERVER['HTTPS']??'')==='on')header('Strict-Transport-Security: max-age=31536000');}
function jsonResponse(array $value,int $status=200):never{http_response_code($status);header('Content-Type: application/json; charset=utf-8');echo jencode($value);exit;}
function fileResponse(string $bytes,string $mime,string $filename,bool $inline=false):never{header('Content-Type: '.$mime);header('Content-Disposition: '.($inline?'inline':'attachment').'; filename="'.$filename.'"');header('Content-Length: '.strlen($bytes));echo $bytes;exit;}

function checkPortalAction(Service $s,string $action):void{
    $portal=$s->config['request_portal']??'';
    $client=['bootstrap','tablet_activate','tablet_lock','draft_new','draft_save','draft_prepare','draft_cancel','contract_sign','photo_save','photo_remove','draft_photo','preview_pdf','review_document','document','holder_sign','mandate_document','withdrawal_start','withdrawal_identify','withdrawal_save','withdrawal_prepare','withdrawal_sign','withdrawal_cancel','withdrawal_review','withdrawal_preview','withdrawal_document','ping'];
    if($portal==='client')ensure(in_array($action,$client,true),'Esta opción no pertenece al formulario de clientes.',403);
    if($portal==='admin')ensure(!in_array($action,array_diff($client,['bootstrap','document','mandate_document','withdrawal_document']),true)&&$action!=='kiosk_start','Esta opción solo está disponible en el formulario de clientes.',403);
}
