<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/sso/library.php';require_once __DIR__.'/conexion.php';
try{
 $session=tfSession($conn);$admin=!empty($_SERVER['REMOTE_USER']);$person=$session?(int)$session['person_id']:(int)($_POST['person_id']??0);
 tfRequire($session||$admin,'AUTH_REQUIRED',401);tfRequire($person>0,'PERSON_REQUIRED');tfPerson($conn,$person);
 $principal=$session?$session['principal']:'admin:'.$_SERVER['REMOTE_USER'];$key=(string)($_POST['request_key']??'');
 $r=tfWrite($conn,$principal,$person,['action'=>'reserve','horario_id'=>(int)($_POST['horario_id']??0),'fecha'=>(string)($_POST['fecha']??''),'accept_waitlist'=>true,'request_key'=>$key],$admin);
 $b=$r['booking'];$h=tfSchedule($conn,$b['horario_id'],$b['fecha']);
 tfJson(['success'=>true,'status'=>$b['estado']==='RESERVED'?'INSCRIBED':'WAITLIST','id'=>$b['id'],'posicion'=>$b['posicion'],'disponibles'=>$h['disponibles'],'inscritos'=>$h['limite']-$h['disponibles'],'limite'=>$h['limite'],'quota'=>tfQuota($conn,$person,$b['fecha'])]);
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
