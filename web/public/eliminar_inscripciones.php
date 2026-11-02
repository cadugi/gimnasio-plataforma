<?php
declare(strict_types=1);
if(empty($_SERVER['REMOTE_USER'])){http_response_code(401);exit;}
require dirname(__DIR__).'/sso/admin_legacy_support.php';require dirname(__DIR__).'/sso/admin_legacy_eliminar_inscripciones.php';
