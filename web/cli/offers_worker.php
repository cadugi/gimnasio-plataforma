<?php
declare(strict_types=1);
// Worker de ofertas (systemd). Cada 2 s: caduca ofertas vencidas, continúa la cadena y ofrece plazas libres. El estado vive en MariaDB:
// tras un reinicio se resuelven las pendientes por su hora de vencimiento. Con --once hace una sola pasada.
if(PHP_SAPI!=='cli')exit(1);
require_once dirname(__DIR__).'/sso/offers.php';
mysqli_report(MYSQLI_REPORT_ERROR|MYSQLI_REPORT_STRICT);date_default_timezone_set('Europe/Madrid');
/** Misma conexión que public/conexion.php (hora de Madrid en la sesión), pero sin terminar el proceso si la base no responde. */
function tfWorkerConnect():mysqli{$c=new mysqli(getenv('TF_REAL_DB_HOST'),getenv('TF_REAL_DB_USER'),getenv('TF_REAL_DB_PASSWORD'),getenv('TF_REAL_DB_NAME'),3306);$c->set_charset('utf8mb4');$c->query("SET time_zone = '".date('P')."'");return $c;}
$once=in_array('--once',$argv,true);
while(true){
 try{
  $conn=tfWorkerConnect();
  tfQuery($conn,"INSERT INTO tf_notify_settings(k,v) VALUES('HB_OFFERS','1') ON DUPLICATE KEY UPDATE v=NOT v");   // latido para la vista de recepción
  $r=tfOffersTick($conn);if($r['expired']||$r['created'])fwrite(STDOUT,date('c').' ofertas: caducadas='.$r['expired'].' creadas='.$r['created']."\n");
  $conn->close();
 }catch(Throwable $e){fwrite(STDERR,date('c').' offers_worker: '.get_class($e)."\n");}
 if($once)exit(0);
 sleep(2);
}
