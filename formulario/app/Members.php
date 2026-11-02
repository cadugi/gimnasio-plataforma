<?php
declare(strict_types=1);
/** Consulta unificada. Nunca crea ni vincula socios ni modifica cuotas o contratos. */
trait MemberOperations {
    private function memberReader():array{return $this->staff(['admin','staff','viewer']);}
    private function memberFold(string $s):string{return mb_strtolower(strtr(trim($s),['á'=>'a','é'=>'e','í'=>'i','ó'=>'o','ú'=>'u','ü'=>'u','ñ'=>'n','Á'=>'a','É'=>'e','Í'=>'i','Ó'=>'o','Ú'=>'u','Ü'=>'u','Ñ'=>'n']),'UTF-8');}
    private function memberSummary(array $m):array{
        $p=$this->open($m['personal_enc']);
        return ['id'=>$m['id'],'name'=>trim(($p['name']??'').' '.($p['surname']??'')),'phone'=>$p['phone']??'','email'=>$p['email']??'','number'=>$m['innux_number'],'innux_reference'=>$m['innux_reference'],'reference'=>$m['internal_reference'],'state'=>$m['state']];
    }
    public function memberSearch(array $r):array{
        $this->memberReader();$q=trim((string)($r['query']??''));ensure(mb_strlen($q)>=2&&mb_strlen($q)<=60,'Escribe entre 2 y 60 caracteres.');
        $needle=$this->memberFold($q);$digits=preg_replace('/\D/','',$q);$items=[];$more=false;
        // Los datos personales están cifrados: se filtran dentro de Altas, sin crear un índice en claro.
        foreach($this->sql('SELECT id,personal_enc,innux_number,innux_reference,internal_reference,state FROM members ORDER BY created_at DESC,id') as $m){
            $v=$this->memberSummary($m);$hit=str_contains($this->memberFold($v['name']),$needle)||(str_contains($q,'@')&&str_contains($this->memberFold($v['email']),$needle))||(str_starts_with(strtoupper($q),'TF-')&&str_contains($this->memberFold($v['reference']),$needle))||($v['number']!==null&&(string)$v['number']===$q);
            if(!$hit&&strlen($digits)>=3)$hit=str_contains(preg_replace('/\D/','',$v['phone']),$digits);
            if(!$hit)continue;if(count($items)===30){$more=true;break;}$items[]=$v;
        }
        $this->transaction(fn()=>$this->audit($this->actor(),'MEMBERS_SEARCHED','members',['count'=>count($items)]));
        return ['items'=>$items,'has_more'=>$more];
    }
    public function memberDetail(array $r):array{
        $u=$this->memberReader();$m=null;
        if(!empty($r['id'])){ensure(preg_match('/^[a-f0-9]{32}$/',(string)$r['id'])===1,'Ficha no válida.');$m=$this->one('SELECT * FROM members WHERE id=?',[$r['id']]);}
        elseif(!empty($r['innux_reference'])){ensure(preg_match('/^INNUX:[1-9][0-9]{0,19}$/',(string)$r['innux_reference'])===1,'Referencia no válida.');$m=$this->one('SELECT * FROM members WHERE innux_reference=?',[$r['innux_reference']]);}
        else throw new AppError('Elige una ficha.',400);
        if(!$m)return ['member'=>null,'contracts'=>[],'dues'=>[],'withdrawals'=>[]];
        $contracts=$this->sql('SELECT c.id,c.reference,c.created_at,c.state,c.center_accepted_at,c.payment_method,c.monthly_cents,t.name tariff FROM contracts c JOIN tariffs t ON t.id=c.tariff_id WHERE member_id=? ORDER BY c.created_at DESC LIMIT 31',[$m['id']]);
        $dues=$u['role']==='admin'?$this->sql('SELECT period,amount_cents,due_date,state FROM dues WHERE member_id=? ORDER BY period DESC LIMIT 31',[$m['id']]):[];
        $withdrawals=$this->sql('SELECT reference,kind,state,effective_date,last_day FROM withdrawals WHERE member_id=? ORDER BY created_at DESC LIMIT 11',[$m['id']]);
        $this->transaction(fn()=>$this->audit($this->actor(),'MEMBER_VIEWED',$m['id']));
        return ['member'=>$this->memberSummary($m),'contracts'=>array_slice($contracts,0,30),'contracts_more'=>count($contracts)>30,'dues'=>array_slice($dues,0,30),'dues_more'=>count($dues)>30,'dues_allowed'=>$u['role']==='admin','withdrawals'=>array_slice($withdrawals,0,10)];
    }
    public function memberInnuxStart(array $r):array{
        $this->memberReader();$q=trim((string)($r['query']??''));ensure(mb_strlen($q)>=2&&mb_strlen($q)<=60,'Escribe entre 2 y 60 caracteres.');$this->limit('member-search:'.$this->actor(),60,60);
        return $this->transaction(function()use($q){
            ensure($this->one('SELECT id FROM innux_devices WHERE active=1'),'Innux no está conectado.',409);
            $id=uuid();$at=instant();$this->sql("INSERT INTO innux_searches(id,actor,query_enc,state,created_at,updated_at) VALUES(?,?,?,'QUEUED',?,?)",[$id,$this->actor(),$this->seal($q,'innux_search_query'),$at,$at]);
            $this->audit($this->actor(),'MEMBERS_INNUX_SEARCHED',$id);return ['id'=>$id];
        });
    }
    public function memberInnuxResult(array $r):array{
        $this->memberReader();$id=(string)($r['id']??'');ensure(preg_match('/^[a-f0-9]{32}$/',$id)===1,'Consulta no válida.');
        $row=$this->one('SELECT * FROM innux_searches WHERE id=? AND actor=?',[$id,$this->actor()]);ensure($row,'Consulta no encontrada.',404);
        ensure($row['created_at']>gmdate('Y-m-d\TH:i:s\Z',time()-1800),'La búsqueda ha caducado. Busca de nuevo.',410);
        if($row['state']!=='DONE')return ['state'=>$row['state'],'items'=>[]];
        $items=[];foreach($this->open($row['result_enc'],'innux_search') as $v){
            $ref='INNUX:'.$v['client_id'];$m=$this->one('SELECT id FROM members WHERE innux_reference=?',[$ref]);
            $items[]=['id'=>(string)$v['client_id'],'number'=>(string)$v['number'],'name'=>(string)$v['name'],'phone'=>(string)($v['phone']??''),'email'=>(string)($v['email']??''),'active'=>(bool)$v['active'],'innux_reference'=>$ref,'portal_id'=>$m['id']??null];
        }
        if(isset($r['client_id'])){$items=array_values(array_filter($items,fn($v)=>$v['id']===(string)$r['client_id']));ensure(count($items)===1,'Socio no encontrado en la búsqueda.',404);}
        return ['state'=>'DONE','items'=>array_slice($items,0,50),'has_more'=>count($items)>50];
    }
}
