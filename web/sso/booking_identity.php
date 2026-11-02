<?php
declare(strict_types=1);
/* Identidad de una persona dentro de una sesión (clase + día): teléfono normalizado Y nombre normalizado.
   Nunca solo el nombre. «Ana  Pérez» y «ana perez» son la misma persona con el mismo teléfono (con o sin +34, espacios o guiones).
   Debe llamarse DENTRO de la transacción y con el cerrojo tf_mutex tomado: así dos pulsaciones o dos peticiones simultáneas se serializan. */

function tfIdPhone(string $raw):string{
    $d=preg_replace('/\D/','',$raw)??'';
    if(strlen($d)===13&&str_starts_with($d,'0034'))$d=substr($d,4);
    elseif(strlen($d)===11&&str_starts_with($d,'34'))$d=substr($d,2);
    return $d;
}
function tfIdName(string $raw):string{
    $s=mb_strtolower(trim($raw),'UTF-8');$s=preg_replace('/\s+/u',' ',$s)??$s;
    if(class_exists('Normalizer')){$n=Normalizer::normalize($s,Normalizer::FORM_D);if($n!==false)$s=preg_replace('/[\x{0300}-\x{036f}]/u','',$n)??$s;}
    return strtr($s,['á'=>'a','à'=>'a','ä'=>'a','â'=>'a','é'=>'e','è'=>'e','ë'=>'e','ê'=>'e','í'=>'i','ì'=>'i','ï'=>'i','î'=>'i','ó'=>'o','ò'=>'o','ö'=>'o','ô'=>'o','ú'=>'u','ù'=>'u','ü'=>'u','û'=>'u','ç'=>'c']);
}
function tfIdSame(string $nameA,string $phoneA,string $nameB,string $phoneB):bool{
    $pa=tfIdPhone($phoneA);$pb=tfIdPhone($phoneB);
    $samePhone=$pa!==''&&$pb!==''?$pa===$pb:trim($phoneA)===trim($phoneB);
    return $samePhone&&tfIdName($nameA)===tfIdName($nameB);
}
/** Inscripción existente de la misma persona en la sesión, o null. */
function tfIdFindInscription(mysqli $conn,int $schedule,string $date,string $name,string $phone):?array{
    $st=$conn->prepare('SELECT id,nombre,telefono FROM inscripciones WHERE horario_id=? AND fecha=?');$st->bind_param('is',$schedule,$date);$st->execute();
    $rows=$st->get_result()->fetch_all(MYSQLI_ASSOC);$st->close();
    foreach($rows as $r)if(tfIdSame($name,$phone,(string)$r['nombre'],(string)$r['telefono']))return $r;
    return null;
}
/** Espera de ese teléfono en esta sesión. El llamador debe comprobar también el nombre:
 * la tabla heredada admite una sola espera por teléfono, clase y fecha. Nunca atribuirla a otra persona. */
function tfIdFindWaiting(mysqli $conn,int $schedule,string $date,string $phone):?array{
    $st=$conn->prepare('SELECT id,nombre,telefono,fecha FROM inscripciones_cola WHERE horario_id=? AND fecha=?');$st->bind_param('is',$schedule,$date);$st->execute();
    $rows=$st->get_result()->fetch_all(MYSQLI_ASSOC);$st->close();$key=tfIdPhone($phone);
    foreach($rows as $r)if($key!==''?tfIdPhone((string)$r['telefono'])===$key:trim((string)$r['telefono'])===trim($phone))return $r;
    return null;
}
/** Clase cancelada ese día. */
function tfIdCancelled(mysqli $conn,int $schedule,string $date):bool{
    $st=$conn->prepare('SELECT 1 FROM clases_canceladas WHERE horario_id=? AND fecha=?');$st->bind_param('is',$schedule,$date);$st->execute();
    $r=$st->get_result()->fetch_row();$st->close();return (bool)$r;
}
/** Registro de acciones administrativas delicadas (p. ej. superar el aforo) en la auditoría existente (tf_identity_audit). Si falla, queda en el log del servidor. */
function tfIdAudit(mysqli $conn,string $action,array $detail):void{
    $who=substr((string)($_SERVER['REMOTE_USER']??''),0,100);$json=json_encode($detail,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES)?:'{}';$zero=0;
    try{
        $st=$conn->prepare('INSERT INTO tf_identity_audit(actor,action,person_id,detail_json) VALUES(?,?,?,?)');$st->bind_param('ssis',$who,$action,$zero,$json);$st->execute();$st->close();
    }catch(Throwable $e){error_log('[reservas] '.$action.' usuario='.$who.' '.$json);}
}
