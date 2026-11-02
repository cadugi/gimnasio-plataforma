<?php
declare(strict_types=1);
function tfProfile(mysqli $db,int $person):array{$data=json_decode(tfQuery($db,'SELECT data_json FROM tf_preferences WHERE person_id=?',[$person])[0]['data_json']??'{}',true);$data+=['favorites'=>[],'routine_ids'=>[],'weekly_summary'=>false];$data['routines']=[];foreach($data['routine_ids'] as $id){$h=tfQuery($db,'SELECT id,clase,dia,hora,limite FROM horarios WHERE id=?',[$id])[0]??null;if($h){$h['id']=(int)$h['id'];$data['routines'][]=$h;}}return $data;}
function tfRead(mysqli $db,string $principal,int $person,array $r):array{
 $a=$r['action'];$today=tfNow()->format('Y-m-d');$dates=[];for($i=0;$i<=5;$i++)$dates[]=tfNow()->setTime(0,0)->modify("+$i days")->format('Y-m-d');
 if($a==='dates')return ['ok'=>true,'dates'=>$dates];
 if(in_array($a,['outbox_claim','outbox_ack'],true))return ['ok'=>true,'events'=>[]];
 $bookings=fn()=>array_map(fn($b)=>tfDescribe($db,(int)$b['id']),tfQuery($db,"SELECT id FROM tf_bookings WHERE person_id=? AND estado IN ('RESERVED','WAITLIST') AND fecha>=? ORDER BY fecha,horario_id",[$person,$today]));
 if($a==='list')return ['ok'=>true,'bookings'=>$bookings(),'now'=>tfNow()->format(DATE_ATOM)];
 if($a==='home'){$bs=$bookings();return ['ok'=>true,'bookings'=>$bs,'confirmed'=>count(array_filter($bs,fn($b)=>$b['estado']==='RESERVED')),'waiting'=>count(array_filter($bs,fn($b)=>$b['estado']==='WAITLIST'))];}
 if($a==='catalog')return ['ok'=>true,'classes'=>array_column(tfQuery($db,'SELECT DISTINCT clase FROM horarios ORDER BY clase'),'clase')];
 $profile=tfProfile($db,$person);
 if($a==='profile')return ['ok'=>true,'profile'=>$profile,'now'=>tfNow()->format(DATE_ATOM)];
 if(in_array($a,['set_favorite','set_routine','set_weekly_summary'],true)){
  return tfAtomic($db,function()use($db,$person,$r,$a){$p=tfProfile($db,$person);$enable=($r['enabled']??false)===true;
   if($a==='set_favorite'){$class=(string)($r['clase']??'');tfRequire(tfQuery($db,'SELECT id FROM horarios WHERE clase=?',[$class]),'SCHEDULE_NOT_FOUND');$p['favorites']=array_values(array_diff($p['favorites'],[$class]));if($enable)$p['favorites'][]=$class;}
   elseif($a==='set_routine'){
    $id=(int)($r['horario_id']??0);$target=tfQuery($db,'SELECT id,dia FROM horarios WHERE id=?',[$id])[0]??null;tfRequire($target,'SCHEDULE_NOT_FOUND');
    $p['routine_ids']=array_values(array_diff($p['routine_ids'],[$id]));
    if($enable){$owner=tfPerson($db,$person);$total=0;$daily=0;foreach(tfQuery($db,'SELECT id FROM tf_people WHERE telefono=?',[$owner['telefono']]) as $member){$profile=tfProfile($db,(int)$member['id']);foreach($profile['routines'] as $h){if((int)$member['id']===$person&&(int)$h['id']===$id)continue;$total++;if($h['dia']===$target['dia'])$daily++;}}tfRequire($total<5,'ROUTINE_PHONE_LIMIT');tfRequire($daily<3,'ROUTINE_DAY_LIMIT');$p['routine_ids'][]=$id;}
   }
   else $p['weekly_summary']=$enable;
   unset($p['routines']);tfQuery($db,'INSERT INTO tf_preferences VALUES(?,?) ON DUPLICATE KEY UPDATE data_json=VALUES(data_json)',[$person,json_encode($p)]);return ['ok'=>true,'profile'=>tfProfile($db,$person)];});
 }
 if($a==='weekly_summary'){[$from,$until]=tfWeek($today);$bs=array_values(array_filter($bookings(),fn($b)=>$b['fecha']>=$from&&$b['fecha']<=$until));return ['ok'=>true,'from'=>$from,'until'=>$until,'bookings'=>$bs,'confirmed'=>count(array_filter($bs,fn($b)=>$b['estado']==='RESERVED')),'waiting'=>count(array_filter($bs,fn($b)=>$b['estado']==='WAITLIST')),'profile'=>$profile];}
 if($a==='routine_week'){$days=['lunes','martes','miercoles','jueves','viernes','sabado','domingo'];$day=$r['dia']??'';if(is_numeric($day))$day=$days[(int)$day-1]??'';$hs=tfQuery($db,'SELECT id,clase,dia,hora,limite FROM horarios WHERE dia=? ORDER BY hora,id',[$day]);foreach($hs as &$h){$h['id']=(int)$h['id'];$h['limite']=(int)$h['limite'];$h['disponibles']=$h['limite'];}return ['ok'=>true,'schedules'=>$hs,'profile'=>$profile];}
 if(in_array($a,['schedules','routine_plan','favorite_sessions','alternatives'],true)){
  $result=[];$selected=$a==='schedules'?[(string)($r['fecha']??'')]:$dates;
  foreach($selected as $date)foreach(tfQuery($db,'SELECT id FROM horarios ORDER BY hora,id') as $row){try{$h=tfSchedule($db,(int)$row['id'],$date);}catch(WebError $e){continue;}if($h['limite']<=0)continue;if($a==='routine_plan'&&!in_array($h['id'],$profile['routine_ids']))continue;if($a==='favorite_sessions'&&!in_array($h['clase'],$profile['favorites']))continue;if($a==='alternatives'&&($h['disponibles']<=0||$h['id']===(int)($r['horario_id']??0)))continue;$result[]=$h;}
  return ['ok'=>true,'schedules'=>$result,'profile'=>$profile];
 }
 throw new WebError('UNKNOWN_ACTION');
}
