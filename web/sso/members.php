<?php
declare(strict_types=1);
require_once __DIR__.'/library.php';
/** Solo SELECT: las relaciones existentes no se crean ni se reparan al consultar. */
function tfMemberRead(mysqli $conn,array $r):array{
 $phoneExpr=tfPhoneSql('telefono');$action=$r['action']??'search';
 if($action==='search'){
  $q=trim((string)($r['query']??''));tfRequire(mb_strlen($q)>=2&&mb_strlen($q)<=60,'INVALID_QUERY');$like='%'.strtr($q,['='=>'==','%'=>'=%','_'=>'=_']).'%';$digits=preg_replace('/\D/','',$q);$phone=strlen($digits)>=3?'%'.$digits.'%':'NO_PHONE_SEARCH';
  $items=tfQuery($conn,"SELECT nombre name,telefono phone FROM (SELECT nombre,telefono FROM tf_people UNION SELECT nombre,telefono FROM inscripciones UNION SELECT nombre,telefono FROM inscripciones_cola) p WHERE nombre LIKE ? ESCAPE '=' OR $phoneExpr LIKE ? GROUP BY nombre,telefono ORDER BY nombre,telefono LIMIT 31",[$like,$phone]);$hasMore=count($items)>30;
  $items=array_slice($items,0,30);
  // Clases de esta semana (lunes a domingo) de cada persona encontrada: una sola consulta para toda la lista.
  $monday=date('Y-m-d',strtotime('monday this week'));$sunday=date('Y-m-d',strtotime('sunday this week'));
  $week=[];
  foreach(['inscripciones'=>'RESERVED','inscripciones_cola'=>'WAITLIST'] as $table=>$state){
   foreach(tfQuery($conn,"SELECT x.nombre name,x.telefono phone,x.fecha date,h.clase class,h.hora time FROM $table x JOIN horarios h ON h.id=x.horario_id WHERE x.fecha BETWEEN ? AND ? AND NOT EXISTS(SELECT 1 FROM clases_canceladas c WHERE c.horario_id=x.horario_id AND c.fecha=x.fecha) ORDER BY x.fecha,h.hora LIMIT 3000",[$monday,$sunday]) as $w){
    $week[mb_strtolower((string)$w['name']).'|'.tfPhoneKey((string)$w['phone'])][]=['date'=>$w['date'],'class'=>$w['class'],'time'=>$w['time'],'state'=>$state];
   }
  }
  foreach($items as &$it){$it['week']=array_slice($week[mb_strtolower((string)$it['name']).'|'.tfPhoneKey((string)$it['phone'])]??[],0,6);}unset($it);
  return ['success'=>true,'items'=>$items,'has_more'=>$hasMore];
 }
 tfRequire($action==='detail','INVALID_ACTION');$name=trim((string)($r['name']??''));$phone=tfPhoneKey((string)($r['phone']??''));$reference=(string)($r['reference']??'');
 tfRequire(mb_strlen($name)<=100&&strlen($phone)<=20,'INVALID_QUERY');$rows=[];$people=[];
 // Solo los vínculos explícitos se atribuyen a una ficha. El teléfono devuelve coincidencias a revisar.
 if($reference!==''){
  tfRequire(preg_match('/^INNUX:[1-9][0-9]{0,19}$/',$reference)===1,'INVALID_REFERENCE');
  $people=tfQuery($conn,'SELECT id,nombre name,telefono phone FROM tf_people WHERE external_reference=?',[$reference]);
 }
 foreach($people as $p){foreach(tfQuery($conn,"SELECT b.fecha date,b.estado state,h.clase class,h.hora time,p.nombre name,EXISTS(SELECT 1 FROM clases_canceladas c WHERE c.horario_id=b.horario_id AND c.fecha=b.fecha) session_cancelled FROM tf_bookings b JOIN horarios h ON h.id=b.horario_id JOIN tf_people p ON p.id=b.person_id WHERE b.person_id=? ORDER BY b.fecha DESC,h.hora DESC LIMIT 31",[$p['id']]) as $v){$v['verified']=count($people)===1;$rows[]=$v;}}
 $selected=($r['selected']??false)===true;
 if(($phone!==''&&strlen($phone)>=9)||$selected){
  foreach(['inscripciones'=>'RESERVED','inscripciones_cola'=>'WAITLIST'] as $table=>$state){
   foreach(tfQuery($conn,"SELECT x.nombre name,x.fecha date,h.clase class,h.hora time,EXISTS(SELECT 1 FROM clases_canceladas c WHERE c.horario_id=x.horario_id AND c.fecha=x.fecha) session_cancelled FROM $table x JOIN horarios h ON h.id=x.horario_id LEFT JOIN tf_bookings b ON b.".($state==='RESERVED'?'reservation_id':'wait_id')."=x.id LEFT JOIN tf_people p ON p.id=b.person_id WHERE ".tfPhoneSql('x.telefono')."=? AND (?=0 OR x.nombre=?) AND (?='' OR p.external_reference IS NULL OR p.external_reference<>?) ORDER BY x.fecha DESC,h.hora DESC LIMIT 31",[$phone,$selected?1:0,$name,$reference,$reference]) as $v){$v['state']=$state;$v['verified']=false;$rows[]=$v;}
  }
 }
 // Una ficha de Reservas elegida expresamente filtra también por su nombre.
 if($selected)$rows=array_values(array_filter($rows,fn($v)=>mb_strtolower($v['name'])===mb_strtolower($name)));
 usort($rows,fn($a,$b)=>strcmp($b['date'].' '.$b['time'],$a['date'].' '.$a['time']));
 return ['success'=>true,'items'=>array_slice($rows,0,30),'has_more'=>count($rows)>30,'linked'=>count($people)===1];
}
