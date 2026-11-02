<?php
require __DIR__.'/bootstrap.php';
// Socio conocido del sistema: lo creamos firmando un alta en la copia.
altaDraft($s,['personal'=>['document'=>'12345678Z','birth_date'=>'1985-05-20','name'=>'Laura','surname'=>'Conocida','email'=>'laura@example.com']]);
$prep=$s->prepareContract();$alta=$s->signContract(['confirmed'=>true,'review_hash'=>$prep['review_hash'],'signature'=>SIG]);
$memberId=$s->one('SELECT member_id FROM contracts WHERE id=?',[$alta['id']])['member_id'];
$number=$s->one('SELECT innux_number FROM members WHERE id=?',[$memberId])['innux_number'];

// (a) socio conocido, fecha correcta → encontrado
kiosk();$s->withdrawalStart('MAINTENANCE');
$id=$s->withdrawalIdentify(['document_type'=>'DNI','document'=>'12345678z','birth_date'=>'1985-05-20']);
eq($id['found'],true,'conocido: encontrado');eq($id['name'],'Laura Conocida','conocido: nombre');eq($id['member_number'],$number,'conocido: n.º socio');
ok(str_contains((string)$id['email_hint'],'@example.com')&&!str_contains((string)$id['email_hint'],'laura@'),'conocido: correo enmascarado');
// (a2) mismo DNI, fecha errónea → no revela nada
kiosk();$s->withdrawalStart('PERMANENT');
$bad=$s->withdrawalIdentify(['document_type'=>'DNI','document'=>'12345678Z','birth_date'=>'1985-05-21']);
eq($bad['found'],false,'fecha errónea: no encontrado');eq($bad['name'],null,'fecha errónea: sin nombre');

// Firma del mantenimiento del socio conocido
kiosk();$s->withdrawalStart('MAINTENANCE');$s->withdrawalIdentify(['document_type'=>'DNI','document'=>'12345678Z','birth_date'=>'1985-05-20']);
$s->withdrawalSave(['reason'=>'injury','reason_text'=>'Rodilla']);
$p=$s->withdrawalPrepare();$dates=withdrawalDates(madridToday());
eq($p['summary']['effective_date'],$dates['effective_date'],'efecto: día 1 del mes siguiente');
eq($p['summary']['last_day'],$dates['last_day'],'último día de entrenamiento');
eq($p['summary']['fee_cents_per_month'],500,'recargo mantenimiento');
$r=$s->withdrawalSign(['confirmed'=>true,'review_hash'=>$p['review_hash'],'signature'=>SIG]);
$w=$s->one('SELECT * FROM withdrawals WHERE id=?',[$r['id']]);
eq($w['state'],'PENDING','queda pendiente');eq($w['kind'],'MAINTENANCE','tipo');eq($w['member_id'],$memberId,'vinculada al socio');
eq($w['effective_date'],$dates['effective_date'],'efecto guardado');
ok(preg_match('/^TF-B-\d{4}-[0-9A-F]{12}$/',$w['reference'])===1,'referencia TF-B');
eq($s->one("SELECT COUNT(*) n FROM withdrawal_email_jobs WHERE withdrawal_id=? AND state='QUEUED'",[$r['id']])['n'],1,'correo encolado');
eq($s->one('SELECT state FROM members WHERE id=?',[$memberId])['state'],'ACTIVE','el socio no cambia hasta que se acepta');
$pdf=$s->vault->decrypt($w['pdf_enc'],'pdf');ok(hash_equals($w['pdf_hash'],hash('sha256',$pdf)),'hash del PDF');
file_put_contents('/var/tmp/tf-bajas-out/mantenimiento.pdf',$pdf);
file_put_contents('/var/tmp/tf-bajas-out/mantenimiento.expect',"MANTENIMIENTO\n".$w['reference']."\n".date('d-m-Y',strtotime($dates['effective_date']))."\n5,00 €\nLaura\n");
eq($s->withdrawalDocument($r['id']),$pdf,'el kiosco descarga su propio PDF');
throws(fn()=>$s->withdrawalDocument('otro'),'',"no descarga PDFs ajenos");

// (c) segunda solicitud pendiente para el mismo documento
kiosk();$s->withdrawalStart('PERMANENT');
throws(fn()=>$s->withdrawalIdentify(['document_type'=>'DNI','document'=>'12345678Z','birth_date'=>'1985-05-20']),'pendiente','duplicada rechazada');

// (b) socio en papel: no está en la BD
kiosk();$s->withdrawalStart('PERMANENT');
$n=$s->withdrawalIdentify(['document_type'=>'DNI','document'=>'87654321X','birth_date'=>'1970-02-02']);
eq($n['found'],false,'papel: no encontrado');
throws(fn()=>$s->withdrawalSave(['name'=>'Pepe']),'',"papel: faltan datos obligatorios");
$s->withdrawalSave(['name'=>'Pepe','surname'=>'De Papel','phone'=>'611 222 333','email'=>'Pepe@Example.com','member_number'=>'1234','reason'=>'price']);
$p2=$s->withdrawalPrepare();
// (d) firma con hash cambiado
throws(fn()=>$s->withdrawalSign(['confirmed'=>true,'review_hash'=>str_repeat('0',64),'signature'=>SIG]),'cambiado','hash distinto rechazado');
throws(fn()=>$s->withdrawalSign(['confirmed'=>false,'review_hash'=>$p2['review_hash'],'signature'=>SIG]),'Confirma','sin confirmar rechazado');
$r2=$s->withdrawalSign(['confirmed'=>true,'review_hash'=>$p2['review_hash'],'signature'=>SIG]);
$w2=$s->one('SELECT * FROM withdrawals WHERE id=?',[$r2['id']]);
eq($w2['member_id'],null,'papel: sin socio vinculado');eq($w2['kind'],'PERMANENT','papel: baja definitiva');
$snap=$s->open($w2['snapshot_enc']);eq($snap['personal']['email'],'pepe@example.com','correo normalizado');eq($snap['member_number'],'1234','n.º de socio indicado');
file_put_contents('/var/tmp/tf-bajas-out/baja.pdf',$s->vault->decrypt($w2['pdf_enc'],'pdf'));
file_put_contents('/var/tmp/tf-bajas-out/baja.expect',"BAJA DEFINITIVA\nPepe\n".date('d-m-Y',strtotime($dates['last_day']))."\n");
// contenido firmado inmutable
throws(fn()=>$s->sql('UPDATE withdrawals SET kind=? WHERE id=?',['MAINTENANCE',$r2['id']]),'immutable','no se puede cambiar lo firmado');
throws(fn()=>$s->sql('DELETE FROM withdrawals WHERE id=?',[$r2['id']]),'immutable','no se puede borrar');
// sin sesión de kiosco no se puede
$_SESSION=['csrf'=>'x'];throws(fn()=>$s->withdrawalStart('PERMANENT'),'recepción','requiere kiosco');
done();
