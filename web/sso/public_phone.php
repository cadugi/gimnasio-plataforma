<?php
declare(strict_types=1);
/* Reservas públicas: el teléfono identifica a la persona para el límite semanal.
   Solo números españoles de 9 cifras que empiezan por 6, 7 u 8, y nada de números inventados. */

const TF_PUBLIC_WEEKLY_LIMIT=10;

// Devuelve el número limpio (9 cifras) o null si no es válido.
function tfPublicPhone(string $raw):?string{
    $d=preg_replace('/\D/','',$raw);
    if(strlen($d)===13&&str_starts_with($d,'0034'))$d=substr($d,4);
    elseif(strlen($d)===11&&str_starts_with($d,'34'))$d=substr($d,2);
    if(preg_match('/^[678]\d{8}$/',$d)!==1)return null;
    if(preg_match('/^\d(\d)\1{7}$/',$d)===1)return null;                  // 600000000, 666666666
    if(count(array_unique(str_split($d)))<=2)return null;                 // 600060000, 677767777
    for($p=2;$p<=4;$p++)if(str_starts_with(str_repeat(substr($d,0,$p),5),$d))return null; // 676767676, 678678678
    $up=$down=1;                                                          // 612345678, 698765432, 678901234
    for($i=1;$i<9;$i++){
        $diff=((int)$d[$i]-(int)$d[$i-1]+10)%10;
        $up=$diff===1?$up+1:1;$down=$diff===9?$down+1:1;
        if($up>=6||$down>=6)return null;
    }
    return $d;
}

// Lunes y domingo de la semana de una fecha 'AAAA-MM-DD'.
function tfPublicWeek(string $date):array{
    $d=new DateTimeImmutable($date,new DateTimeZone('Europe/Madrid'));$start=$d->modify('-'.((int)$d->format('N')-1).' days');
    return [$start->format('Y-m-d'),$start->modify('+6 days')->format('Y-m-d')];
}

// Clases (reservadas o en espera) de ese teléfono en la semana. Las canceladas por el gimnasio no cuentan.
function tfPublicWeekCount(mysqli $conn,string $phone,string $date):int{
    [$from,$until]=tfPublicWeek($date);$n=0;
    foreach(['inscripciones','inscripciones_cola'] as $table){
        $stmt=$conn->prepare("SELECT COUNT(*) n FROM $table t WHERE RIGHT(REGEXP_REPLACE(t.telefono,'[^0-9]',''),9)=? AND t.fecha BETWEEN ? AND ? AND NOT EXISTS (SELECT 1 FROM clases_canceladas c WHERE c.horario_id=t.horario_id AND c.fecha=t.fecha)");
        $stmt->bind_param('sss',$phone,$from,$until);$stmt->execute();$n+=(int)$stmt->get_result()->fetch_assoc()['n'];
    }
    return $n;
}
