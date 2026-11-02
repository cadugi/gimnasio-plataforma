<?php
declare(strict_types=1);
/**
 * Bajas de socios. El portal conserva siempre el historico (ficha, contratos, mandatos, cuotas);
 * el borrado en Innux lo ejecuta el conector local en una sola transaccion, tras guardar alli un
 * archivo cifrado con todas las filas que va a eliminar.
 */
trait RetirementOperations {
    private function retirementName(array $personal):string{return trim(($personal['name']??'').' '.($personal['surname']??''));}
    private function retirementDocument(array $personal):string{return strtoupper(str_replace([' ','-'],'',(string)($personal['document']??'')));}

    public function retirementCandidates(array $r):array {
        $this->staff(['admin']);
        $query=strtolower(trim((string)($r['query']??'')));ensure(strlen($query)>=2,'Escribe al menos dos caracteres.');
        $needle=strtoupper(str_replace([' ','-'],'',$query));$out=[];
        foreach($this->sql("SELECT * FROM members WHERE state<>'BAJA' ORDER BY created_at DESC") as $m){
            $p=$this->open($m['personal_enc']);$name=$this->retirementName($p);
            $hit=str_contains(strtolower($name),$query)||str_contains(strtolower($m['internal_reference']),$query)||($m['innux_number']!==null&&$m['innux_number']===trim($query))||str_contains($this->retirementDocument($p),$needle);
            if(!$hit)continue;
            $out[]=['id'=>$m['id'],'name'=>$name,'internal_reference'=>$m['internal_reference'],'innux_number'=>$m['innux_number'],'innux_state'=>$m['innux_state'],
                'linked'=>$m['innux_reference']!==null,'contracts'=>(int)$this->one('SELECT COUNT(*) n FROM contracts WHERE member_id=?',[$m['id']])['n'],
                'open_dues'=>(int)$this->one("SELECT COUNT(*) n FROM dues WHERE member_id=? AND state IN ('PREPARED','EXPORTED','SENT')",[$m['id']])['n']];
            if(count($out)>=50)break;
        }
        return $out;
    }

    /** Busca en Innux (no solo en el portal): la consulta la atiende el PC de Innux en unos segundos. */
    public function innuxSearchStart(array $r):array {
        $this->staff(['admin']);
        $query=trim((string)($r['query']??''));ensure(mb_strlen($query)>=2&&mb_strlen($query)<=60&&preg_match('//u',$query)===1,'Escribe entre 2 y 60 caracteres.');
        $this->limit('innux-search:'.$this->actor(),150,60);  // autocompletado: una consulta por pausa al escribir
        return $this->transaction(function()use($query){
            ensure($this->one('SELECT id FROM innux_devices WHERE active=1'),'El conector de Innux no está configurado.',409);
            $this->sql('DELETE FROM innux_searches WHERE created_at<?',[gmdate('Y-m-d\TH:i:s\Z',time()-3600)]);
            $id=uuid();$now=instant();$this->sql("INSERT INTO innux_searches(id,actor,query_enc,state,created_at,updated_at) VALUES(?,?,?,'QUEUED',?,?)",[$id,$this->actor(),$this->seal($query,'innux_search_query'),$now,$now]);
            return ['id'=>$id];
        });
    }

    public function innuxSearchResult(string $id):array {
        $this->staff(['admin']);$row=$this->one('SELECT * FROM innux_searches WHERE id=?',[$id]);ensure($row,'Búsqueda no encontrada.',404);
        if($row['state']==='QUEUED'&&$row['created_at']<gmdate('Y-m-d\TH:i:s\Z',time()-60))return ['state'=>'FAILED','error_code'=>'CONNECTOR_NOT_RESPONDING'];
        if($row['state']!=='DONE')return ['state'=>$row['state'],'error_code'=>$row['error_code']];
        $items=[];
        foreach($this->open($row['result_enc'],'innux_search') as $it){
            $doc=(string)($it['document']??'');$m=$this->one('SELECT id,state FROM members WHERE innux_number=?',[(string)$it['number']]);
            $items[]=['client_id'=>$it['client_id'],'number'=>$it['number'],'name'=>$it['name'],'active'=>(bool)$it['active'],'document_hint'=>$doc===''?'':'···'.substr($doc,-3),'in_portal'=>(bool)$m,'removed'=>$m&&$m['state']==='BAJA'];
        }
        return ['state'=>'DONE','id'=>$id,'items'=>$items];
    }

    /** Socio que solo existe en Innux: se crea su ficha historica en el portal para poder conservar su perfil. */
    private function legacyMemberFromSearch(string $searchId,string $clientId):array {
        ensure(preg_match('/^[a-f0-9]{32}$/',$searchId)===1&&preg_match('/^[1-9][0-9]{0,9}$/',$clientId)===1,'Búsqueda no válida.');
        $s=$this->one("SELECT * FROM innux_searches WHERE id=? AND state='DONE' AND created_at>?",[$searchId,gmdate('Y-m-d\TH:i:s\Z',time()-3600)]);ensure($s,'La búsqueda ha caducado. Busca de nuevo.',409);
        $item=null;foreach($this->open($s['result_enc'],'innux_search') as $it)if((string)$it['client_id']===$clientId)$item=$it;
        ensure($item,'Socio no encontrado en la búsqueda.',404);
        $m=$this->one('SELECT * FROM members WHERE innux_number=?',[(string)$item['number']]);
        if($m){ensure($m['innux_reference']==='INNUX:'.$clientId,'El número de socio coincide con otra ficha del portal. Revísalo.',409);return [$m['id'],$item];}
        ensure(!$this->one('SELECT id FROM members WHERE innux_reference=?',['INNUX:'.$clientId]),'Esa ficha de Innux ya está vinculada.',409);
        $id=uuid();$personal=['name'=>(string)$item['name'],'surname'=>'','document_type'=>'NIF','document'=>(string)($item['document']??''),'birth_date'=>(string)($item['birth_date']??''),'email'=>(string)($item['email']??''),'phone'=>(string)($item['phone']??''),'address'=>'','town'=>'','postal_code'=>'','source'=>'INNUX_ONLY'];
        $this->sql("INSERT INTO members(id,internal_reference,personal_enc,document_fingerprint,innux_reference,innux_number,innux_state,created_at) VALUES(?,?,?,?,?,?,'VERIFIED_READ_ONLY',?)",
            [$id,'TF-S-'.strtoupper(substr($id,0,12)),$this->seal($personal),$this->vault->fingerprint('INNUX:'.$clientId),'INNUX:'.$clientId,(string)$item['number'],instant()]);
        return [$id,$item];
    }

    public function retirementList():array {
        $this->staff(['admin']);$out=[];
        foreach($this->sql('SELECT r.*,m.personal_enc,m.internal_reference,m.innux_number,u.username FROM member_retirements r JOIN members m ON m.id=r.member_id LEFT JOIN users u ON u.id=r.actor ORDER BY r.created_at DESC LIMIT 300') as $row){
            $result=$row['result_enc']?$this->open($row['result_enc'],'retirement_result'):[];$options=$this->open($row['options_enc'],'retirement_options');
            $out[]=['id'=>$row['id'],'member_id'=>$row['member_id'],'name'=>$this->retirementName($this->open($row['personal_enc'])),'internal_reference'=>$row['internal_reference'],
                'innux_number'=>$options['innux_number']??$row['innux_number'],'mode'=>$row['mode'],'state'=>$row['state'],'error_code'=>$row['error_code'],'actor'=>$row['username']??$row['actor'],
                'created_at'=>$row['created_at'],'completed_at'=>$row['completed_at'],'not_before'=>$row['not_before'],'include_fiscal'=>(bool)($options['include_fiscal']??false),'counts'=>$result['counts']??null];
        }
        return $out;
    }

    public function retirementArchive(string $id):array {
        $this->staff(['admin']);$row=$this->one('SELECT * FROM member_retirements WHERE id=?',[$id]);ensure($row,'Baja no encontrada.',404);
        $this->transaction(fn()=>$this->audit($this->actor(),'RETIREMENT_ARCHIVE_VIEWED',$id));
        $result=$row['result_enc']?$this->open($row['result_enc'],'retirement_result'):null;
        return ['id'=>$id,'state'=>$row['state'],'archive'=>$this->open($row['archive_enc'],'retirement_archive'),'innux'=>$result];
    }

    private function retirementSnapshot(array $m,string $reason):array {
        $contracts=[];foreach($this->sql('SELECT * FROM contracts WHERE member_id=? ORDER BY created_at',[$m['id']]) as $c){$s=$this->open($c['snapshot_enc']);
            $contracts[]=['id'=>$c['id'],'reference'=>$c['reference'],'state'=>$c['state'],'created_at'=>$c['created_at'],'center_accepted_at'=>$c['center_accepted_at'],'pdf_hash'=>$c['pdf_hash'],
                'payment_method'=>$c['payment_method'],'monthly_cents'=>(int)$c['monthly_cents'],'enrollment_cents'=>(int)$c['enrollment_cents'],'initial_cents'=>(int)$c['initial_cents'],
                'tariff'=>$s['tariff']['name']??null,'brand'=>$s['tariff']['brand']??null,'legal_version'=>$s['legal']['version']??null,'previous_id'=>$c['previous_id']];}
        return ['version'=>1,'created_at'=>instant(),'actor'=>$this->actor(),'reason'=>$reason,
            'member'=>['id'=>$m['id'],'internal_reference'=>$m['internal_reference'],'created_at'=>$m['created_at'],'state'=>$m['state'],'innux_reference'=>$m['innux_reference'],'innux_number'=>$m['innux_number'],'innux_state'=>$m['innux_state'],'personal'=>$this->open($m['personal_enc'])],
            'contracts'=>$contracts,
            'mandates'=>$this->sql('SELECT reference,contract_id,last_four,state,holder_same,signed_at,revoked_at FROM mandates WHERE member_id=? ORDER BY signed_at',[$m['id']]),
            'dues'=>$this->sql('SELECT period,contract_id,amount_cents,expected_cents,concept,due_date,state FROM dues WHERE member_id=? ORDER BY period',[$m['id']]),
            'innux_jobs'=>$this->sql('SELECT state,number,created_at,updated_at FROM innux_jobs WHERE member_id=?',[$m['id']])];
    }

    public function requestRetirement(array $r):array {
        $this->staff(['admin']);
        $searchId=(string)($r['search_id']??'');$id=$searchId!==''?'':textField($r,'member_id',32);$reason=textField($r,'reason',600);ensure(strlen($reason)>=8,'Indica el motivo de la baja (mínimo 8 caracteres).');
        $skip=($r['skip_innux']??false)===true;$fiscal=($r['include_fiscal']??false)===true;
        return $this->transaction(function()use($id,$searchId,$reason,$skip,$fiscal,$r){
            $legacy=null;if($searchId!==''){[$id,$legacy]=$this->legacyMemberFromSearch($searchId,(string)($r['client_id']??''));}
            $m=$this->one('SELECT * FROM members WHERE id=?',[$id]);ensure($m,'Socio no encontrado.',404);
            ensure($m['state']!=='BAJA'&&!$this->one("SELECT id FROM member_retirements WHERE member_id=? AND state<>'CANCELLED'",[$id]),'Este socio ya está dado de baja o tiene una baja en curso.',409);
            $expected=$m['innux_number']!==null?(string)$m['innux_number']:$m['internal_reference'];
            ensure(hash_equals($expected,trim((string)($r['confirm_text']??''))),'Para confirmar, escribe exactamente '.($m['innux_number']!==null?'el número de socio':'la referencia interna').' del socio.');
            ensure(!$this->one("SELECT id FROM innux_jobs WHERE member_id=? AND state IN ('QUEUED','RUNNING','REVIEW_REQUIRED')",[$id]),'Hay un alta en Innux sin terminar para este socio. Resuélvela antes de dar la baja.',409);
            ensure(!$this->one("SELECT id FROM dues WHERE member_id=? AND state IN ('EXPORTED','SENT')",[$id]),'Hay domiciliaciones exportadas o enviadas: registra primero su resolución bancaria.',409);
            $pattern=$m['innux_reference']!==null&&preg_match('/^INNUX:([1-9][0-9]{0,9})$/',$m['innux_reference'],$match)===1&&$m['innux_number']!==null&&ctype_digit((string)$m['innux_number']);
            ensure(!($m['innux_reference']!==null&&!$pattern&&!$skip),'La ficha de Innux no se puede localizar con seguridad desde el portal. Elimínala en Innux y marca «ya no existe en Innux».');
            $mode=$m['innux_reference']!==null&&$pattern&&!$skip?'INNUX':'PORTAL_ONLY';
            $personal=$this->open($m['personal_enc']);
            $options=['previous_innux_state'=>$m['innux_state'],'include_fiscal'=>$fiscal];
            if($mode==='INNUX')$options+=['client_id'=>(int)$match[1],'innux_number'=>(string)$m['innux_number'],'document'=>$this->retirementDocument($personal),'birth_date'=>$personal['birth_date']??'','name'=>$legacy?(string)$legacy['name']:''];
            $rid=uuid();$now=instant();
            $this->sql('INSERT INTO member_retirements(id,member_id,mode,state,actor,reason_enc,options_enc,archive_enc,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                [$rid,$id,$mode,$mode==='INNUX'?'QUEUED':'COMPLETED',$this->actor(),$this->vault->encrypt($reason,'retirement_reason'),$this->seal($options,'retirement_options'),$this->seal($this->retirementSnapshot($m,$reason),'retirement_archive'),$now,$now]);
            // Efectos inmediatos en el portal: el socio deja de cobrarse y de aparecer como alta pendiente.
            $this->sql("UPDATE members SET state='BAJA' WHERE id=?",[$id]);
            $this->sql("UPDATE mandates SET state='REVOKED',revoked_at=? WHERE member_id=? AND state<>'REVOKED'",[$now,$id]);
            $this->sql("UPDATE dues SET state='CANCELLED',revision=revision+1 WHERE member_id=? AND state='PREPARED'",[$id]);
            $this->sql("UPDATE contracts SET state='CANCELLED' WHERE member_id=? AND state='SIGNED' AND center_accepted_at IS NULL",[$id]);
            if($mode==='INNUX'){$this->sql("UPDATE members SET innux_state='REMOVAL_QUEUED' WHERE id=?",[$id]);}
            else{$this->sql("UPDATE members SET innux_reference=NULL,innux_state='REMOVED' WHERE id=?",[$id]);$this->sql('UPDATE member_retirements SET completed_at=? WHERE id=?',[$now,$rid]);}
            $this->audit($this->actor(),'MEMBER_RETIREMENT_REQUESTED',$rid,['member'=>$id,'mode'=>$mode,'include_fiscal'=>$fiscal,'reason'=>$reason]);
            return ['id'=>$rid,'state'=>$mode==='INNUX'?'QUEUED':'COMPLETED','mode'=>$mode];
        });
    }

    /**
     * Baja definitiva firmada y aceptada: el socio se elimina de Innux (con su historico) cuando la baja es efectiva.
     * Se llama dentro de la transaccion de la aceptacion; nunca bloquea la aceptacion, solo informa de lo que no pudo programar.
     */
    public function scheduleRetirementForWithdrawal(array $w):array {
        if(($w['kind']??'')!=='PERMANENT'||empty($w['member_id']))return ['state'=>'NOT_APPLICABLE'];
        $m=$this->one('SELECT * FROM members WHERE id=?',[$w['member_id']]);
        if(!$m||$m['innux_reference']===null||preg_match('/^INNUX:([1-9][0-9]{0,9})$/',(string)$m['innux_reference'],$match)!==1||$m['innux_number']===null||!ctype_digit((string)$m['innux_number']))return ['state'=>'NOT_LINKED'];
        if($this->one("SELECT id FROM member_retirements WHERE member_id=? AND state<>'CANCELLED'",[$m['id']]))return ['state'=>'ALREADY'];
        if($this->one("SELECT id FROM innux_jobs WHERE member_id=? AND state IN ('QUEUED','RUNNING','REVIEW_REQUIRED')",[$m['id']]))return ['state'=>'BLOCKED','error_code'=>'ENROLLMENT_PENDING'];
        $personal=$this->open($m['personal_enc']);$reason='Baja definitiva solicitada y firmada por el socio ('.$w['reference'].')';$rid=uuid();$now=instant();
        $options=['previous_innux_state'=>$m['innux_state'],'include_fiscal'=>false,'deferred'=>true,'withdrawal'=>$w['id'],'client_id'=>(int)$match[1],'innux_number'=>(string)$m['innux_number'],'document'=>$this->retirementDocument($personal),'birth_date'=>$personal['birth_date']??'','name'=>''];
        $this->sql('INSERT INTO member_retirements(id,member_id,mode,state,actor,reason_enc,options_enc,archive_enc,created_at,updated_at,not_before) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            [$rid,$m['id'],'INNUX','QUEUED',$this->actor(),$this->vault->encrypt($reason,'retirement_reason'),$this->seal($options,'retirement_options'),$this->seal($this->retirementSnapshot($m,$reason),'retirement_archive'),$now,$now,substr((string)$w['effective_date'],0,10)]);
        $this->sql("UPDATE members SET innux_state='REMOVAL_QUEUED' WHERE id=?",[$m['id']]);
        $this->audit($this->actor(),'MEMBER_RETIREMENT_SCHEDULED',$rid,['member'=>$m['id'],'withdrawal'=>$w['id'],'not_before'=>$w['effective_date']]);
        return ['state'=>'QUEUED','id'=>$rid,'not_before'=>substr((string)$w['effective_date'],0,10),'due'=>substr((string)$w['effective_date'],0,10)<=madridToday()];
    }

    public function retryRetirement(array $r):array {
        $this->staff(['admin']);$id=textField($r,'id',32);
        return $this->transaction(function()use($id,$r){
            $j=$this->one('SELECT * FROM member_retirements WHERE id=?',[$id]);ensure($j&&$j['state']==='REVIEW_REQUIRED'&&$j['mode']==='INNUX','Esta baja no admite reintento.',409);
            $options=$this->open($j['options_enc'],'retirement_options');
            if(($r['include_fiscal']??false)===true)$options['include_fiscal']=true;
            $this->sql("UPDATE member_retirements SET state='QUEUED',error_code=NULL,options_enc=?,lease_until=NULL,updated_at=? WHERE id=?",[$this->seal($options,'retirement_options'),instant(),$id]);
            $this->audit($this->actor(),'MEMBER_RETIREMENT_RETRY',$id,['include_fiscal'=>(bool)$options['include_fiscal']]);
            return ['state'=>'QUEUED'];
        });
    }

    public function cancelRetirement(string $id):array {
        $this->staff(['admin']);
        return $this->transaction(function()use($id){
            $j=$this->one('SELECT * FROM member_retirements WHERE id=?',[$id]);ensure($j&&$j['mode']==='INNUX'&&in_array($j['state'],['QUEUED','REVIEW_REQUIRED'],true),'Esta baja ya no se puede cancelar.',409);
            ensure(!in_array($j['error_code'],['SQL_COMMIT_RESULT_UNCERTAIN','LEASE_EXPIRED'],true),'No se sabe si Innux llegó a borrar la ficha. Reintenta la baja para que el conector lo compruebe.',409);
            $options=$this->open($j['options_enc'],'retirement_options');
            $this->sql("UPDATE member_retirements SET state='CANCELLED',updated_at=? WHERE id=?",[instant(),$id]);
            $this->sql(empty($options['deferred'])?"UPDATE members SET state='ACTIVE',innux_state=? WHERE id=?":"UPDATE members SET innux_state=? WHERE id=?",[$options['previous_innux_state']??'VERIFIED_CONNECTOR',$j['member_id']]);
            $this->audit($this->actor(),'MEMBER_RETIREMENT_CANCELLED',$id,['note'=>'mandates and prepared dues stay cancelled']);
            return ['state'=>'CANCELLED'];
        });
    }

    private function retirementDeviceOperation(string $device,array $r):array {
        $op=$r['operation'];
        if($op==='removal_claim')return $this->transaction(function()use($device){
            $this->sql("UPDATE member_retirements SET state='REVIEW_REQUIRED',error_code='LEASE_EXPIRED',updated_at=? WHERE state='RUNNING' AND lease_until<?",[instant(),time()]);
            if($this->one("SELECT id FROM member_retirements WHERE state='RUNNING' OR (state='REVIEW_REQUIRED' AND error_code='LEASE_EXPIRED')")||$this->one("SELECT id FROM innux_jobs WHERE state='RUNNING'"))return ['removal'=>null,'wait_reason'=>'ACTIVE_WORKER'];
            $j=$this->one("SELECT * FROM member_retirements WHERE state='QUEUED' AND mode='INNUX' AND (not_before IS NULL OR not_before<=?) ORDER BY created_at LIMIT 1",[madridToday()]);if(!$j)return ['removal'=>null,'wait_reason'=>'EMPTY_QUEUE'];
            $o=$this->open($j['options_enc'],'retirement_options');
            $this->sql("UPDATE member_retirements SET state='RUNNING',device_id=?,lease_until=?,updated_at=? WHERE id=?",[$device,time()+300,instant(),$j['id']]);
            $this->sql("UPDATE members SET innux_state='REMOVAL_RUNNING' WHERE id=?",[$j['member_id']]);
            $this->audit('connector:'.$device,'MEMBER_RETIREMENT_CLAIMED',$j['id'],['client_id'=>$o['client_id']]);
            return ['removal'=>['id'=>$j['id'],'client_id'=>$o['client_id'],'number'=>$o['innux_number'],'document'=>$o['document'],'birth_date'=>$o['birth_date'],'name'=>$o['name']??'','include_fiscal'=>(bool)$o['include_fiscal']]];
        });
        if($op==='search_claim')return $this->transaction(function()use($device){
            $this->sql("UPDATE innux_searches SET state='FAILED',error_code='CONNECTOR_TIMEOUT',updated_at=? WHERE state IN ('QUEUED','RUNNING') AND created_at<?",[instant(),gmdate('Y-m-d\TH:i:s\Z',time()-60)]);
            // Como en un autocompletado: solo cuenta la ultima busqueda; las anteriores se descartan sin trabajo.
            $s=$this->one("SELECT * FROM innux_searches WHERE state='QUEUED' ORDER BY created_at DESC,rowid DESC LIMIT 1");if(!$s)return ['search'=>null];
            $this->sql("UPDATE innux_searches SET state='FAILED',error_code='SUPERSEDED',updated_at=? WHERE state='QUEUED' AND id<>? AND actor=?",[instant(),$s['id'],$s['actor']]);
            $this->sql("UPDATE innux_searches SET state='RUNNING',updated_at=? WHERE id=?",[instant(),$s['id']]);
            return ['search'=>['id'=>$s['id'],'query'=>$this->open($s['query_enc'],'innux_search_query')]];
        });
        if($op==='search_result')return $this->transaction(function()use($device,$r){
            $id=textField($r,'search_id',32);$s=$this->one("SELECT * FROM innux_searches WHERE id=? AND state='RUNNING'",[$id]);ensure($s,'Búsqueda no disponible.',404);
            if(($r['state']??'')==='FAILED'){$code=(string)($r['error_code']??'');ensure(preg_match('/^[A-Z0-9_]{1,60}$/',$code)===1,'Código no válido.');$this->sql("UPDATE innux_searches SET state='FAILED',error_code=?,updated_at=? WHERE id=?",[$code,instant(),$id]);return ['state'=>'FAILED'];}
            ensure(($r['state']??'')==='DONE'&&is_array($r['items']??null)&&count($r['items'])<=25,'Resultado no válido.');$items=[];
            foreach($r['items'] as $it){ensure(is_array($it)&&preg_match('/^[1-9][0-9]{0,9}$/',(string)($it['client_id']??''))===1&&preg_match('/^[1-9][0-9]{0,9}$/',(string)($it['number']??''))===1,'Resultado no válido.');
                $items[]=['client_id'=>(string)$it['client_id'],'number'=>(string)$it['number'],'name'=>textField($it,'name',100,false),'document'=>textField($it,'document',20,false),'birth_date'=>textField($it,'birth_date',10,false),'email'=>textField($it,'email',100,false),'phone'=>textField($it,'phone',30,false),'active'=>($it['active']??false)===true];}
            $this->sql("UPDATE innux_searches SET state='DONE',result_enc=?,updated_at=? WHERE id=?",[$this->seal($items,'innux_search'),instant(),$id]);return ['state'=>'DONE'];
        });
        $id=textField($r,'job_id',32);$j=$this->one('SELECT * FROM member_retirements WHERE id=? AND device_id=?',[$id,$device]);ensure($j,'Baja no disponible.',404);
        if($op==='removal_check'){
            ensure($j['state']==='RUNNING','Baja detenida para revisión.',409);
            $this->sql('UPDATE member_retirements SET lease_until=? WHERE id=?',[time()+300,$id]);return ['authorized'=>true];
        }
        ensure($op==='removal_result','Operación no disponible.',404);
        return $this->transaction(function()use($j,$r,$id,$device){
            $j=$this->one('SELECT * FROM member_retirements WHERE id=?',[$id]);if($j['state']==='COMPLETED')return ['state'=>'COMPLETED'];
            ensure($j['state']!=='CANCELLED','La baja está cancelada.',409);
            $state=$r['state']??'';ensure(in_array($state,['COMPLETED','REVIEW_REQUIRED','QUEUED'],true),'Estado no válido.');
            $code=(string)($r['error_code']??'');ensure(preg_match('/^[A-Z0-9_]{0,60}$/',$code)===1,'Código no válido.');
            // Un COMPLETED es un hecho (la ficha ya no existe) y se acepta aunque la concesion haya caducado.
            if($state!=='COMPLETED')ensure($j['state']==='RUNNING','El resultado no corresponde a una baja en marcha.',409);
            if($state==='QUEUED')ensure($code==='INNUX_BUSY','Reintento no permitido.',409);
            $summary=$r['summary']??[];ensure(is_array($summary)&&strlen(jencode($summary))<60000,'Resumen no válido.');
            $options=$this->open($j['options_enc'],'retirement_options');$now=instant();
            if($state==='COMPLETED'){
                ensure((string)($r['client_id']??'')===(string)$options['client_id']&&preg_match('/^[a-f0-9]{64}$/',(string)($summary['archive_sha256']??''))===1,'Resultado de baja incompleto.',409);
                $this->sql("UPDATE members SET innux_reference=NULL,innux_state='REMOVED' WHERE id=?",[$j['member_id']]);
                if(!empty($options['deferred'])){  // baja programada: los efectos en el portal se aplican al hacerse efectiva
                    $this->sql("UPDATE members SET state='BAJA' WHERE id=?",[$j['member_id']]);
                    $this->sql("UPDATE mandates SET state='REVOKED',revoked_at=? WHERE member_id=? AND state<>'REVOKED'",[$now,$j['member_id']]);
                    $this->sql("UPDATE dues SET state='CANCELLED',revision=revision+1 WHERE member_id=? AND state='PREPARED'",[$j['member_id']]);
                    $this->sql("UPDATE contracts SET state='CANCELLED' WHERE member_id=? AND state='SIGNED' AND center_accepted_at IS NULL",[$j['member_id']]);
                }
                $this->sql("UPDATE member_retirements SET state='COMPLETED',error_code=NULL,result_enc=?,completed_at=?,updated_at=? WHERE id=?",[$this->seal($summary,'retirement_result'),$now,$now,$id]);
                $this->audit('connector:'.$device,'INNUX_MEMBER_REMOVED',$id,['client_id'=>$options['client_id'],'counts'=>$summary['counts']??[],'archive_sha256'=>$summary['archive_sha256']]);
                return ['state'=>'COMPLETED'];
            }
            $this->sql('UPDATE member_retirements SET state=?,error_code=?,result_enc=?,lease_until=NULL,updated_at=? WHERE id=?',[$state,$code,$summary?$this->seal($summary,'retirement_result'):$j['result_enc'],$now,$id]);
            $this->sql('UPDATE members SET innux_state=? WHERE id=?',[$state==='QUEUED'?'REMOVAL_QUEUED':'REMOVAL_REVIEW',$j['member_id']]);
            $this->audit('connector:'.$device,'INNUX_MEMBER_REMOVAL_'.$state,$id,['code'=>$code,'counts'=>$summary['counts']??[]]);
            return ['state'=>$state];
        });
    }
}
