<?php
declare(strict_types=1);
/* Cálculos de calendario y prorrateo (fechas Y-m-d sin zona horaria; la fecha de Madrid la pone quien llama). */

const MAINTENANCE_FEE_CENTS=500;

function ymd(string $date):DateTimeImmutable{$d=DateTimeImmutable::createFromFormat('!Y-m-d',$date);ensure($d&&$d->format('Y-m-d')===$date,'Fecha no válida.');return $d;}

// Parte del mes que queda desde $date (incluido) hasta fin de mes. La matrícula nunca se prorratea.
function prorateMonth(int $monthlyCents,string $date):array{
    $d=ymd($date);$days=(int)$d->format('t');$left=$days-(int)$d->format('j')+1;
    return ['cents'=>(int)round($monthlyCents*$left/$days),'days'=>$left,'days_in_month'=>$days,'from'=>$d->format('Y-m-d'),'to'=>$d->format('Y-m-t')];
}

// Se puede entrenar hasta fin del mes de la solicitud; la baja o el mantenimiento empieza el día 1 siguiente.
function withdrawalDates(string $signed):array{
    $d=ymd($signed);
    return ['last_day'=>$d->format('Y-m-t'),'effective_date'=>$d->modify('first day of next month')->format('Y-m-d')];
}

// Meses completos fuera: desde el mes de efecto hasta el mes anterior al de la vuelta.
function maintenanceMonths(string $effective,string $return):int{
    $e=ymd($effective);$r=ymd($return);
    $months=((int)$r->format('Y')-(int)$e->format('Y'))*12+(int)$r->format('n')-(int)$e->format('n');
    return max(0,$months);
}
