<?php
// Ejecuta una ruta heredada como lo haría PHP-FPM (con recepción autenticada) sobre la BD de pruebas. Uso: php legacy_call.php RUTA 'json_post'
if(!str_contains(getenv('TF_REAL_DB_NAME')?:'','test'))exit(2);
$_POST=json_decode($argv[2]??'{}',true);$_SERVER['REMOTE_USER']='recepcion';$_SERVER['REQUEST_METHOD']=($argv[3]??'POST');$_SERVER['REMOTE_ADDR']='203.0.113.5';
chdir(dirname($argv[1]));include $argv[1];
