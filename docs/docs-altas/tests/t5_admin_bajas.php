<?php
require __DIR__.'/bootstrap.php';
// Socio con domiciliación, aceptado por el centro.
$s->sql("INSERT INTO settings(name,value) VALUES('creditor',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",[json_encode(['name'=>'Top Fitness Prueba','id'=>'ES00ZZZ00000000'])]);
altaDraft($s,['personal'=>['document'=>'11111111H','birth_date'=>'1980-03-03','name'=>'Dora','surname'=>'Domiciliada'],'payment_method'=>'debit','bank'=>['holder_same'=>true,'iban'=>'ES9121000418450200051332','holder'=>'Dora Domiciliada'],'consents'=>['sepa'=>true]]);
$prep=$s->prepareContract();$alta=$s->signContract(['confirmed'=>true,'review_hash'=>$prep['review_hash'],'signature'=>SIG]);
$c=$s->one('SELECT * FROM contracts WHERE id=?',[$alta['id']]);$member=$c['member_id'];
staff($s);$s->acceptContract($alta['id']);
// Mantenimiento firmado en la tablet
kiosk();$s->withdrawalStart('MAINTENANCE');$s->withdrawalIdentify(['document_type'=>'DNI','document'=>'11111111H','birth_date'=>'1980-03-03']);$s->withdrawalSave([]);
$p=$s->withdrawalPrepare();$w=$s->withdrawalSign(['confirmed'=>true,'review_hash'=>$p['review_hash'],'signature'=>SIG]);
// Baja definitiva de alguien en papel (para rechazarla)
kiosk();$s->withdrawalStart('PERMANENT');$s->withdrawalIdentify(['document_type'=>'DNI','document'=>'22222222J','birth_date'=>'1975-01-01']);
$s->withdrawalSave(['name'=>'Rita','surname'=>'Rechazada','phone'=>'600111222','email'=>'rita@example.com']);$p2=$s->withdrawalPrepare();$w2=$s->withdrawalSign(['confirmed'=>true,'review_hash'=>$p2['review_hash'],'signature'=>SIG]);

staff($s);
$d=$s->dashboard();ok(($d['pending_withdrawals']??0)>=2,'panel: bajas pendientes');
$list=$s->withdrawalList([]);$row=array_values(array_filter($list,fn($r)=>$r['id']===$w['id']))[0]??null;
ok($row!==null,'lista: aparece');eq($row['name']??null,'Dora Domiciliada','lista: nombre');eq($row['state']??null,'PENDING','lista: pendiente');
$det=$s->withdrawalDetail($w['id']);eq($det['kind'],'MAINTENANCE','detalle: tipo');eq($det['member_linked'],true,'detalle: vinculada');eq($det['default_tariff_id'],$c['tariff_id'],'detalle: tarifa por defecto');
throws(fn()=>$s->withdrawalReturn($w['id'],'2027-02-10',$c['tariff_id']),'aceptado','no se registra vuelta sin aceptar');
throws(fn()=>$s->rejectWithdrawal($w2['id'],''),'motivo','rechazar exige motivo');
$s->rejectWithdrawal($w2['id'],'Datos duplicados');eq($s->one('SELECT state FROM withdrawals WHERE id=?',[$w2['id']])['state'],'REJECTED','rechazada');
$s->acceptWithdrawal($w['id']);
eq($s->one('SELECT state FROM withdrawals WHERE id=?',[$w['id']])['state'],'ACCEPTED','aceptada');
eq($s->one('SELECT state FROM members WHERE id=?',[$member])['state'],'MAINTENANCE','socio en mantenimiento');
throws(fn()=>$s->acceptWithdrawal($w['id']),'pendiente','no se acepta dos veces');
// Cuotas: el mes de efecto no se le cobra
$eff=$s->one('SELECT effective_date FROM withdrawals WHERE id=?',[$w['id']])['effective_date'];$P=substr($eff,0,7);
$s->prepareDues(['period'=>$P,'due_date'=>$P.'-05']);
eq($s->one('SELECT COUNT(*) n FROM dues WHERE member_id=? AND period=?',[$member,$P])['n'],0,'sin cuota durante el mantenimiento');
// Vuelta 3 meses y 9 días después del efecto
$ret=(new DateTimeImmutable($eff))->modify('+3 months')->modify('+9 days')->format('Y-m-d');
$v=$s->withdrawalReturn($w['id'],$ret,$c['tariff_id']);
$monthly=(int)$s->one('SELECT monthly_cents FROM tariffs WHERE id=?',[$c['tariff_id']])['monthly_cents'];
eq($v['months'],3,'vuelta: 3 meses');eq($v['fee_cents'],1500,'vuelta: 15 €');eq($v['renewal_cents'],prorateMonth($monthly,$ret)['cents'],'vuelta: renovación prorrateada');
eq($v['total_cents'],1500+prorateMonth($monthly,$ret)['cents'],'vuelta: total');
eq($s->one('SELECT state FROM members WHERE id=?',[$member])['state'],'ACTIVE','socio activo de nuevo');
throws(fn()=>$s->withdrawalReturn($w['id'],$ret,$c['tariff_id']),'vuelta','no se registra la vuelta dos veces');
// El mes de vuelta lo paga en recepción; las cuotas siguen el mes siguiente
$RP=substr($ret,0,7);$NP=(new DateTimeImmutable($ret))->modify('first day of next month')->format('Y-m');
$s->prepareDues(['period'=>$RP,'due_date'=>$RP.'-20']);eq($s->one('SELECT COUNT(*) n FROM dues WHERE member_id=? AND period=?',[$member,$RP])['n'],0,'mes de vuelta sin cuota automática');
$s->prepareDues(['period'=>$NP,'due_date'=>$NP.'-05']);eq($s->one('SELECT COUNT(*) n FROM dues WHERE member_id=? AND period=?',[$member,$NP])['n'],1,'cuotas de nuevo tras la vuelta');
// Permisos: consulta ve pero no acepta
staff($s,'viewer');ok(count($s->withdrawalList([]))>=2,'consulta: ve la lista');throws(fn()=>$s->acceptWithdrawal($w2['id']),'permiso','consulta: no acepta');
// El PDF lo descarga el personal
staff($s);ok(str_starts_with($s->withdrawalDocument($w['id']),'%PDF'),'personal descarga el PDF');
done();
