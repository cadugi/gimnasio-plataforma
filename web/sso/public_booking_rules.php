<?php
declare(strict_types=1);
/** Validación compartida del calendario público; no depende de MySQL ni modifica datos. */
function tfPublicValidateSchedule(array $schedule,string $date,?DateTimeImmutable $now=null):void{
    $zone=new DateTimeZone('Europe/Madrid');$now=($now??new DateTimeImmutable('now',$zone))->setTimezone($zone);
    $day=DateTimeImmutable::createFromFormat('!Y-m-d',$date,$zone);
    if(!$day||$day->format('Y-m-d')!==$date)throw new InvalidArgumentException('La fecha no es válida.');
    if($day<$now->setTime(0,0)||$day>$now->setTime(0,0)->modify('+5 days'))throw new InvalidArgumentException('Solo puedes reservar desde hoy hasta los próximos 5 días.');
    $names=['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
    $name=strtr(strtolower(trim((string)($schedule['dia']??''))),['á'=>'a','é'=>'e','í'=>'i','ó'=>'o','ú'=>'u']);
    if($name!==$names[(int)$day->format('w')])throw new InvalidArgumentException('La clase no corresponde al día elegido.');
    $hours=(string)($schedule['hora']??'');
    if(!preg_match('/^([01][0-9]|2[0-3]):[0-5][0-9]-([01][0-9]|2[0-3]):[0-5][0-9]$/',$hours)||substr($hours,0,5)>=substr($hours,6,5))throw new InvalidArgumentException('El horario de esta clase necesita revisión en recepción.');
    if(new DateTimeImmutable($date.' '.substr($hours,0,5),$zone)<=$now)throw new InvalidArgumentException('Esta clase ya ha empezado. Elige otro horario.');
}
