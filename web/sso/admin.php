<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/sso/library.php';require_once __DIR__.'/conexion.php';
try{
 tfRequire(!empty($_SERVER['REMOTE_USER']),'AUTH_REQUIRED',401);
 session_name('TF_RESERVAS_ADMIN');session_set_cookie_params(['secure'=>true,'httponly'=>true,'samesite'=>'Strict','path'=>'/admin/']);session_start();$_SESSION['csrf']??=bin2hex(random_bytes(32));
 if(($_SERVER['REQUEST_METHOD']??'')==='GET'&&!isset($_GET['action'])){
  header('Content-Type: text/html; charset=utf-8');echo '<!doctype html><html lang="es"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Identidades · Top Fitness</title><link rel="stylesheet" href="mobile.css"><main><h1>Identidades de reservas</h1><p>Las vinculaciones deben comprobarse con la ficha del socio. Compartir teléfono no significa ser la misma persona.</p><div id="tf-admin-root"></div></main><script src="identities.js" defer></script></html>';exit;
 }
 if(($_SERVER['REQUEST_METHOD']??'')==='GET')tfJson(['success'=>true,'csrf'=>$_SESSION['csrf'],'people'=>tfQuery($conn,'SELECT id,nombre,telefono,external_reference,active FROM tf_people ORDER BY nombre,id')]);
 tfRequire(hash_equals($_SESSION['csrf'],$_SERVER['HTTP_X_CSRF_TOKEN']??''),'CSRF_REQUIRED',403);
 $r=json_decode(file_get_contents('php://input'),true,32,JSON_THROW_ON_ERROR);$action=$r['action']??'';$person=(int)($r['person_id']??0);$p=tfPerson($conn,$person);$actor=(string)$_SERVER['REMOTE_USER'];
 if($action==='legacy'){$rows=[];$phoneExpr=tfPhoneSql('x.telefono');foreach(['inscripciones'=>'reservation_id','inscripciones_cola'=>'wait_id'] as $table=>$column){foreach(tfQuery($conn,"SELECT x.id,x.nombre,x.telefono,x.horario_id,x.fecha FROM $table x LEFT JOIN tf_bookings b ON b.$column=x.id WHERE b.id IS NULL AND $phoneExpr=? ORDER BY x.fecha DESC LIMIT 100",[tfPhoneKey($p['telefono'])]) as $row){$row['table']=$table;$rows[]=$row;}}tfJson(['success'=>true,'items'=>$rows]);}
 if($action==='revoke')tfAtomic($conn,function()use($conn,$person,$actor){tfQuery($conn,'UPDATE tf_people SET session_epoch=session_epoch+1 WHERE id=?',[$person]);tfQuery($conn,'DELETE FROM tf_sessions WHERE person_id=?',[$person]);tfQuery($conn,'INSERT INTO tf_identity_audit(actor,action,person_id,detail_json) VALUES(?,?,?,?)',[$actor,'SESSIONS_REVOKED',$person,'{}']);});
 elseif($action==='link_legacy'){
  tfRequire(($r['confirmed']??false)===true,'CONFIRMATION_REQUIRED');$items=$r['items']??[];tfRequire(is_array($items)&&count($items)>0&&count($items)<=100,'INVALID_SELECTION');
  tfAtomic($conn,function()use($conn,$person,$actor,$items){foreach($items as $item){$table=$item['table']??'';tfRequire(in_array($table,['inscripciones','inscripciones_cola'],true),'INVALID_TABLE');$raw=tfQuery($conn,"SELECT id,nombre,telefono,horario_id,fecha FROM $table WHERE id=?",[(int)($item['id']??0)])[0]??null;tfRequire($raw,'BOOKING_NOT_FOUND');$column=$table==='inscripciones'?'reservation_id':'wait_id';tfRequire(!tfQuery($conn,"SELECT id FROM tf_bookings WHERE $column=?",[$raw['id']]),'ALREADY_LINKED',409);tfQuery($conn,'INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,reservation_id,wait_id) VALUES(?,?,?,?,?,?)',[$person,$raw['horario_id'],$raw['fecha'],$table==='inscripciones'?'RESERVED':'WAITLIST',$table==='inscripciones'?$raw['id']:null,$table==='inscripciones_cola'?$raw['id']:null]);}tfQuery($conn,'INSERT INTO tf_identity_audit(actor,action,person_id,detail_json) VALUES(?,?,?,?)',[$actor,'LEGACY_LINKED',$person,json_encode($items)]);});
 }else tfRequire($action==='revoke','INVALID_ACTION');
 tfJson(['success'=>true]);
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
