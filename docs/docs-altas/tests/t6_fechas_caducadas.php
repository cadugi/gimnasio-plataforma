<?php
require __DIR__.'/bootstrap.php';
// Si cambia el mes entre la revisión y la firma, las fechas ya no valen: hay que revisar de nuevo.
kiosk();$s->withdrawalStart('PERMANENT');$s->withdrawalIdentify(['document_type'=>'DNI','document'=>'33333333P','birth_date'=>'1990-01-01']);
$s->withdrawalSave(['name'=>'Fede','surname'=>'Fechas','phone'=>'600000001','email'=>'fede@example.com']);$s->withdrawalPrepare();
$_SESSION['withdrawal']['snapshot']['last_day']='2000-01-31';$_SESSION['withdrawal']['snapshot']['effective_date']='2000-02-01';
$_SESSION['withdrawal']['review_hash']=hash('sha256',jencode($_SESSION['withdrawal']['snapshot']));
throws(fn()=>$s->withdrawalSign(['confirmed'=>true,'review_hash'=>$_SESSION['withdrawal']['review_hash'],'signature'=>SIG]),'Revísala','fechas caducadas obligan a revisar');
eq($s->one("SELECT COUNT(*) n FROM withdrawals WHERE last_day='2000-01-31'")['n'],0,'no se guarda');
done();
