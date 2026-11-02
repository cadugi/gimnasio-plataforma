<?php
declare(strict_types=1);
require dirname(__DIR__).'/web/sso/public_booking_rules.php';
$now=new DateTimeImmutable('2026-10-22 10:00:00',new DateTimeZone('Europe/Madrid'));$passed=0;
$check=function(array $schedule,string $date,bool $expected)use($now,&$passed){try{tfPublicValidateSchedule($schedule,$date,$now);$ok=true;}catch(InvalidArgumentException){$ok=false;}if($ok!==$expected)throw new RuntimeException('Fallo de regla de reserva: '.$date);$passed++;};
$check(['dia'=>'jueves','hora'=>'11:00-12:00'],'2026-10-22',true);
$check(['dia'=>'martes','hora'=>'11:00-12:00'],'2026-10-27',true);
$check(['dia'=>'miercoles','hora'=>'11:00-12:00'],'2026-10-28',false);
$check(['dia'=>'miercoles','hora'=>'11:00-12:00'],'2026-10-21',false);
$check(['dia'=>'viernes','hora'=>'11:00-12:00'],'2026-10-22',false);
$check(['dia'=>'jueves','hora'=>'09:00-10:00'],'2026-10-22',false);
$check(['dia'=>'jueves','hora'=>'10:00-11:00'],'2026-10-22',false);
$check(['dia'=>'jueves','hora'=>'25:00-26:00'],'2026-10-22',false);
$check(['dia'=>'jueves','hora'=>'12:00-11:00'],'2026-10-22',false);
$check(['dia'=>'jueves','hora'=>'11:00-12:00'],'2026-02-31',false);
$check(['dia'=>'sábado','hora'=>'11:00-12:00'],'2026-10-24',true);
echo "Public booking rules: $passed passed\n";
