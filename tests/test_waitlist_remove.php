<?php
declare(strict_types=1);
// sudo env TF_RUN_MYSQL_INTEGRATION=1 php tests/test_waitlist_remove.php
if(getenv('TF_RUN_MYSQL_INTEGRATION')!=='1'){fwrite(STDERR,"Prueba MySQL explícita; usa TF_RUN_MYSQL_INTEGRATION=1.\n");exit(2);}
require (getenv('TF_MEMBER_ROOT')?:dirname(__DIR__)).'/web/sso/waitlist.php';
$db=new mysqli('localhost','root','','topfitness_reservas');$db->set_charset('utf8mb4');
foreach(['tf_mutex','inscripciones_cola','inscripciones','tf_bookings','tf_identity_audit'] as $t){
 $ddl=$db->query("SHOW CREATE TABLE `$t`")->fetch_row()[1];if(!str_starts_with($ddl,"CREATE TABLE `$t`"))throw new RuntimeException('Esquema inesperado');
 $ddl=preg_replace('/^CREATE TABLE /','CREATE TEMPORARY TABLE ',$ddl,1);$ddl=preg_replace('/,\n\s*CONSTRAINT[^\n]*/','',$ddl);$db->query($ddl);
}
$db->query('INSERT INTO tf_mutex VALUES(1)');$at='2026-10-26';$passed=0;
$ok=function($v,$m)use(&$passed){if(!$v)throw new RuntimeException($m);$passed++;};
$bad=function($fn,$status)use($ok){try{$fn();}catch(WebError $e){$ok($e->status===$status,'HTTP correcto');return;}$ok(false,'Se aceptó una acción incorrecta');};
$db->query("INSERT INTO inscripciones_cola(id,nombre,telefono,horario_id,fecha,creado_en) VALUES(101,'Ana espera','641827395',1,'$at','2026-01-01 08:00:00'),(102,'Luis espera','652918374',1,'$at','2026-01-01 09:00:00'),(103,'Otra clase','674192835',2,'$at','2026-01-01 08:00:00'),(104,'Cambió a plaza','695182734',1,'$at','2026-01-01 08:00:00'),(105,'Auditoría','681947253',1,'$at','2026-01-01 08:00:00')");
$db->query("INSERT INTO inscripciones(id,nombre,telefono,horario_id,fecha) VALUES(101,'Plaza confirmada','611928374',1,'$at')");
$db->query("INSERT INTO tf_bookings(id,person_id,horario_id,fecha,estado,reservation_id,wait_id) VALUES(201,1,1,'$at','WAITLIST',NULL,101),(202,2,1,'$at','RESERVED',101,NULL),(204,4,1,'$at','RESERVED',NULL,104),(205,5,1,'$at','WAITLIST',NULL,105)");
$active=tfQuery($db,'SELECT * FROM inscripciones');$other=tfQuery($db,'SELECT * FROM inscripciones_cola WHERE id=102')[0];
$r=tfRemoveWaitlist($db,101,1,$at,'qa_total');$ok($r['success']&&$r['removed_id']===101,'Retira espera elegida');$ok(!tfQuery($db,'SELECT * FROM inscripciones_cola WHERE id=101'),'Espera eliminada');
$ok(tfQuery($db,'SELECT * FROM inscripciones')===$active,'La plaza confirmada con el mismo id no cambia');
$linked=tfQuery($db,'SELECT * FROM tf_bookings WHERE id=201')[0];$ok($linked['estado']==='CANCELLED'&&$linked['wait_id']===null&&(int)$linked['version']===2,'Reserva enlazada cancelada y versionada');
$ok(tfQuery($db,'SELECT estado FROM tf_bookings WHERE id=202')[0]['estado']==='RESERVED','No cambia la inscripción confirmada');$ok(tfQuery($db,'SELECT * FROM inscripciones_cola WHERE id=102')[0]===$other,'Conserva el turno y datos de las otras personas');
$a=tfQuery($db,'SELECT * FROM tf_identity_audit')[0];$ok($a['actor']==='qa_total'&&$a['action']==='ADMIN_WAITLIST_REMOVED','Auditoría nominal');$ok((int)json_decode($a['detail_json'],true)['espera']===101,'Auditoría de la entrada exacta');
$r=tfRemoveWaitlist($db,102,1,$at,'qa_total');$ok($r['success'],'También retira entradas antiguas sin vínculo');
$bad(fn()=>tfRemoveWaitlist($db,101,1,$at,'qa_total'),409);$bad(fn()=>tfRemoveWaitlist($db,103,1,$at,'qa_total'),409);$bad(fn()=>tfRemoveWaitlist($db,103,2,'2026-10-27','qa_total'),409);
$ok(count(tfQuery($db,'SELECT id FROM inscripciones_cola WHERE id=103'))===1,'Otra clase o fecha intacta');
$bad(fn()=>tfRemoveWaitlist($db,104,1,$at,'qa_total'),409);$ok(count(tfQuery($db,'SELECT id FROM inscripciones_cola WHERE id=104'))===1,'No quita una entrada que ya figura confirmada');
$bad(fn()=>tfRemoveWaitlist($db,103,2,$at,''),401);$bad(fn()=>tfRemoveWaitlist($db,0,2,$at,'qa_total'),400);$bad(fn()=>tfRemoveWaitlist($db,103,2,'2026-02-31','qa_total'),400);
// Cambiar una columna de la tabla TEMPORARY fuerza el fallo del registro de auditoría.
// No se retira la tabla temporal, por lo que nunca queda expuesta la tabla real.
$db->query('ALTER TABLE tf_identity_audit CHANGE COLUMN actor fixture_actor VARCHAR(100) NOT NULL');
try{tfRemoveWaitlist($db,105,1,$at,'qa_total');$ok(false,'Debe fallar si no puede auditar');}catch(mysqli_sql_exception){$ok(true,'Error de auditoría detectado');}
$ok(count(tfQuery($db,'SELECT id FROM inscripciones_cola WHERE id=105'))===1,'Retirada revertida si falla la auditoría');$ok(tfQuery($db,'SELECT estado FROM tf_bookings WHERE id=205')[0]['estado']==='WAITLIST','Estado enlazado revertido si falla la auditoría');$ok(tfQuery($db,'SELECT * FROM inscripciones')===$active,'Nunca se alteran plazas ni se promociona nadie');
echo "Waitlist removal: $passed passed\n";
