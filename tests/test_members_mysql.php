<?php
declare(strict_types=1);
require (getenv('TF_MEMBER_ROOT')?:dirname(__DIR__)).'/web/sso/members.php';
// Tablas TEMPORARY privadas de esta conexión: nunca se insertan personas o reservas reales.
$conn=new mysqli('localhost','root','','topfitness_reservas');$conn->set_charset('utf8mb4');$passed=0;
$ok=function($v,$label)use(&$passed){if(!$v)throw new RuntimeException($label);$passed++;};
foreach([
 'tf_people'=>'id INT,nombre VARCHAR(100),telefono VARCHAR(20),external_reference VARCHAR(100)',
 'horarios'=>'id INT,clase VARCHAR(60),hora VARCHAR(20)',
 'clases_canceladas'=>'horario_id INT,fecha DATE',
 'inscripciones'=>'id INT,nombre VARCHAR(100),telefono VARCHAR(20),horario_id INT,fecha DATE',
 'inscripciones_cola'=>'id INT,nombre VARCHAR(100),telefono VARCHAR(20),horario_id INT,fecha DATE',
 'tf_bookings'=>'person_id INT,horario_id INT,fecha DATE,estado VARCHAR(20),reservation_id INT,wait_id INT'
] as $t=>$columns)$conn->query("CREATE TEMPORARY TABLE $t($columns) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
$conn->query("INSERT INTO tf_people VALUES(1,'Ana García','612345678','INNUX:101'),(2,'Luis García','+34 612 345 678',NULL),(3,'Solo reservas','611111111','')");
$conn->query("INSERT INTO horarios VALUES(1,'Yoga','09:00-10:00')");
$conn->query("INSERT INTO inscripciones VALUES(1,'Ana García','612345678',1,'2026-10-24'),(2,'Luis García','+34 612 345 678',1,'2026-10-24'),(3,'Solo reservas','611111111',1,'2026-10-24')");
$conn->query("INSERT INTO tf_bookings VALUES(1,1,'2026-10-24','RESERVED',1,NULL),(2,1,'2026-10-24','RESERVED',2,NULL),(3,1,'2026-10-24','RESERVED',3,NULL)");
$r=tfMemberRead($conn,['query'=>'ana garcia']);$ok(count($r['items'])===1,'Nombre sin tildes');$r=tfMemberRead($conn,['query'=>'612345678']);$ok(count($r['items'])===2,'Buscar teléfono con formatos distintos');
$r=tfMemberRead($conn,['query'=>"' OR 1=1 --"]);$ok(!$r['items'],'SQL no se interpreta');$ok(!tfMemberRead($conn,['query'=>'%%'])['items'],'Porcentaje literal, no comodín');
$r=tfMemberRead($conn,['action'=>'detail','reference'=>'INNUX:101','phone'=>'612345678','name'=>'Ana García']);$ok(count($r['items'])===2,'Reserva vinculada más coincidencia familiar');$ok(count(array_filter($r['items'],fn($v)=>$v['verified']))===1,'Solo vínculo explícito verificado');
$r=tfMemberRead($conn,['action'=>'detail','phone'=>'612345678','name'=>'Luis García','selected'=>true]);$ok(count($r['items'])===1&&$r['items'][0]['name']==='Luis García','Seleccionar persona no mezcla familiares');
$r=tfMemberRead($conn,['action'=>'detail','phone'=>'611111111','name'=>'Solo reservas','selected'=>true]);$ok(count($r['items'])===1,'Referencia vacía no oculta reserva');
$conn->query("INSERT INTO clases_canceladas VALUES(1,'2026-10-24')");$r=tfMemberRead($conn,['action'=>'detail','reference'=>'INNUX:101','phone'=>'']);$ok((int)$r['items'][0]['session_cancelled']===1,'Clase cancelada visible');
$conn->query("INSERT INTO tf_people VALUES(4,'Otro vínculo','699999999','INNUX:101')");$r=tfMemberRead($conn,['action'=>'detail','reference'=>'INNUX:101','phone'=>'']);$ok(!$r['linked']&&!$r['items'][0]['verified'],'Vínculo duplicado requiere revisión');
$conn->query("INSERT INTO inscripciones VALUES(4,'Teléfono antiguo','12',1,'2026-10-24'),(5,'Sin teléfono','',1,'2026-10-24')");
$r=tfMemberRead($conn,['action'=>'detail','phone'=>'12','name'=>'Teléfono antiguo','selected'=>true]);$ok(count($r['items'])===1,'Reserva histórica con teléfono corto consultable sin vincular');
$r=tfMemberRead($conn,['action'=>'detail','phone'=>'','name'=>'Sin teléfono','selected'=>true]);$ok(count($r['items'])===1,'Reserva histórica sin teléfono consultable por selección expresa');
$ok((int)$conn->query('SELECT COUNT(*) n FROM inscripciones')->fetch_assoc()['n']===5,'Lecturas no escriben reservas');
echo "Reservations members: $passed passed\n";
