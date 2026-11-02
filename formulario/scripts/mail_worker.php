<?php
declare(strict_types=1);
/* Envía los correos pendientes (contratos de alta) y sirve de herramienta de pruebas.
   Uso:
     php mail_worker.php                      envía lo pendiente (lo lanza el temporizador cada minuto)
     php mail_worker.php --test destino@x.es  envía un correo de prueba sin tocar contratos
     php mail_worker.php --alert "Asunto" "Texto"   avisa a alert_to (usado por la vigilancia del servidor)
   No guarda ni imprime direcciones de correo, contraseñas ni contenido del contrato. */
require_once dirname(__DIR__).'/app/Service.php';
if(PHP_SAPI!=='cli'){http_response_code(403);exit;}
$root=dirname(__DIR__);$cfg=mailConfig();
if(!$cfg){echo "Correo desactivado o sin configurar (/etc/topfitness-altas/mail.json).\n";exit(0);}
$pwFile=getenv('TF_SMTP_PASSWORD_FILE')?:'';$password=($pwFile!==''&&is_file($pwFile))?rtrim((string)file_get_contents($pwFile),"\r\n"):'';
if($password===''&&empty($cfg['allow_no_auth'])){fwrite(STDERR,"Falta la contraseña SMTP (credencial smtp_password).\n");exit(1);}
$client=fn()=>new SmtpClient($cfg,$password);
$safe=fn(string $m):string=>mb_substr(preg_replace('/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/','<correo>',$m),0,300);

if(($argv[1]??'')==='--test'){
    $to=(string)($argv[2]??'');if(!filter_var($to,FILTER_VALIDATE_EMAIL)){fwrite(STDERR,"Indica un correo de destino válido.\n");exit(2);}
    try{$client()->send($cfg['from_address'],$to,buildPlainEmail($cfg,$to,'Prueba de correo de Top Fitness',"Este es un correo de prueba enviado desde el servidor de altas.\nSi lo lees, el envío funciona.\n"));echo "Correo de prueba enviado.\n";exit(0);}
    catch(Throwable $e){fwrite(STDERR,'Fallo: '.$safe($e->getMessage())."\n");exit(1);}
}
if(($argv[1]??'')==='--alert'){
    $to=(string)($cfg['alert_to']??'');if(!filter_var($to,FILTER_VALIDATE_EMAIL)){fwrite(STDERR,"Falta alert_to en mail.json.\n");exit(2);}
    try{$client()->send($cfg['from_address'],$to,buildPlainEmail($cfg,$to,(string)($argv[2]??'Aviso del servidor'),(string)($argv[3]??'')));echo "Aviso enviado.\n";exit(0);}
    catch(Throwable $e){fwrite(STDERR,'Fallo: '.$safe($e->getMessage())."\n");exit(1);}
}

$s=new Service($root,readConfig($root));$actor='mail-worker';$delays=[2,10,30,120,360];$maxAttempts=6;
$s->transaction(function()use($s){$s->sql("UPDATE email_jobs SET state='RETRY',next_try_at=? WHERE state='SENDING' AND (next_try_at IS NULL OR next_try_at<?)",[instant(),instant()]);});
$jobs=$s->sql("SELECT id FROM email_jobs WHERE state IN ('QUEUED','RETRY') AND (next_try_at IS NULL OR next_try_at<=?) ORDER BY created_at LIMIT 20",[instant()]);
$sent=0;$failed=0;
foreach($jobs as $row){
    $id=$row['id'];
    $attempt=$s->transaction(function()use($s,$id){
        $j=$s->one('SELECT state,attempts FROM email_jobs WHERE id=?',[$id]);if(!$j||!in_array($j['state'],['QUEUED','RETRY'],true))return 0;
        $s->sql("UPDATE email_jobs SET state='SENDING',attempts=attempts+1,next_try_at=? WHERE id=?",[gmdate('Y-m-d\TH:i:s\Z',time()+900),$id]);return (int)$j['attempts']+1;
    });
    if($attempt===0)continue;
    $contractId='';
    try{
        $j=$s->one('SELECT contract_id FROM email_jobs WHERE id=?',[$id]);$contractId=$j['contract_id'];
        $c=$s->one('SELECT * FROM contracts WHERE id=?',[$contractId]);
        if(!$c||$c['state']!=='SIGNED')throw new MailError('El contrato ya no está vigente.',true);
        if($c['is_demo']&&!$s->demo())throw new MailError('Contrato de demostración: no se envía.',true);
        $m=$s->one('SELECT personal_enc FROM members WHERE id=?',[$c['member_id']]);$person=$s->open($m['personal_enc']);
        $to=trim((string)($person['email']??''));if(!filter_var($to,FILTER_VALIDATE_EMAIL))throw new MailError('El socio no tiene un correo válido.',true);
        $pdf=$s->vault->decrypt($c['pdf_enc'],'pdf');if(!hash_equals($c['pdf_hash'],hash('sha256',$pdf)))throw new MailError('El PDF no supera la comprobación de integridad.',true);
        $mime=buildContractEmail($cfg,$to,trim((string)($person['name']??'')),$c['reference'],$pdf);
        $client()->send($cfg['from_address'],$to,$mime);
        $s->transaction(function()use($s,$id,$contractId,$attempt,$actor){$s->sql("UPDATE email_jobs SET state='SENT',sent_at=?,last_error=NULL,next_try_at=NULL WHERE id=?",[instant(),$id]);$s->audit($actor,'EMAIL_SENT',$contractId,['job'=>$id,'attempt'=>$attempt]);});
        $sent++;
    }catch(Throwable $e){
        $permanent=($e instanceof MailError&&$e->permanent)||$attempt>=$maxAttempts;$failed++;
        $s->transaction(function()use($s,$id,$contractId,$attempt,$actor,$permanent,$delays,$safe,$e){
            $next=$permanent?null:gmdate('Y-m-d\TH:i:s\Z',time()+60*$delays[min($attempt-1,count($delays)-1)]);
            $s->sql('UPDATE email_jobs SET state=?,next_try_at=?,last_error=? WHERE id=?',[$permanent?'FAILED':'RETRY',$next,$safe($e->getMessage()),$id]);
            $s->audit($actor,$permanent?'EMAIL_FAILED':'EMAIL_RETRY',$contractId?:$id,['job'=>$id,'attempt'=>$attempt]);
        });
    }
}
// Copias de las solicitudes de baja y mantenimiento (se envían al firmar). Mismos reintentos que los contratos.
$s->transaction(function()use($s){$s->sql("UPDATE withdrawal_email_jobs SET state='RETRY',next_try_at=? WHERE state='SENDING' AND (next_try_at IS NULL OR next_try_at<?)",[instant(),instant()]);});
foreach($s->sql("SELECT id FROM withdrawal_email_jobs WHERE state IN ('QUEUED','RETRY') AND (next_try_at IS NULL OR next_try_at<=?) ORDER BY created_at LIMIT 20",[instant()]) as $row){
    $id=$row['id'];
    $attempt=$s->transaction(function()use($s,$id){
        $j=$s->one('SELECT state,attempts FROM withdrawal_email_jobs WHERE id=?',[$id]);if(!$j||!in_array($j['state'],['QUEUED','RETRY'],true))return 0;
        $s->sql("UPDATE withdrawal_email_jobs SET state='SENDING',attempts=attempts+1,next_try_at=? WHERE id=?",[gmdate('Y-m-d\TH:i:s\Z',time()+900),$id]);return (int)$j['attempts']+1;
    });
    if($attempt===0)continue;
    $withdrawalId='';
    try{
        $withdrawalId=$s->one('SELECT withdrawal_id FROM withdrawal_email_jobs WHERE id=?',[$id])['withdrawal_id'];
        $w=$s->one('SELECT * FROM withdrawals WHERE id=?',[$withdrawalId]);if(!$w)throw new MailError('La solicitud ya no existe.',true);
        $snap=$s->open($w['snapshot_enc']);$to=trim((string)($snap['personal']['email']??''));if(!filter_var($to,FILTER_VALIDATE_EMAIL))throw new MailError('La solicitud no tiene un correo válido.',true);
        $pdf=$s->vault->decrypt($w['pdf_enc'],'pdf');if(!hash_equals($w['pdf_hash'],hash('sha256',$pdf)))throw new MailError('El PDF no supera la comprobación de integridad.',true);
        $client()->send($cfg['from_address'],$to,buildWithdrawalEmail($cfg,$to,trim((string)($snap['personal']['name']??'')),$w['kind'],$w['reference'],$w['effective_date'],$w['last_day'],$pdf));
        $s->transaction(function()use($s,$id,$withdrawalId,$attempt,$actor){$s->sql("UPDATE withdrawal_email_jobs SET state='SENT',sent_at=?,last_error=NULL,next_try_at=NULL WHERE id=?",[instant(),$id]);$s->audit($actor,'EMAIL_SENT',$withdrawalId,['job'=>$id,'attempt'=>$attempt,'kind'=>'withdrawal']);});
        $sent++;
    }catch(Throwable $e){
        $permanent=($e instanceof MailError&&$e->permanent)||$attempt>=$maxAttempts;$failed++;
        $s->transaction(function()use($s,$id,$withdrawalId,$attempt,$actor,$permanent,$delays,$safe,$e){
            $next=$permanent?null:gmdate('Y-m-d\TH:i:s\Z',time()+60*$delays[min($attempt-1,count($delays)-1)]);
            $s->sql('UPDATE withdrawal_email_jobs SET state=?,next_try_at=?,last_error=? WHERE id=?',[$permanent?'FAILED':'RETRY',$next,$safe($e->getMessage()),$id]);
            $s->audit($actor,$permanent?'EMAIL_FAILED':'EMAIL_RETRY',$withdrawalId?:$id,['job'=>$id,'attempt'=>$attempt,'kind'=>'withdrawal']);
        });
    }
}
// Avisos del servidor (los deja la vigilancia en /var/lib/topfitness-altas/alerts). Solo se envían a alert_to.
$alerts=0;$dir='/var/lib/topfitness-altas/alerts';$alertTo=(string)($cfg['alert_to']??'');
if(is_dir($dir)&&filter_var($alertTo,FILTER_VALIDATE_EMAIL)){
    foreach(array_slice(glob($dir.'/*.alert')?:[],0,10) as $file){
        $lines=explode("\n",(string)file_get_contents($file),2);$subject=trim($lines[0])?:'Aviso del servidor';$body=$lines[1]??'';
        try{$client()->send($cfg['from_address'],$alertTo,buildPlainEmail($cfg,$alertTo,'[Top Fitness] '.mb_substr($subject,0,120),$body));unlink($file);$alerts++;}
        catch(Throwable $e){break;} // se reintenta en la siguiente pasada
    }
}
echo "Correos enviados: $sent. Con incidencia: $failed. Avisos: $alerts.\n";
exit($failed>0&&$sent===0?1:0);
