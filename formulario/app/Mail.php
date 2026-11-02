<?php
declare(strict_types=1);
/* Envío de correos de la aplicación de altas.
   PHP-FPM está aislado sin red; el envío lo hace scripts/mail_worker.php, un servicio aparte.
   Aquí solo hay: configuración, cola y un cliente SMTP mínimo con TLS verificado. */

function mailConfigPath():string{return getenv('TF_MAIL_CONFIG')?:'/etc/topfitness-altas/mail.json';}
function mailConfig():?array{
    $path=mailConfigPath();if(!is_file($path)||!is_readable($path))return null;
    $c=json_decode((string)file_get_contents($path),true);if(!is_array($c)||($c['enabled']??false)!==true)return null;
    foreach(['host','port','security','username','from_address'] as $k)if(empty($c[$k]))return null;
    if(!in_array($c['security'],['ssl','starttls'],true)||!filter_var($c['from_address'],FILTER_VALIDATE_EMAIL))return null;
    return $c;
}

trait MailOperations {
    public function mailEnabled():bool{return mailConfig()!==null;}
    /** Encola el contrato para enviarlo por correo. Con $force permite reenviar un contrato ya enviado. */
    public function queueContractEmail(string $contract,bool $force=false):array{
        ensure($this->mailEnabled(),'El envío de correos no está configurado.',409);
        $c=$this->one('SELECT id,state,is_demo FROM contracts WHERE id=?',[$contract]);ensure($c&&$c['state']==='SIGNED','El contrato no está disponible.',409);
        $open=$this->one("SELECT id,state FROM email_jobs WHERE contract_id=? AND state IN ('QUEUED','RETRY','SENDING')",[$contract]);
        if($open)return ['id'=>$open['id'],'state'=>$open['state']];
        if(!$force&&$this->one("SELECT id FROM email_jobs WHERE contract_id=? AND state='SENT'",[$contract]))return ['id'=>null,'state'=>'SENT'];
        $id=uuid();$this->sql("INSERT INTO email_jobs(id,contract_id,state,created_at) VALUES(?,?,'QUEUED',?)",[$id,$contract,instant()]);
        return ['id'=>$id,'state'=>'QUEUED'];
    }
}

final class SmtpClient {
    private $socket=null;
    public function __construct(private array $cfg,private string $password){}
    private function fail(string $message):never{$this->close();throw new RuntimeException($message);}
    private function read():array{
        $lines=[];while(true){
            $line=fgets($this->socket,1024);if($line===false)$this->fail('El servidor de correo ha cortado la conexión.');
            $lines[]=rtrim($line);if(strlen($line)<4||$line[3]!=='-')break;
        }
        return [(int)substr($lines[0],0,3),implode(' | ',$lines)];
    }
    private function command(string $line,array $ok,string $masked=''):string{
        fwrite($this->socket,$line."\r\n");[$code,$text]=$this->read();
        if(!in_array($code,$ok,true)){$permanent=$code>=500&&!str_starts_with($line,'AUTH');$this->close();throw new MailError(($masked?:$line).' -> '.$text,$permanent);}
        return $text;
    }
    private function connect():void{
        $host=(string)$this->cfg['host'];$port=(int)$this->cfg['port'];$ssl=$this->cfg['security']==='ssl';
        $verify=!($this->cfg['insecure_test_tls']??false);
        $ctx=stream_context_create(['ssl'=>['verify_peer'=>$verify,'verify_peer_name'=>$verify,'peer_name'=>$host,'allow_self_signed'=>!$verify,'crypto_method'=>STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT|STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT]]);
        $this->socket=@stream_socket_client(($ssl?'ssl://':'tcp://').$host.':'.$port,$errno,$err,20,STREAM_CLIENT_CONNECT,$ctx);
        if(!$this->socket)throw new MailError('No se pudo conectar con '.$host.':'.$port.' ('.$err.')',false);
        stream_set_timeout($this->socket,30);
        [$code,$text]=$this->read();if($code!==220)$this->fail('Saludo inesperado: '.$text);
        $name=parse_url((string)($this->cfg['helo_name']??'https://whatsapp.gimnasio.example'),PHP_URL_HOST)?:'whatsapp.gimnasio.example';
        $this->command('EHLO '.$name,[250]);
        if(!$ssl){
            $this->command('STARTTLS',[220]);
            if(!@stream_socket_enable_crypto($this->socket,true,STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT|STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT))$this->fail('No se pudo establecer la conexión cifrada con el servidor de correo.');
            $this->command('EHLO '.$name,[250]);
        }
        if($this->password!==''||!empty($this->cfg['username'])){
            $this->command('AUTH PLAIN '.base64_encode("\0".$this->cfg['username']."\0".$this->password),[235],'AUTH PLAIN (credenciales ocultas)');
        }
    }
    public function send(string $from,string $to,string $message):void{
        $this->connect();
        $this->command('MAIL FROM:<'.$from.'>',[250]);
        $this->command('RCPT TO:<'.$to.'>',[250,251]);
        $this->command('DATA',[354]);
        $body=preg_replace('/(?m)^\./','..',str_replace(["\r\n","\r"],"\n",$message));$body=str_replace("\n","\r\n",$body);
        fwrite($this->socket,$body."\r\n.\r\n");[$code,$text]=$this->read();
        if($code!==250){$permanent=$code>=500;$this->close();throw new MailError('El servidor rechazó el mensaje: '.$text,$permanent);}
        $this->command('QUIT',[221]);$this->close();
    }
    private function close():void{if(is_resource($this->socket))@fclose($this->socket);$this->socket=null;}
}

final class MailError extends RuntimeException {public function __construct(string $message,public bool $permanent=false){parent::__construct($message);}}

function mimeHeader(string $value):string{return preg_match('/^[\x20-\x7e]*$/',$value)?$value:'=?UTF-8?B?'.base64_encode($value).'?=';}
function mimeBody(string $bytes):string{return rtrim(chunk_split(base64_encode($bytes),76,"\r\n"));}

function buildContractEmail(array $cfg,string $to,string $name,string $reference,string $pdf):string{
    $from=$cfg['from_address'];$fromName=$cfg['from_name']??'Top Fitness';$domain=substr(strrchr($from,'@'),1);
    $boundary='tf_'.bin2hex(random_bytes(12));
    $text="Hola, ".$name.":\r\n\r\nTe damos la bienvenida a Top Fitness.\r\n\r\nEn este correo va una copia en PDF de tu contrato de alta (referencia ".$reference."). Guárdala: es tu comprobante.\r\n\r\nSi algo no es correcto, responde a este correo o pregunta en recepción.\r\n\r\nTop Fitness · Top Fighters\r\n";
    $headers=[
        'From: '.mimeHeader($fromName).' <'.$from.'>','To: <'.$to.'>',
        ...(!empty($cfg['reply_to'])?['Reply-To: <'.$cfg['reply_to'].'>']:[]),
        'Subject: '.mimeHeader('Tu contrato de alta en Top Fitness'),
        'Date: '.date('r'),'Message-ID: <'.bin2hex(random_bytes(12)).'@'.$domain.'>',
        'MIME-Version: 1.0','Auto-Submitted: auto-generated','X-Auto-Response-Suppress: All',
        'Content-Type: multipart/mixed; boundary="'.$boundary.'"',
    ];
    $file='contrato-topfitness-'.preg_replace('/[^A-Za-z0-9._-]/','',$reference).'.pdf';
    return implode("\r\n",$headers)."\r\n\r\n--".$boundary."\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n".mimeBody($text)."\r\n--".$boundary."\r\nContent-Type: application/pdf; name=\"".$file."\"\r\nContent-Transfer-Encoding: base64\r\nContent-Disposition: attachment; filename=\"".$file."\"\r\n\r\n".mimeBody($pdf)."\r\n--".$boundary."--\r\n";
}

function buildWithdrawalEmail(array $cfg,string $to,string $name,string $kind,string $reference,string $effective,string $lastDay,string $pdf):string{
    $from=$cfg['from_address'];$fromName=$cfg['from_name']??'Top Fitness';$domain=substr(strrchr($from,'@'),1);$m=$kind==='MAINTENANCE';
    $d=fn($v)=>date('d-m-Y',strtotime($v));$boundary='tf_'.bin2hex(random_bytes(12));
    $text=$m
        ?"Hola, ".$name.":\r\n\r\nHemos recibido tu solicitud de mantenimiento (referencia ".$reference.").\r\n\r\nPuedes seguir entrenando hasta el ".$d($lastDay).". El mantenimiento empieza el ".$d($effective).". Por cada mes completo en mantenimiento se acumula un recargo de 5,00 €, que pagarás al volver junto con la cuota de ese mes. No tendrás que pagar la matrícula otra vez.\r\n\r\nEn este correo va una copia en PDF de tu solicitud firmada. Recepción la revisará y la tramitará.\r\n\r\n¡Te esperamos a la vuelta!\r\n\r\nTop Fitness · Top Fighters\r\n"
        :"Hola, ".$name.":\r\n\r\nHemos recibido tu solicitud de baja (referencia ".$reference.").\r\n\r\nPuedes seguir entrenando hasta el ".$d($lastDay)." y la baja será efectiva el ".$d($effective).".\r\n\r\nEn este correo va una copia en PDF de tu solicitud firmada. Recepción la revisará y la tramitará.\r\n\r\nSentimos que te vayas. Gracias por haber entrenado con nosotros; aquí tienes tu casa si algún día quieres volver.\r\n\r\nTop Fitness · Top Fighters\r\n";
    $headers=['From: '.mimeHeader($fromName).' <'.$from.'>','To: <'.$to.'>',...(!empty($cfg['reply_to'])?['Reply-To: <'.$cfg['reply_to'].'>']:[]),
        'Subject: '.mimeHeader($m?'Tu mantenimiento en Top Fitness':'Tu solicitud de baja en Top Fitness'),'Date: '.date('r'),'Message-ID: <'.bin2hex(random_bytes(12)).'@'.$domain.'>',
        'MIME-Version: 1.0','Auto-Submitted: auto-generated','X-Auto-Response-Suppress: All','Content-Type: multipart/mixed; boundary="'.$boundary.'"'];
    $file=($m?'mantenimiento':'baja').'-topfitness-'.preg_replace('/[^A-Za-z0-9._-]/','',$reference).'.pdf';
    return implode("\r\n",$headers)."\r\n\r\n--".$boundary."\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n".mimeBody($text)."\r\n--".$boundary."\r\nContent-Type: application/pdf; name=\"".$file."\"\r\nContent-Transfer-Encoding: base64\r\nContent-Disposition: attachment; filename=\"".$file."\"\r\n\r\n".mimeBody($pdf)."\r\n--".$boundary."--\r\n";
}

function buildPlainEmail(array $cfg,string $to,string $subject,string $text):string{
    $from=$cfg['from_address'];$domain=substr(strrchr($from,'@'),1);
    $headers=['From: '.mimeHeader($cfg['from_name']??'Top Fitness').' <'.$from.'>','To: <'.$to.'>','Subject: '.mimeHeader($subject),'Date: '.date('r'),'Message-ID: <'.bin2hex(random_bytes(12)).'@'.$domain.'>','MIME-Version: 1.0','Auto-Submitted: auto-generated','Content-Type: text/plain; charset=UTF-8','Content-Transfer-Encoding: base64'];
    return implode("\r\n",$headers)."\r\n\r\n".mimeBody(str_replace("\n","\r\n",$text));
}
