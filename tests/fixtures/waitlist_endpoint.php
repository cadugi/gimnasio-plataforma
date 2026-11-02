<?php
declare(strict_types=1);
// Ejecutar solo con el árbol de pruebas privado preparado por test_waitlist_endpoint.py.
$root=getenv('TF_WAITLIST_FIXTURE_ROOT');if(!$root||!is_file($root.'/fixture-only'))exit(2);
$r=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
require $root.'/public/conexion.php';
foreach(['horarios','inscripciones','inscripciones_cola','clases_canceladas','tf_mutex','tf_identity_audit'] as $table){
 $ddl=$conn->query("SHOW CREATE TABLE `$table`")->fetch_row()[1];
 if(!str_starts_with($ddl,"CREATE TABLE `$table`"))throw new RuntimeException('Esquema inesperado');
 $ddl=preg_replace('/^CREATE TABLE /','CREATE TEMPORARY TABLE ',$ddl,1);
 $ddl=preg_replace('/,\n\s*CONSTRAINT[^\n]*/','',$ddl); // las tablas privadas no referencian personas reales
 $conn->query($ddl);
}
$conn->query('INSERT INTO tf_mutex(id) VALUES(1)');
$date=$r['date']??'2030-01-07';$limit=(int)($r['limit']??2);$days=['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];$day=$days[(int)(new DateTimeImmutable($date))->format('w')];
$st=$conn->prepare("INSERT INTO horarios(id,clase,dia,hora,limite) VALUES(1,'YOGA',?,'23:58-23:59',?)");$st->bind_param('si',$day,$limit);$st->execute();
$tables=['occupied'=>'inscripciones','waiting'=>'inscripciones_cola'];
foreach($tables as $key=>$table)foreach($r[$key]??[] as $index=>$v){
 $name=$v['name'];$phone=$v['phone'];$d=$v['date']??$date;$created=$v['created']??'2020-01-01 08:00:00';
 $st=$conn->prepare("INSERT INTO $table(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,1,?,?)");$st->bind_param('ssss',$name,$phone,$d,$created);$st->execute();
}
$_POST=['nombre'=>$r['name']??'Persona nueva','telefono'=>$r['phone']??'674192835','horario_id'=>'1','fecha'=>$date];if($r['force']??false)$_POST['confirmar_exceso']='1';
$_SERVER['REMOTE_USER']=($r['admin']??true)?'qa_total':'';
register_shutdown_function(function()use($conn){
 $stats=['http'=>http_response_code()?:200,'occupied'=>(int)$conn->query('SELECT COUNT(*) n FROM inscripciones')->fetch_assoc()['n'],'waiting'=>(int)$conn->query('SELECT COUNT(*) n FROM inscripciones_cola')->fetch_assoc()['n'],'actors'=>array_column($conn->query('SELECT actor FROM tf_identity_audit')->fetch_all(MYSQLI_ASSOC),'actor')];
 echo "\n__FIXTURE__".json_encode($stats);
});
if($r['bulk']??false){$_POST['sesiones']=json_encode([['horario_id'=>1,'fecha'=>$date]]);require $root.'/public/admin_inscribir_multiple.php';}
else require $root.'/sso/admin_legacy_inscribir_cliente.php';
