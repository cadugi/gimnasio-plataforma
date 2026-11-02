<?php
require __DIR__.'/bootstrap.php';
// Fichas ficticias en la COPIA de la BD.
function addMember(Service $s,string $name,string $surname,string $phone,string $state='ACTIVE'):string{
  $id=bin2hex(random_bytes(16));$doc=(string)random_int(10000000,99999999);
  $s->sql('INSERT INTO members(id,internal_reference,personal_enc,document_fingerprint,state,created_at) VALUES(?,?,?,?,?,?)',[$id,'TF-T'.substr($id,0,8),$s->seal(['name'=>$name,'surname'=>$surname,'phone'=>$phone,'email'=>'']),'fp'.$doc.$id,$state,instant()]);return $id;}
$a=addMember($s,'Ángela','Pérez Ruiz','612 345 678');
$b=addMember($s,'Luis','Gómez','+34 622-111-222');
$c1=addMember($s,'Marta','Díaz','633444555');$c2=addMember($s,'Marta','Díaz','0034 633 444 555');
$d=addMember($s,'Baja','Antigua','644000111','BAJA');
$f=addMember($s,'Juan','López','655000222');$g=addMember($s,'Juan','López','655000333');
eq($s->memberMatch(['name'=>'  ANGELA   perez ruiz','phone'=>'+34612345678']),['result'=>'ONE','ref'=>$a],'tildes, mayúsculas, espacios y prefijo');
eq($s->memberMatch(['name'=>'Luis Gómez','phone'=>'0034622111222']),['result'=>'ONE','ref'=>$b],'0034 y guiones');
eq($s->memberMatch(['name'=>'Marta Diaz','phone'=>'633 444 555']),['result'=>'MANY'],'ficha duplicada = revisión');
eq($s->memberMatch(['name'=>'Ángela Pérez','phone'=>'612345678']),['result'=>'NONE'],'nombre parcial NO coincide (sin aproximación)');
eq($s->memberMatch(['name'=>'Angela Perez Ruiz','phone'=>'612345679']),['result'=>'NONE'],'un dígito distinto');
eq($s->memberMatch(['name'=>'Baja Antigua','phone'=>'644000111']),['result'=>'NONE'],'ficha no activa');
eq($s->memberMatch(['name'=>'Juan López','phone'=>'655000222']),['result'=>'ONE','ref'=>$f],'mismo nombre, distinto teléfono: no se mezclan');
eq(array_keys($s->memberMatch(['name'=>'Luis Gómez','phone'=>'622111222'])),['result','ref'],'solo resultado y referencia');
throws(fn()=>$s->memberMatch(['name'=>'Ana','phone'=>'123']),'Datos no válidos','teléfono inválido');
throws(fn()=>$s->memberMatch(['name'=>'','phone'=>'612345678']),'Datos no válidos','nombre vacío');
// Autorización por token de servicio
$s->sql("INSERT OR REPLACE INTO settings(name,value) VALUES('reservas_match_token_hash',?)",[hash('sha256','tok-correcto')]);
$s->matchAuthorize('tok-correcto');ok(true,'token válido');
throws(fn()=>$s->matchAuthorize('otro'),'No autorizado','token erróneo');
throws(fn()=>$s->matchAuthorize(''),'No autorizado','token vacío');
$s->sql("DELETE FROM settings WHERE name='reservas_match_token_hash'");
throws(fn()=>$s->matchAuthorize('tok-correcto'),'No autorizado','sin token configurado = cerrado');
done();
