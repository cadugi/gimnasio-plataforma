<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/sso/library.php';require_once __DIR__.'/conexion.php';
try{
 tfRequire(!empty($_SERVER['REMOTE_USER']),'AUTH_REQUIRED',401);$ids=$_POST['ids']??[$_POST['id']??0];tfRequire(is_array($ids)&&count($ids)<=100,'INVALID_SELECTION');$ids=array_values(array_filter(array_map('intval',$ids),fn($v)=>$v>0));tfRequire($ids,'INVALID_SELECTION');
 tfAtomic($conn,function()use($conn,$ids){foreach($ids as $id){$b=tfQuery($conn,'SELECT id,person_id FROM tf_bookings WHERE reservation_id=?',[$id])[0]??null;if($b){tfCancel($conn,(int)$b['person_id'],(int)$b['id']);continue;}$old=tfQuery($conn,'SELECT horario_id,fecha FROM inscripciones WHERE id=?',[$id])[0]??null;if(!$old)continue;tfQuery($conn,'DELETE FROM inscripciones WHERE id=?',[$id]);tfPromote($conn,(int)$old['horario_id'],$old['fecha']);}});
 tfJson(['success'=>true,'promoted'=>null,'promoted_all'=>[]]);
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
