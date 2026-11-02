<?php
declare(strict_types=1);

trait InnuxConnectorOperations {
    private const SERIES_MIN=6325;
    private const SERIES_MAX=19999;
    /** Números ya usados por altas de la serie: trabajos (aunque estén cancelados), fichas vinculadas y el mayor número dado jamás. */
    private function innuxSeriesReserved():array {
        $jobs=array_map(fn($v)=>(int)$v['number'],$this->sql('SELECT number FROM innux_jobs WHERE number BETWEEN ? AND ?',[self::SERIES_MIN,self::SERIES_MAX]));
        $members=array_map(fn($v)=>(int)$v['innux_number'],$this->sql("SELECT innux_number FROM members WHERE innux_number GLOB '[0-9]*' AND CAST(innux_number AS INTEGER) BETWEEN ? AND ?",[self::SERIES_MIN,self::SERIES_MAX]));
        $high=$this->one("SELECT value FROM settings WHERE name='member_number_high_water'");
        $high=$high&&ctype_digit((string)$high['value'])&&(int)$high['value']>=self::SERIES_MIN&&(int)$high['value']<=self::SERIES_MAX?[(int)$high['value']]:[];
        return array_values(array_unique([...$jobs,...$members,...$high]));
    }
    /** Número propuesto por el agente tras mirar Innux: dentro de la serie, nunca reutilizado y por encima de todo lo reservado. */
    private function innuxSeriesNumber(mixed $candidate,string $jobId):int {
        ensure(is_int($candidate)&&$candidate>=self::SERIES_MIN&&$candidate<=self::SERIES_MAX,'Número de socio fuera de la serie.',409);
        ensure(!$this->one('SELECT id FROM innux_jobs WHERE number=? AND id<>?',[$candidate,$jobId])&&!$this->one('SELECT id FROM members WHERE innux_number=?',[(string)$candidate]),'Número ya reservado.',409);
        $reserved=$this->innuxSeriesReserved();
        ensure(!$reserved||$candidate>max($reserved),'El número debe ser posterior a los ya reservados.',409);
        return $candidate;
    }
    private function recordSeriesNumber(int $number):void {
        $this->sql('UPDATE innux_sequence SET next_number=MAX(next_number,?) WHERE id=1',[$number+1]);
        $this->sql("INSERT INTO settings(name,value) VALUES('member_number_high_water',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",[(string)$number]);
    }
    private function innuxNumberingPolicy():array {
        $row=$this->one("SELECT value FROM settings WHERE name='innux_temporary_numbering'");
        if(!$row)return ['mode'=>'PRODUCTION_ASCENDING','next_number'=>(int)$this->one('SELECT next_number FROM innux_sequence WHERE id=1')['next_number']];
        $p=json_decode($row['value'],true,8,JSON_THROW_ON_ERROR);
        $mode=$p['mode']??'';
        ensure(in_array($mode,['TABLET_TEST_DESCENDING','TABLET_TEST_ASCENDING'],true)&&is_int($p['next_number']??null),'Revisa la numeración temporal.',409);
        $minimum=$mode==='TABLET_TEST_ASCENDING'?1000000:6325;
        ensure($p['next_number']>=($mode==='TABLET_TEST_ASCENDING'?$minimum:$minimum-1)&&$p['next_number']<=($mode==='TABLET_TEST_ASCENDING'?2147483647:2147483646),'Revisa la numeración temporal.',409);
        return ['mode'=>$mode,'next_number'=>$p['next_number'],'minimum'=>$minimum,'maximum'=>2147483646];
    }
    public function authorizeExistingInnux(string $job):array {
        $this->staff(['admin','staff']);
        return $this->transaction(function()use($job){
            $j=$this->one('SELECT * FROM innux_jobs WHERE id=?',[$job]);ensure($j&&$j['state']==='REVIEW_REQUIRED','Revisa el estado del alta antes de vincular.',409);
            $c=$this->one('SELECT * FROM contracts WHERE id=?',[$j['contract_id']]);
            ensure($c&&$c['state']==='SIGNED'&&$c['center_accepted_at'],'Falta un contrato firmado y aceptado.',409);
            $m=$this->one('SELECT innux_reference FROM members WHERE id=?',[$j['member_id']]);ensure($m&&!$m['innux_reference'],'La ficha ya esta vinculada.',409);
            $options=$this->open($j['options_enc'],'innux_options');$options['mode']='LINK_EXISTING_ONLY';
            $this->sql("UPDATE innux_jobs SET options_enc=?,state='QUEUED',error_code=NULL,updated_at=? WHERE id=?",[$this->seal($options,'innux_options'),instant(),$job]);
            $this->sql("UPDATE members SET innux_state='QUEUED' WHERE id=?",[$j['member_id']]);
            $this->audit($this->actor(),'INNUX_EXISTING_LINK_AUTHORIZED',$job,['changes_to_innux'=>false]);return ['state'=>'QUEUED'];
        });
    }
    private function innuxJobPayload(array $j,array $c,int $number):array {
        $s=$this->open($c['snapshot_enc']);$photo=$this->one('SELECT image_enc FROM contract_photos WHERE contract_id=?',[$c['id']]);
        $s['bank']=null;
        return ['job'=>['id'=>$j['id'],'contract_id'=>$c['id'],'number'=>$number,'snapshot'=>$s,'options'=>$this->open($j['options_enc'],'innux_options'),'photo'=>$photo?base64_encode($this->vault->decrypt($photo['image_enc'],'photo')):null]];
    }
    public function innuxStatus(string $member=''):array {
        $this->staff(['admin','staff']);
        $devices=$this->sql('SELECT id,last_seen,catalog_enc FROM innux_devices WHERE active=1 ORDER BY last_seen DESC');
        $catalog=[];foreach($devices as $d)if($d['catalog_enc']){$catalog=$this->open($d['catalog_enc'],'innux_catalog');break;}
        $job=$member?$this->one('SELECT id,state,number,error_code,updated_at,options_enc FROM innux_jobs WHERE member_id=?',[$member]):null;
        if($job){$job['card_number']=$this->open($job['options_enc'],'innux_options')['card_number'];unset($job['options_enc']);if($job['state']==='COMPLETED'){$m=$this->one('SELECT innux_number,innux_state FROM members WHERE id=?',[$member]);$job['number']=$m['innux_number'];$job['linked_existing']=$m['innux_state']==='VERIFIED_READ_ONLY';}}
        return ['configured'=>count($devices)===1,'last_seen'=>$devices[0]['last_seen']??null,'catalog'=>$catalog,'job'=>$job,'next_number'=>(int)$this->one('SELECT next_number FROM innux_sequence WHERE id=1')['next_number'],'numbering'=>$this->innuxNumberingPolicy()];
    }
    public function enqueueInnux(string $contract,array $options):array {
        $this->staff(['admin','staff']);
        return $this->transaction(function()use($contract,$options){
            $c=$this->one('SELECT * FROM contracts WHERE id=?',[$contract]);
            ensure($c&&$c['state']==='SIGNED'&&$c['center_accepted_at'],'Falta un contrato firmado y aceptado.',409);
            $snapshot=$this->open($c['snapshot_enc']);
            ensure(($snapshot['legal']['approved']??0)==1&&!empty($snapshot['legal']['approval_reference']),'Los textos legales requieren aprobación.',409);
            $m=$this->one('SELECT * FROM members WHERE id=?',[$c['member_id']]);
            ensure(!$m['innux_reference'],'Esta ficha ya está vinculada a Innux.',409);
            $job=$this->one('SELECT id,state,number,error_code FROM innux_jobs WHERE member_id=?',[$m['id']]);
            $retryRejected=$job&&$job['state']==='REVIEW_REQUIRED'&&$job['error_code']==='CONTRACT_NOT_APPROVED';
            if($job&&!$retryRejected)return ['id'=>$job['id'],'state'=>$job['state'],'number'=>$job['number']];
            $device=$this->one('SELECT * FROM innux_devices WHERE active=1');ensure($device&&$device['catalog_enc'],'Falta configurar el conector de Innux de recepción.',409);
            $catalog=$this->open($device['catalog_enc'],'innux_catalog');
            $plan=(string)($options['plan_id']??'');
            $plans=array_filter($catalog['plans']??[],fn($p)=>(string)$p['id']===$plan&&($p['active']??false)===true);
            ensure(count($plans)===1,'Selecciona una tarifa verificada de Innux.',409);
            $group=(string)($options['group_id']??'');$groups=array_filter($catalog['groups']??[],fn($g)=>(string)$g['id']===$group);ensure(count($groups)===1,'Selecciona el grupo de socios de Innux.',409);
            $start=(string)($options['valid_from']??'');$end=(string)($options['valid_until']??'');
            foreach([$start,$end] as $date)ensure(preg_match('/^\d{4}-\d{2}-\d{2}$/',$date)&&($d=DateTimeImmutable::createFromFormat('!Y-m-d',$date))&&$d->format('Y-m-d')===$date,'Revisa las fechas de acceso.');
            ensure($end>=$start&&(new DateTimeImmutable($start))->diff(new DateTimeImmutable($end))->days<=366,'Revisa el periodo de acceso.');
            ensure(($options['authorize_access']??false)===true,'Confirma la autorización de acceso. No registra un cobro bancario.');
            $card=(string)($options['card_number']??'');ensure(preg_match('/^[1-9][0-9]{0,18}$/',$card)&&strlen($card)<=19&&(strlen($card)<19||strcmp($card,'9223372036854775807')<=0),'Introduce el identificador de la ficha, distinto del número de socio.');
            $safe=['plan_id'=>$plan,'group_id'=>$group,'card_number'=>$card,'valid_from'=>$start,'valid_until'=>$end,'authorize_access'=>true,'actor'=>$this->actor()];
            if($retryRejected){
                // Explicit staff submission only. The local agent also requires
                // NOT_STARTED: attempts that reached the UI remain fenced.
                $this->sql("UPDATE innux_jobs SET state='QUEUED',error_code=NULL,options_enc=?,updated_at=? WHERE id=?",[$this->seal($safe,'innux_options'),instant(),$job['id']]);
                $this->sql("UPDATE members SET innux_state='QUEUED' WHERE id=?",[$m['id']]);
                $this->audit($this->actor(),'INNUX_REJECTED_BEFORE_START_REQUEUED',$job['id'],['contract'=>$contract,'number'=>$job['number'],'explicit_access_authorization'=>true]);
                return ['id'=>$job['id'],'state'=>'QUEUED','number'=>$job['number']];
            }
            $assigned=ctype_digit((string)$m['innux_number'])&&!$this->one('SELECT id FROM innux_jobs WHERE number=?',[(int)$m['innux_number']])?(int)$m['innux_number']:null;
            $id=uuid();$this->sql("INSERT INTO innux_jobs(id,contract_id,member_id,number,state,options_enc,created_at,updated_at) VALUES(?,?,?,?,'QUEUED',?,?,?)",[$id,$contract,$m['id'],$assigned,$this->seal($safe,'innux_options'),instant(),instant()]);
            $this->sql("UPDATE members SET innux_state='QUEUED' WHERE id=?",[$m['id']]);
            $this->audit($this->actor(),'INNUX_ENROLLMENT_QUEUED',$id,['contract'=>$contract,'plan_id'=>$plan,'from'=>$start,'until'=>$end,'payment_recorded'=>false]);
            return ['id'=>$id,'state'=>'QUEUED','number'=>$assigned];
        });
    }
    public function authenticateInnuxDevice(string $raw,array $headers):string {
        ensure(($this->config['request_portal']??'')==='admin','Portal de recepción requerido.',403);
        $id=$headers['id']??'';$at=$headers['timestamp']??'';$nonce=$headers['nonce']??'';$signature=$headers['signature']??'';
        ensure(preg_match('/^[a-f0-9]{32}$/',$id)&&ctype_digit($at)&&abs(time()-(int)$at)<=90&&preg_match('/^[a-f0-9]{32}$/',$nonce),'Conector no autorizado.',401);
        $device=$this->one('SELECT * FROM innux_devices WHERE id=? AND active=1',[$id]);ensure($device,'Conector no autorizado.',401);
        $secret=$this->vault->decrypt($device['secret_enc'],'innux_secret');
        $expected=hash_hmac('sha256',"POST\n/alta/admin/api.php\n$at\n$nonce\n".hash('sha256',$raw),$secret);
        ensure(hash_equals($expected,$signature),'Conector no autorizado.',401);
        $this->transaction(function()use($id,$nonce){
            $this->sql('DELETE FROM innux_nonces WHERE expires<?',[time()]);
            ensure(!$this->one('SELECT nonce FROM innux_nonces WHERE device_id=? AND nonce=?',[$id,$nonce]),'Petición repetida.',409);
            $this->sql('INSERT INTO innux_nonces VALUES(?,?,?)',[$id,$nonce,time()+180]);
            $this->sql('UPDATE innux_devices SET last_seen=? WHERE id=?',[instant(),$id]);
        });return $id;
    }
    public function innuxDeviceOperation(string $device,array $r):array {
        $op=$r['operation']??'';
        if(str_starts_with((string)$op,'removal_')||str_starts_with((string)$op,'search_'))return $this->retirementDeviceOperation($device,$r);
        if($op==='numbering_status'){
            $p=$this->innuxNumberingPolicy();
            $q=$this->one("SELECT id,number FROM innux_jobs WHERE state='QUEUED' ORDER BY created_at LIMIT 1");
            $p['queued_job_id']=$q['id']??null;$p['reserved_number']=$q['number']??null;
            if($p['mode']==='PRODUCTION_ASCENDING'){$p['series_min']=self::SERIES_MIN;$p['series_max']=self::SERIES_MAX;$p['reserved_numbers']=$this->innuxSeriesReserved();return $p;}
            $p['reserved_numbers']=$p['mode']==='TABLET_TEST_DESCENDING'?array_map(fn($v)=>(int)$v['number'],$this->sql('SELECT number FROM innux_jobs WHERE number IS NOT NULL AND number<=?',[$p['next_number']])):($p['mode']==='TABLET_TEST_ASCENDING'?array_map(fn($v)=>(int)$v['number'],$this->sql('SELECT number FROM innux_jobs WHERE number IS NOT NULL AND number>=?',[$p['next_number']])):[]);
            return $p;
        }
        if($op==='heartbeat'){
            $catalog=$r['catalog']??[];ensure(is_array($catalog)&&strlen(jencode($catalog))<40000,'Catálogo no válido.');
            $plans=[];foreach($catalog['plans']??[] as $plan){ensure(ctype_digit((string)($plan['id']??'')),'Tarifa no válida.');$plans[]=['id'=>(string)$plan['id'],'name'=>textField($plan,'name',100),'active'=>($plan['active']??false)===true];}
            $groups=[];foreach($catalog['groups']??[] as $group){ensure(ctype_digit((string)($group['id']??'')),'Grupo no válido.');$groups[]=['id'=>(string)$group['id'],'name'=>textField($group,'name',100)];}
            $this->sql('UPDATE innux_devices SET catalog_enc=? WHERE id=?',[$this->seal(['plans'=>$plans,'groups'=>$groups],'innux_catalog'),$device]);return ['active'=>true];
        }
        if($op==='claim')return $this->transaction(function()use($device,$r){
            $this->sql("UPDATE innux_jobs SET state='REVIEW_REQUIRED',error_code='LEASE_EXPIRED',updated_at=? WHERE state='RUNNING' AND lease_until<?",[instant(),time()]);
            // Reviewed jobs keep their identity and reservation; they are never retried
            // by claim. An expired lease still fences the queue: its worker may be alive.
            if($blocker=$this->one("SELECT state FROM innux_jobs WHERE state='RUNNING' OR (state='REVIEW_REQUIRED' AND error_code='LEASE_EXPIRED')"))return ['job'=>null,'wait_reason'=>$blocker['state']==='RUNNING'?'ACTIVE_WORKER':'LEASE_REQUIRES_REVIEW'];
            $j=$this->one("SELECT * FROM innux_jobs WHERE state='QUEUED' ORDER BY created_at LIMIT 1");if(!$j)return ['job'=>null,'wait_reason'=>'EMPTY_QUEUE'];
            $c=$this->one('SELECT * FROM contracts WHERE id=?',[$j['contract_id']]);
            $snapshot=$c?$this->open($c['snapshot_enc']):[];
            if(!$c||$c['state']!=='SIGNED'||!$c['center_accepted_at']||($snapshot['legal']['approved']??0)!=1||empty($snapshot['legal']['approval_reference'])){
                $this->sql("UPDATE innux_jobs SET state='CANCELLED',error_code='CONTRACT_NOT_APPROVED',updated_at=? WHERE id=?",[instant(),$j['id']]);
                $this->sql("UPDATE members SET innux_state='REVIEW_REQUIRED' WHERE id=?",[$j['member_id']]);
                $this->audit('connector:'.$device,'INNUX_INELIGIBLE_JOB_CANCELLED',$j['id'],['number_reserved'=>$j['number']!==null]);return ['job'=>null,'wait_reason'=>'CONTRACT_NOT_APPROVED'];
            }
            $policy=$this->innuxNumberingPolicy();
            if($j['number'])$number=(int)$j['number'];
            elseif(in_array($policy['mode'],['TABLET_TEST_DESCENDING','TABLET_TEST_ASCENDING'],true)){
                ensure(($r['expected_job_id']??'')===$j['id']&&($r['number_checked_free']??false)===true,'Falta comprobar el número en Innux.',409);
                $candidate=$r['number_candidate']??null;
                $ascending=$policy['mode']==='TABLET_TEST_ASCENDING';
                $low=$ascending?$policy['next_number']:max($policy['minimum'],$policy['next_number']-4095);
                $high=$ascending?min(2147483646,$policy['next_number']+4095):$policy['next_number'];
                ensure(is_int($candidate)&&$candidate>=$low&&$candidate<=$high,'Número temporal no válido.',409);
                ensure(!$this->one('SELECT id FROM innux_jobs WHERE number=?',[$candidate])&&!$this->one('SELECT id FROM members WHERE innux_number=?',[(string)$candidate]),'Número ya reservado.',409);
                $number=$candidate;
                $saved=['mode'=>$policy['mode'],'next_number'=>$number+($ascending?1:-1)];
                $this->sql("UPDATE settings SET value=? WHERE name='innux_temporary_numbering'",[jencode($saved)]);
                $options=$this->open($j['options_enc'],'innux_options');$options['numbering_policy']=$policy['mode'];
                $j['options_enc']=$this->seal($options,'innux_options');
                $this->sql('UPDATE innux_jobs SET options_enc=? WHERE id=?',[$j['options_enc'],$j['id']]);
                $this->audit('connector:'.$device,'INNUX_TEST_NUMBER_RESERVED',$j['id'],['number'=>$number,'mode'=>$policy['mode'],'innux_absence_checked'=>true]);
            }else{
                // Producción: el agente mira Innux (último de la serie + 1); el servidor no inventa números.
                ensure(($r['expected_job_id']??'')===$j['id']&&($r['number_checked_free']??false)===true,'Falta comprobar el número en Innux.',409);
                $number=$this->innuxSeriesNumber($r['number_candidate']??null,$j['id']);
                $this->recordSeriesNumber($number);
                $this->audit('connector:'.$device,'INNUX_NUMBER_RESERVED',$j['id'],['number'=>$number,'mode'=>'PRODUCTION_SERIES','innux_absence_checked'=>true]);
            }
            $this->sql("UPDATE innux_jobs SET number=?,device_id=?,state='RUNNING',lease_until=?,updated_at=? WHERE id=?",[$number,$device,time()+300,instant(),$j['id']]);
            return $this->innuxJobPayload($j,$c,$number);
        });
        ensure(in_array($op,['result','check','resume','renumber','recovery_preview','recover_interrupted','job_status'],true),'Operación no disponible.',404);
        $id=textField($r,'job_id',32);$j=$this->one('SELECT * FROM innux_jobs WHERE id=? AND device_id=?',[$id,$device]);ensure($j,'Alta no disponible.',404);
        if($op==='job_status')return ['id'=>$id,'contract_id'=>$j['contract_id'],'number'=>$j['number'],'state'=>$j['state'],
            'error_code'=>$j['error_code'],'result'=>$j['state']==='COMPLETED'?$this->open($j['result_enc'],'innux_result'):null];
        if($op==='renumber')return $this->transaction(function()use($id,$device,$r){
            // Solo si el número se ocupó antes de crear nada: el agente confirma que la ficha de este trabajo no existe.
            $j=$this->one('SELECT * FROM innux_jobs WHERE id=? AND device_id=?',[$id,$device]);
            ensure($j&&$j['state']==='RUNNING'&&$j['number']!==null&&($r['reason']??'')==='NUMBER_OCCUPIED','El trabajo no admite cambio de número.',409);
            $options=$this->open($j['options_enc'],'innux_options');$count=(int)($options['renumbers']??0);
            ensure($count<3,'Demasiados cambios de número. Requiere revisión.',409);
            ensure(($r['number_checked_free']??false)===true,'Falta comprobar el número en Innux.',409);
            $new=$this->innuxSeriesNumber($r['number_candidate']??null,$id);ensure($new>(int)$j['number'],'El nuevo número debe ser posterior.',409);
            $options['renumbers']=$count+1;
            $this->sql('UPDATE innux_jobs SET number=?,options_enc=?,updated_at=? WHERE id=?',[$new,$this->seal($options,'innux_options'),instant(),$id]);
            $this->recordSeriesNumber($new);
            $this->audit('connector:'.$device,'INNUX_NUMBER_REASSIGNED_OCCUPIED',$id,['from'=>(int)$j['number'],'to'=>$new,'attempt'=>$count+1,'innux_absence_checked'=>true,'changes_to_innux'=>false]);
            return ['number'=>$new];
        });
        if($op==='recovery_preview'||$op==='recover_interrupted')return $this->transaction(function()use($j,$r,$id,$device,$op){
            ensure($j['state']==='REVIEW_REQUIRED'&&$j['error_code']==='WORKER_INTERRUPTED','El trabajo no admite esta recuperación.',409);
            ensure($j['number']!==null&&(int)$j['number']>=6325,'Falta el número reservado.',409);
            ensure(($r['contract_id']??'')===$j['contract_id']&&(string)($r['number']??'')===(string)$j['number'],'La solicitud no coincide.',409);
            ensure(!$this->one("SELECT id FROM innux_jobs WHERE id<>? AND number=?",[$id,$j['number']]),'Número reservado por otro trabajo.',409);
            $c=$this->one('SELECT * FROM contracts WHERE id=?',[$j['contract_id']]);
            ensure($c&&$c['state']==='SIGNED'&&$c['center_accepted_at'],'El contrato no está firmado y aceptado.',409);
            $m=$this->one('SELECT innux_reference FROM members WHERE id=?',[$j['member_id']]);ensure($m&&!$m['innux_reference'],'La ficha ya está vinculada.',409);
            $options=$this->open($j['options_enc'],'innux_options');ensure(($options['mode']??'')!=='LINK_EXISTING_ONLY','La vinculación existente no admite este reintento.',409);
            if($op==='recovery_preview')return $this->innuxJobPayload($j,$c,(int)$j['number']);
            ensure(($r['phase']??'')==='NEW_REQUESTED'&&($r['checks_passed']??false)===true,'Faltan las comprobaciones locales.',409);
            ensure(!$this->one("SELECT id FROM innux_jobs WHERE id<>? AND state IN ('RUNNING','REVIEW_REQUIRED')",[$id]),'Hay otro trabajo que requiere revisión.',409);
            $this->sql("UPDATE innux_jobs SET state='RUNNING',error_code=NULL,lease_until=?,updated_at=? WHERE id=?",[time()+300,instant(),$id]);
            $this->sql("UPDATE members SET innux_state='RUNNING' WHERE id=?",[$j['member_id']]);
            $this->audit('connector:'.$device,'INNUX_INTERRUPTED_RETRY_AUTHORIZED',$id,['contract'=>$j['contract_id'],'number'=>(int)$j['number'],'phase'=>'NEW_REQUESTED','checks_passed'=>true]);
            $payload=$this->innuxJobPayload($j,$c,(int)$j['number']);$payload['job']['recovery_authorized']=true;return $payload;
        });
        if($op==='resume')return $this->transaction(function()use($j){
            $j=$this->one('SELECT * FROM innux_jobs WHERE id=?',[$j['id']]);
            ensure($j['state']==='RUNNING'||($j['state']==='REVIEW_REQUIRED'&&$j['error_code']==='LEASE_EXPIRED'),'El alta necesita revisión del trabajador.',409);
            ensure(!$this->one("SELECT id FROM innux_jobs WHERE id<>? AND (state='RUNNING' OR (state='REVIEW_REQUIRED' AND error_code='LEASE_EXPIRED'))",[$j['id']]),'Hay otro trabajador activo o sin resolver.',409);
            $c=$this->one('SELECT * FROM contracts WHERE id=?',[$j['contract_id']]);ensure($c&&$c['state']==='SIGNED'&&$c['center_accepted_at'],'Contrato no disponible.',409);
            $this->sql("UPDATE innux_jobs SET state='RUNNING',lease_until=?,updated_at=? WHERE id=?",[time()+300,instant(),$j['id']]);
            return $this->innuxJobPayload($j,$c,(int)$j['number']);
        });
        if($op==='check'){
            $c=$this->one('SELECT state,center_accepted_at FROM contracts WHERE id=?',[$j['contract_id']]);
            ensure($j['state']==='RUNNING'&&$c&&$c['state']==='SIGNED'&&$c['center_accepted_at'],'Alta detenida para revisión.',409);
            $this->sql('UPDATE innux_jobs SET lease_until=? WHERE id=?',[time()+300,$id]);return ['authorized'=>true];
        }
        return $this->transaction(function()use($j,$r,$id,$device){
            $j=$this->one('SELECT * FROM innux_jobs WHERE id=? AND device_id=?',[$id,$device]);
            $state=$r['state']??'';ensure(in_array($state,['COMPLETED','REVIEW_REQUIRED','QUEUED'],true),'Estado no válido.');
            if($j['state']==='COMPLETED')return ['state'=>'COMPLETED'];
            ensure($j['state']!=='CANCELLED','El alta está cancelada.',409);
            $code=(string)($r['error_code']??'');ensure(preg_match('/^[A-Z0-9_]{0,60}$/',$code),'Código no válido.');
            if($state==='QUEUED')ensure($code==='INNUX_BUSY'&&in_array($j['state'],['RUNNING','QUEUED'],true),'Reintento no permitido.',409);
            $result=[];
            if($state==='COMPLETED'){
                $current=$this->one('SELECT state FROM contracts WHERE id=?',[$j['contract_id']]);ensure($current&&$current['state']==='SIGNED','El contrato requiere revisión tras el guardado.',409);
                $options=$this->open($j['options_enc'],'innux_options');
                if(($options['mode']??'')==='LINK_EXISTING_ONLY'){
                    foreach(['client_id','number'] as $field)ensure(ctype_digit((string)($r[$field]??''))&&(int)$r[$field]>0,'Falta comprobar la ficha existente.');
                    ensure(!$this->one('SELECT id FROM members WHERE id<>? AND (innux_reference=? OR innux_number=?)',[$j['member_id'],'INNUX:'.$r['client_id'],(string)$r['number']]),'Ficha vinculada a otro registro.',409);
                    $this->sql("UPDATE members SET innux_reference=?,innux_number=?,innux_state='VERIFIED_READ_ONLY' WHERE id=?",['INNUX:'.$r['client_id'],(string)$r['number'],$j['member_id']]);
                    $next=(int)$this->one('SELECT next_number FROM innux_sequence WHERE id=1')['next_number'];
                    if(!str_starts_with($options['numbering_policy']??'','TABLET_TEST_')&&$j['number']&&($r['unused_number_free']??false)===true&&$next===(int)$j['number']+1&&!$this->one('SELECT id FROM innux_jobs WHERE id<>? AND number>=?',[$id,$j['number']])){
                        $this->sql('UPDATE innux_sequence SET next_number=? WHERE id=1',[(int)$j['number']]);
                        $this->sql('UPDATE innux_jobs SET number=NULL WHERE id=?',[$id]);
                    }
                    $result=['client_id'=>(string)$r['client_id'],'number'=>(string)$r['number'],'operation'=>'LINK_EXISTING_ONLY'];
                    $this->sql("UPDATE innux_jobs SET state='COMPLETED',error_code=NULL,result_enc=?,updated_at=? WHERE id=?",[$this->seal($result,'innux_result'),instant(),$id]);
                    $this->audit('connector:'.$device,'INNUX_EXISTING_LINKED',$id,['changes_to_innux'=>false]);return ['state'=>'COMPLETED','linked_existing'=>true];
                }
                foreach(['client_id','number','card_id','quota_id'] as $field)ensure(ctype_digit((string)($r[$field]??''))&&(int)$r[$field]>0,'Falta la comprobación de alta, tarjeta y cuota.');
                ensure((int)$r['number']===(int)$j['number'],'Numeración no coincidente.',409);
                ensure(!$this->one('SELECT id FROM members WHERE id<>? AND (innux_reference=? OR innux_number=?)',[$j['member_id'],'INNUX:'.$r['client_id'],(string)$r['number']]),'Vinculación duplicada.',409);
                foreach(['client_id','number','card_id','quota_id'] as $field)$result[$field]=(string)$r[$field];
                $this->sql("UPDATE members SET innux_reference=?,innux_number=?,innux_state='VERIFIED_CONNECTOR' WHERE id=?",['INNUX:'.$r['client_id'],(string)$r['number'],$j['member_id']]);
            }else $this->sql('UPDATE members SET innux_state=? WHERE id=?',[$state,$j['member_id']]);
            $this->sql('UPDATE innux_jobs SET state=?,error_code=?,result_enc=?,updated_at=? WHERE id=?',[$state,$code,$this->seal($result,'innux_result'),instant(),$id]);
            $this->audit('connector:'.$device,'INNUX_'.$state,$id,['code'=>$code,'result'=>$result]);return ['state'=>$state];
        });
    }
}
