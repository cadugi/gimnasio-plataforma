<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/sso/members.php';require_once __DIR__.'/conexion.php';
try{
 tfRequire(!empty($_SERVER['REMOTE_USER']),'AUTH_REQUIRED',401);
 tfRequire(($_SERVER['REQUEST_METHOD']??'')==='POST','METHOD_NOT_ALLOWED',405);
 tfRequire(($_SERVER['HTTP_ORIGIN']??'')===getenv('TF_PUBLIC_ORIGIN')&&($_SERVER['HTTP_X_TOPFITNESS_REQUEST']??'')==='1','REQUEST_NOT_ALLOWED',403);
 tfRequire((int)($_SERVER['CONTENT_LENGTH']??0)<=4096,'INVALID_REQUEST',400);
 $r=json_decode(file_get_contents('php://input'),true,16,JSON_THROW_ON_ERROR);tfRequire(is_array($r),'INVALID_REQUEST');
 tfJson(tfMemberRead($conn,$r));
}catch(WebError $e){tfJson(['success'=>false,'error'=>$e->getMessage()],$e->status);}catch(Throwable $e){tfJson(['success'=>false,'error'=>'TEMPORARY_FAILURE'],503);}
