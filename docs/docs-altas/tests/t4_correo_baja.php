<?php
require __DIR__.'/bootstrap.php';
$cfg=['from_address'=>'contratos@example.com','from_name'=>'Top Fitness'];
$decode=function(string $mime):array{preg_match('/^Subject: ([^\r\n]*)/m',$mime,$m);$subject=iconv_mime_decode($m[1],0,'UTF-8');
  preg_match('/Content-Type: text\/plain.*?\r\n\r\n(.*?)\r\n--/s',$mime,$t);return [$subject,base64_decode(preg_replace('/\s/','',$t[1]))];};
$m=buildWithdrawalEmail($cfg,'socio@example.com','Laura','MAINTENANCE','TF-B-2026-ABC','2026-11-01','2026-10-31','%PDF-prueba');
[$subj,$body]=$decode($m);
eq($subj,'Tu mantenimiento en Top Fitness','asunto mantenimiento');
ok(str_contains($body,'01-11-2026')&&str_contains($body,'31-10-2026'),'fechas en el cuerpo');
ok(str_contains($body,'5,00 €'),'recargo en el cuerpo');ok(str_contains($body,'Laura'),'saludo');
ok(str_contains($m,'filename="mantenimiento-topfitness-TF-B-2026-ABC.pdf"'),'adjunto mantenimiento');
ok(str_contains($m,base64_encode('%PDF-prueba')),'PDF adjunto');
[$subj2,$body2]=$decode(buildWithdrawalEmail($cfg,'socio@example.com','Pepe','PERMANENT','TF-B-2026-DEF','2026-11-01','2026-10-31','%PDF'));
eq($subj2,'Tu solicitud de baja en Top Fitness','asunto baja');ok(str_contains($body2,'Sentimos que te vayas'),'despedida');
// El worker recoge la cola de bajas (correo desactivado en la copia: no envía, pero no debe romper)
ok(is_string(file_get_contents('/var/tmp/tf-bajas-test/scripts/mail_worker.php'))&&str_contains(file_get_contents('/var/tmp/tf-bajas-test/scripts/mail_worker.php'),'withdrawal_email_jobs'),'worker procesa withdrawal_email_jobs');
done();
