<?php
$path=parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH);
$mounted=false;
if(str_starts_with($path,'/alta/admin/')){$_SERVER['TF_PORTAL']='admin';$path=substr($path,11);$mounted=true;}
elseif(str_starts_with($path,'/alta/')){$_SERVER['TF_PORTAL']='client';$path=substr($path,5);$mounted=true;}
if($path==='/'||$path==='/index.php')require __DIR__.'/index.php';
elseif($path==='/api.php')require __DIR__.'/api.php';
elseif(preg_match('#^/assets/[a-zA-Z0-9_.-]+\.(css|js|jpg|png|ico|svg|woff2)$#',$path,$match)&&is_file(__DIR__.$path)){
    if(!$mounted)return false;
    header('Content-Type: '.['css'=>'text/css','js'=>'application/javascript','jpg'=>'image/jpeg','png'=>'image/png','ico'=>'image/x-icon','svg'=>'image/svg+xml','woff2'=>'font/woff2'][$match[1]]);readfile(__DIR__.$path);
}
else{http_response_code(404);header('Cache-Control: no-store');echo 'No encontrado';}
