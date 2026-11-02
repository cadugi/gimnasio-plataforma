<?php
declare(strict_types=1);
// Tarea periódica (systemd timer, cada minuto): programa recordatorios. Solo CLI.
if(PHP_SAPI!=='cli')exit(1);
require_once dirname(__DIR__).'/public/conexion.php';require_once dirname(__DIR__).'/sso/avisos.php';
try{
 if(!tfNotifySwitch($conn,'PUSH_SEND_ENABLED')&&trim((string)(tfQuery($conn,"SELECT v FROM tf_notify_settings WHERE k='PUSH_ALLOW_PERSONS'")[0]['v']??''))==='')exit(0);   // todo apagado: no se programa nada
 $n=tfPlanReminders($conn);if($n)fwrite(STDOUT,"recordatorios programados: $n\n");
}catch(Throwable $e){fwrite(STDERR,'notify_tick: '.get_class($e)."\n");exit(1);}
