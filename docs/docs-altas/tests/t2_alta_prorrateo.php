<?php
require __DIR__.'/bootstrap.php';
altaDraft($s);
$prep=$s->prepareContract();
$t=$s->one("SELECT * FROM tariffs WHERE active=1 AND brand='fitness' ORDER BY monthly_cents DESC LIMIT 1");
$p=prorateMonth((int)$t['monthly_cents'],madridToday());
eq($prep['summary']['first_month_cents']??null,$p['cents'],'resumen: primer mes prorrateado');
eq($prep['summary']['initial_cents'],$p['cents']+(int)$t['enrollment_cents'],'resumen: total = prorrateo + matrícula');
eq($prep['summary']['monthly_cents'],(int)$t['monthly_cents'],'la cuota mensual sigue completa');
$r=$s->signContract(['confirmed'=>true,'review_hash'=>$prep['review_hash'],'signature'=>SIG]);
$c=$s->one('SELECT * FROM contracts WHERE id=?',[$r['id']]);
eq((int)$c['initial_cents'],$p['cents']+(int)$t['enrollment_cents'],'contrato guardado con total prorrateado');
$snap=$s->open($c['snapshot_enc']);
eq($snap['first_month_from']??null,date('d-m-Y',strtotime($p['from'])),'snapshot: desde');
eq($snap['first_month_to']??null,date('d-m-Y',strtotime($p['to'])),'snapshot: hasta');
file_put_contents('/var/tmp/tf-bajas-out/alta.pdf',$s->vault->decrypt($c['pdf_enc'],'pdf'));
file_put_contents('/var/tmp/tf-bajas-out/alta.expect',"Primer mes\n".centsString($p['cents'])."\n");
done();
