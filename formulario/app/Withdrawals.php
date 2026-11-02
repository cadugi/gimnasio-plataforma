<?php
declare(strict_types=1);
/* Bajas definitivas y mantenimientos (bajas temporales) pedidas por el socio en la tablet.
   Mismo patrón que el alta: datos en la sesión del kiosco, revisión ligada por hash, firma con trazos,
   PDF propio cifrado y aceptación posterior del centro. Nada se aplica hasta que un trabajador la acepta. */

const WITHDRAWAL_REASONS=['price'=>'Precio','schedule'=>'Horario','moving'=>'Cambio de domicilio','injury'=>'Lesión o salud','other'=>'Otro'];

function withdrawalLegal(string $root,string $type):array{
    $raw=(string)file_get_contents($root.'/fixtures/bajas_condiciones_20261020.txt');
    ensure(preg_match('/^VERSION: (\S+)/',$raw,$v)===1,'Faltan las condiciones de baja.',503);
    $parts=preg_split('/^## (.+)$/m',$raw,-1,PREG_SPLIT_DELIM_CAPTURE);$texts=[];
    for($i=1;$i<count($parts);$i+=2)$texts[trim($parts[$i])]=trim($parts[$i+1]);
    $key=$type==='MAINTENANCE'?'MANTENIMIENTO':'BAJA DEFINITIVA';ensure(isset($texts[$key]),'Faltan las condiciones de baja.',503);
    return ['version'=>$v[1],'text'=>$texts[$key]];
}

function maskEmail(string $email):string{
    [$user,$domain]=array_pad(explode('@',$email,2),2,'');
    return $domain===''?'':mb_substr($user,0,1).str_repeat('*',max(2,min(6,mb_strlen($user)-1))).'@'.$domain;
}

trait WithdrawalOperations {
    private function withdrawalSession():array{$this->kiosk();$w=$_SESSION['withdrawal']??null;ensure(is_array($w),'Empieza de nuevo la solicitud de baja.',410);return $w;}

    private function pendingWithdrawalFor(string $fingerprint):bool{return (bool)$this->one("SELECT id FROM withdrawals WHERE document_fingerprint=? AND state='PENDING'",[$fingerprint]);}

    public function withdrawalStart(string $kind):array{
        $this->kiosk();ensure(in_array($kind,['PERMANENT','MAINTENANCE'],true),'Elige baja definitiva o mantenimiento.');
        $_SESSION['withdrawal']=['kind'=>$kind];unset($_SESSION['withdrawal_receipt']);
        return ['kind'=>$kind];
    }

    public function withdrawalIdentify(array $r):array{
        $w=$this->withdrawalSession();$this->limit('withdrawal-identify:'.session_id(),12,900);
        $type=textField($r,'document_type',12);$doc=validateDocument($type,textField($r,'document',35));$birth=validateBirthDate(textField($r,'birth_date',10));
        $fp=$this->vault->fingerprint($type.':'.$doc);
        ensure(!$this->pendingWithdrawalFor($fp),'Ya hay una solicitud de baja pendiente con este documento. Pregunta en recepción.',409);
        $w=['kind'=>$w['kind'],'fingerprint'=>$fp,'personal'=>['document_type'=>$type,'document'=>$doc,'birth_date'=>$birth],'member_id'=>null,'member_number'=>null];
        $m=$this->one('SELECT id,personal_enc,innux_number FROM members WHERE document_fingerprint=?',[$fp]);
        $person=$m?$this->open($m['personal_enc']):null;
        // Solo se reconoce al socio si además coincide la fecha de nacimiento: así no se revela quién es socio.
        if($person&&($person['birth_date']??'')===$birth){
            $w['member_id']=$m['id'];$w['member_number']=$m['innux_number'];
            $w['personal']+=['name'=>$person['name'],'surname'=>$person['surname'],'phone'=>$person['phone']??'','email'=>$person['email']??''];
            $_SESSION['withdrawal']=$w;
            return ['found'=>true,'name'=>$person['name'].' '.$person['surname'],'member_number'=>$m['innux_number'],'email_hint'=>maskEmail((string)($person['email']??''))];
        }
        $_SESSION['withdrawal']=$w;
        return ['found'=>false,'name'=>null,'member_number'=>null,'email_hint'=>null];
    }

    public function withdrawalSave(array $r):array{
        $w=$this->withdrawalSession();ensure(isset($w['fingerprint']),'Identifícate primero.',409);
        if(!$w['member_id']){
            $w['personal']['name']=textField($r,'name',100);$w['personal']['surname']=textField($r,'surname',160);
            $phone=preg_replace('/[\s().-]/','',textField($r,'phone',24));ensure(preg_match('/^\+?[0-9]{7,15}$/',$phone)===1,'Teléfono no válido.');$w['personal']['phone']=$phone;
            $number=textField($r,'member_number',10,false);ensure($number===''||ctype_digit($number),'El número de socio solo lleva cifras.');$w['member_number']=$number?:null;
        }
        $email=textField($r,'email',180,!$w['member_id']);
        if($email!==''){ensure(filter_var($email,FILTER_VALIDATE_EMAIL)!==false,'Correo electrónico no válido.');$w['personal']['email']=strtolower($email);}
        $reason=textField($r,'reason',20,false);ensure($reason===''||isset(WITHDRAWAL_REASONS[$reason]),'Motivo no válido.');
        $w['reason']=$reason?:null;$w['reason_text']=textField($r,'reason_text',200,false)?:null;unset($w['snapshot'],$w['review_hash']);
        $_SESSION['withdrawal']=$w;return ['saved'=>true];
    }

    public function withdrawalPrepare():array{
        $w=$this->withdrawalSession();ensure(isset($w['fingerprint'])&&isset($w['personal']['name']),'Completa tus datos.',409);
        $dates=withdrawalDates(madridToday());$maintenance=$w['kind']==='MAINTENANCE';
        $snapshot=['kind'=>'withdrawal','type'=>$w['kind'],'reference'=>'TF-B-'.date('Y').'-'.strtoupper(bin2hex(random_bytes(6))),
            'paper_reference'=>paperReference($this->root),'date_local'=>date('d-m-Y H:i'),'prepared_at'=>instant(),
            'member_id'=>$w['member_id'],'member_number'=>$w['member_number'],'personal'=>$w['personal'],
            'reason'=>$w['reason']??null,'reason_label'=>isset($w['reason'])?WITHDRAWAL_REASONS[$w['reason']]:null,'reason_text'=>$w['reason_text']??null,
            'last_day'=>$dates['last_day'],'effective_date'=>$dates['effective_date'],'fee_cents_per_month'=>$maintenance?MAINTENANCE_FEE_CENTS:null,
            'legal'=>withdrawalLegal($this->root,$w['kind']),'is_demo'=>$this->demo()];
        $w['snapshot']=$snapshot;$w['review_hash']=hash('sha256',jencode($snapshot));$_SESSION['withdrawal']=$w;
        return ['review_hash'=>$w['review_hash'],'summary'=>['kind'=>$w['kind'],'reference'=>$snapshot['reference'],'last_day'=>$dates['last_day'],'effective_date'=>$dates['effective_date'],'fee_cents_per_month'=>$snapshot['fee_cents_per_month'],'email'=>$w['personal']['email']??'']];
    }

    public function withdrawalSign(array $r):array{
        $w=$this->withdrawalSession();ensure(($r['confirmed']??false)===true,'Confirma expresamente tu firma.');
        $signature=validateSignature($r['signature']??null);$key=textField($r,'review_hash',64);
        ensure(isset($w['snapshot'])&&hash_equals((string)$w['review_hash'],$key),'La solicitud ha cambiado. Revísala antes de firmar.',409);
        $s=$w['snapshot'];$now=withdrawalDates(madridToday());
        ensure($now['last_day']===$s['last_day']&&$now['effective_date']===$s['effective_date'],'Ha cambiado el mes y las fechas ya no son las mismas. Revísala de nuevo antes de firmar.',409);
        return $this->transaction(function()use($w,$s,$signature,$key){
            ensure(!$this->pendingWithdrawalFor($w['fingerprint']),'Ya hay una solicitud de baja pendiente con este documento. Pregunta en recepción.',409);
            $pdf=(new ContractPdf($this->root,$this->config))->build($s,$signature);$id=uuid();
            $evidence=['signed_at'=>instant(),'review_hash'=>$key,'snapshot_hash'=>hash('sha256',jencode($s)),'signature_hash'=>hash('sha256',jencode($signature)),'signature_method'=>'DRAWN_VISUAL_V1','explicit_confirmation'=>true,'qualified_signature'=>false,'legal_version'=>$s['legal']['version'],'center_state'=>'PENDING_ACCEPTANCE'];
            $this->sql('INSERT INTO withdrawals(id,reference,kind,member_id,document_fingerprint,snapshot_enc,snapshot_hash,pdf_enc,pdf_hash,signature_enc,evidence_enc,last_day,effective_date,fee_cents_per_month,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                [$id,$s['reference'],$s['type'],$s['member_id'],$w['fingerprint'],$this->seal($s),$evidence['snapshot_hash'],$this->vault->encrypt($pdf,'pdf'),hash('sha256',$pdf),$this->seal($signature,'signature'),$this->seal($evidence),$s['last_day'],$s['effective_date'],$s['fee_cents_per_month']??MAINTENANCE_FEE_CENTS,instant()]);
            // Copia al socio en cuanto firma: es su comprobante de que lo pidió en plazo.
            if(filter_var($s['personal']['email']??'',FILTER_VALIDATE_EMAIL)&&$this->mailEnabled())
                $this->sql("INSERT INTO withdrawal_email_jobs(id,withdrawal_id,state,created_at) VALUES(?,?,'QUEUED',?)",[uuid(),$id,instant()]);
            $this->audit($this->actor(),'WITHDRAWAL_SIGNED',$id,['type'=>$s['type'],'pdf_hash'=>hash('sha256',$pdf),'member_linked'=>$s['member_id']!==null]);
            unset($_SESSION['withdrawal']);$_SESSION['withdrawal_receipt']=$id;
            return ['id'=>$id,'reference'=>$s['reference'],'kind'=>$s['type'],'last_day'=>$s['last_day'],'effective_date'=>$s['effective_date']];
        });
    }

    public function withdrawalCancel():array{$this->kiosk();unset($_SESSION['withdrawal'],$_SESSION['withdrawal_receipt']);return ['cleared'=>true];}

    public function withdrawalPreviewPdf():string{$w=$this->withdrawalSession();ensure(isset($w['snapshot']),'Revisa primero la solicitud.',409);return (new ContractPdf($this->root,$this->config))->build($w['snapshot'],[],true);}

    public function withdrawalReviewHtml():string{
        $w=$this->withdrawalSession();ensure(isset($w['snapshot']),'Revisa primero la solicitud.',409);$s=$w['snapshot'];$p=$s['personal'];$m=$s['type']==='MAINTENANCE';
        $e=fn(mixed $v)=>htmlspecialchars((string)$v,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');$d=fn($v)=>date('d-m-Y',strtotime($v));
        $dl=function(array $rows)use($e){$o='<dl class="review-fields">';foreach($rows as $k=>$v)$o.='<div><dt>'.$e($k).'</dt><dd>'.$e($v).'</dd></div>';return $o.'</dl>';};
        $html='<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión de la solicitud</title><link rel="stylesheet" href="assets/review.css?v=20261020-bajas"><body>';
        $html.='<header><img src="assets/logo.jpg" alt="Top Fitness"><div><img class="fighters-logo" src="assets/logo-fighters.png" alt="Top Fighters"><h1>'.($m?'Mantenimiento (baja temporal)':'Baja definitiva').'</h1>'.$e($s['reference']).'</div></header>';
        $html.='<section><h2>Datos del socio</h2>'.$dl(['N.º socio'=>$s['member_number']?:'No indicado','Nombre'=>$p['name'].' '.$p['surname'],'Documento'=>$p['document_type'].' '.$p['document'],'Fecha de nacimiento'=>$d($p['birth_date']),'Teléfono'=>$p['phone']?:'—','E-mail'=>$p['email']?:'—']).'</section>';
        $html.='<section><h2>Fechas</h2>'.$dl(['Puedes entrenar hasta'=>$d($s['last_day']),($m?'Empieza el mantenimiento':'Baja efectiva desde')=>$d($s['effective_date'])]+($m?['Recargo'=>centsString($s['fee_cents_per_month']).' por mes completo, se paga al volver','Matrícula al volver'=>'No se vuelve a pagar']:[])).'</section>';
        if($s['reason_label'])$html.='<section><h2>Motivo</h2><p>'.$e($s['reason_label'].($s['reason_text']?' · '.$s['reason_text']:'')).'</p></section>';
        $html.='<section><h2>Condiciones · '.$e($s['legal']['version']).'</h2>'.implode('',array_map(fn($l)=>'<p>'.$e($l).'</p>',array_filter(explode("\n",$s['legal']['text'])))).'</section>';
        $html.='<section class="signature-columns"><div><h2>Por el socio</h2><p>La firma se incorpora al PDF cuando confirmes.</p></div><div><h2>Por el Centro</h2><p>La aceptación se registra de forma auditada por un trabajador autorizado.</p></div></section>';
        return $html.'<footer>Versión revisada: '.$e($w['review_hash']).'</footer></body></html>';
    }

    // --- Panel de recepción ---
    public function withdrawalList(array $r):array{
        $this->staff(['admin','staff','viewer']);$out=[];
        foreach($this->sql('SELECT id,reference,kind,state,member_id,snapshot_enc,created_at,last_day,effective_date,decided_at,returned_at,return_fee_cents,return_renewal_cents FROM withdrawals ORDER BY created_at DESC LIMIT 300') as $w){
            $s=$this->open($w['snapshot_enc']);unset($w['snapshot_enc']);
            $out[]=$w+['name'=>$s['personal']['name'].' '.$s['personal']['surname'],'member_number'=>$s['member_number']];
        }
        return $out;
    }
    public function withdrawalDetail(string $id):array{
        $this->staff(['admin','staff','viewer']);$w=$this->one('SELECT * FROM withdrawals WHERE id=?',[$id]);ensure($w,'Solicitud no encontrada.',404);
        $s=$this->open($w['snapshot_enc']);$job=$this->one('SELECT state,sent_at,last_error FROM withdrawal_email_jobs WHERE withdrawal_id=? ORDER BY created_at DESC LIMIT 1',[$id]);
        $last=$w['member_id']?$this->one("SELECT tariff_id FROM contracts WHERE member_id=? AND state='SIGNED' ORDER BY created_at DESC LIMIT 1",[$w['member_id']]):null;
        return ['id'=>$id,'reference'=>$w['reference'],'kind'=>$w['kind'],'state'=>$w['state'],'created_at'=>$w['created_at'],'date_local'=>$s['date_local'],
            'last_day'=>$w['last_day'],'effective_date'=>$w['effective_date'],'fee_cents_per_month'=>(int)$w['fee_cents_per_month'],
            'member_linked'=>$w['member_id']!==null,'member_number'=>$s['member_number'],'personal'=>$s['personal'],'reason_label'=>$s['reason_label'],'reason_text'=>$s['reason_text'],
            'decided_at'=>$w['decided_at'],'decided_actor'=>$w['decided_actor'],'reject_reason'=>$w['reject_reason_enc']?$this->open($w['reject_reason_enc']):null,
            'returned_at'=>$w['returned_at'],'return_months'=>$w['return_months'],'return_fee_cents'=>$w['return_fee_cents'],'return_renewal_cents'=>$w['return_renewal_cents'],
            'email'=>$job,'default_tariff_id'=>$last['tariff_id']??null];
    }
    private function pendingWithdrawal(string $id):array{$w=$this->one('SELECT * FROM withdrawals WHERE id=?',[$id]);ensure($w,'Solicitud no encontrada.',404);ensure($w['state']==='PENDING','La solicitud ya no está pendiente.',409);return $w;}
    public function acceptWithdrawal(string $id):array{
        $u=$this->staff(['admin','staff']);
        return $this->transaction(function()use($id,$u){$w=$this->pendingWithdrawal($id);
            $this->sql("UPDATE withdrawals SET state='ACCEPTED',decided_at=?,decided_actor=? WHERE id=?",[instant(),$u['username'],$id]);
            if($w['member_id'])$this->sql('UPDATE members SET state=? WHERE id=?',[$w['kind']==='MAINTENANCE'?'MAINTENANCE':'WITHDRAWN',$w['member_id']]);
            $this->audit($this->actor(),'WITHDRAWAL_ACCEPTED',$id,['kind'=>$w['kind'],'pdf_hash'=>$w['pdf_hash']]);
            return ['accepted'=>true,'retirement'=>$this->scheduleRetirementForWithdrawal($w)];});
    }
    public function rejectWithdrawal(string $id,string $reason):array{
        $u=$this->staff(['admin','staff']);$reason=trim($reason);ensure($reason!==''&&mb_strlen($reason)<=300,'Indica el motivo del rechazo.');
        return $this->transaction(function()use($id,$u,$reason){$this->pendingWithdrawal($id);
            $this->sql("UPDATE withdrawals SET state='REJECTED',decided_at=?,decided_actor=?,reject_reason_enc=? WHERE id=?",[instant(),$u['username'],$this->seal($reason),$id]);
            $this->audit($this->actor(),'WITHDRAWAL_REJECTED',$id,['reason'=>$reason]);return ['rejected'=>true];});
    }
    // Vuelta de un mantenimiento: 5 € por mes completo fuera + cuota del mes de vuelta prorrateada (se cobra en recepción).
    public function withdrawalReturn(string $id,string $date,string $tariffId):array{
        $u=$this->staff(['admin','staff']);ymd($date);
        return $this->transaction(function()use($id,$date,$tariffId,$u){
            $w=$this->one('SELECT * FROM withdrawals WHERE id=?',[$id]);ensure($w&&$w['kind']==='MAINTENANCE'&&$w['state']==='ACCEPTED','Solo se registra la vuelta de un mantenimiento aceptado.',409);
            ensure($w['returned_at']===null,'La vuelta de este mantenimiento ya está registrada.',409);ensure($date>=substr($w['created_at'],0,10),'La fecha de vuelta no puede ser anterior a la solicitud.');
            $t=$this->one('SELECT monthly_cents FROM tariffs WHERE id=?',[$tariffId]);ensure($t,'Elige la tarifa con la que vuelve.');
            $months=maintenanceMonths($w['effective_date'],$date);$fee=$months*(int)$w['fee_cents_per_month'];$renewal=prorateMonth((int)$t['monthly_cents'],$date)['cents'];
            $this->sql('UPDATE withdrawals SET returned_at=?,return_months=?,return_fee_cents=?,return_renewal_cents=?,return_actor=? WHERE id=?',[$date,$months,$fee,$renewal,$u['username'],$id]);
            if($w['member_id'])$this->sql("UPDATE members SET state='ACTIVE' WHERE id=?",[$w['member_id']]);
            $this->audit($this->actor(),'MAINTENANCE_RETURNED',$id,['months'=>$months,'fee_cents'=>$fee,'renewal_cents'=>$renewal,'tariff_id'=>$tariffId]);
            return ['months'=>$months,'fee_cents'=>$fee,'renewal_cents'=>$renewal,'total_cents'=>$fee+$renewal];
        });
    }
    // ¿Está el socio fuera (baja o mantenimiento aceptados) en el periodo 'AAAA-MM'? El mes de vuelta se cobra en recepción.
    private function withdrawnInPeriod(string $member,string $period):bool{
        return (bool)$this->one("SELECT id FROM withdrawals WHERE member_id=? AND state='ACCEPTED' AND substr(effective_date,1,7)<=? AND (kind='PERMANENT' OR returned_at IS NULL OR substr(returned_at,1,7)>=?)",[$member,$period,$period]);
    }

    public function withdrawalDocument(string $id):string{
        if(($_SESSION['mode']??'')!=='kiosk'||($_SESSION['withdrawal_receipt']??'')!==$id)$this->staff(['admin','staff','viewer']);
        $w=$this->one('SELECT pdf_enc,pdf_hash FROM withdrawals WHERE id=?',[$id]);ensure($w,'Documento no disponible.',404);
        $pdf=$this->vault->decrypt($w['pdf_enc'],'pdf');ensure(hash_equals($w['pdf_hash'],hash('sha256',$pdf)),'El PDF no supera la comprobación de integridad.',500);
        return $pdf;
    }
}
