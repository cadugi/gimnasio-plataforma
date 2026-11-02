<?php
declare(strict_types=1);
trait TabletOperations {
    public function issueTabletInvite(array $payload=[]):array {
        $u=$this->staff(['admin','staff','finance']);
        $code=strtoupper(bin2hex(random_bytes(8)));$id=uuid();$expires=gmdate('Y-m-d\TH:i:s\Z',time()+900);
        $this->transaction(function()use($u,$code,$id,$expires,$payload){
            $this->sql('DELETE FROM tablet_invitations WHERE expires_at<?',[instant()]);
            $this->sql('INSERT INTO tablet_invitations(id,code_hash,issuer_id,payload_enc,created_at,expires_at) VALUES(?,?,?,?,?,?)',[$id,$this->vault->fingerprint('tablet:'.$code),$u['id'],$this->seal($payload),instant(),$expires]);
            $this->audit($u['id'],'TABLET_ACTIVATION_ISSUED',$id,['expires_at'=>$expires]);
        });
        $response=['tablet_invitation'=>true,'code'=>$code,'expires_at'=>$expires,'client_url'=>'/alta/'];
        if(($this->config['request_portal']??'')==='admin'){
            $_SESSION=['csrf'=>uuid()];session_regenerate_id(true);
            $response['csrf']=$_SESSION['csrf'];$response['staff_session_closed']=true;
        }
        return $response;
    }
    public function activateTablet(array $r):array {
        ensure(empty($_SESSION['mode']),'Bloquea la tablet antes de introducir un nuevo código.',409);
        $this->limit('tablet-activation:'.($_SERVER['REMOTE_ADDR']??''),8,900);
        $code=strtoupper(preg_replace('/[\s-]/','',textField($r,'code',40)));
        ensure(preg_match('/^[A-F0-9]{16}$/',$code)===1,'Código no válido o caducado.',403);
        $invite=$this->transaction(function()use($code){
            $i=$this->one('SELECT i.* FROM tablet_invitations i JOIN users u ON u.id=i.issuer_id WHERE i.code_hash=? AND i.used_at IS NULL AND i.expires_at>? AND u.active=1 AND u.role IN (\'admin\',\'staff\',\'finance\')',[$this->vault->fingerprint('tablet:'.$code),instant()]);
            ensure($i,'Código no válido o caducado.',403);
            $payload=$this->open($i['payload_enc']);
            if(($payload['kind']??'')==='holder')ensure($this->one("SELECT id FROM mandates WHERE id=? AND state='PENDING_HOLDER'",[$payload['snapshot']['mandate_id']]),'La autorización ya no está disponible.',409);
            $this->sql('UPDATE tablet_invitations SET used_at=? WHERE id=?',[instant(),$i['id']]);
            $this->audit($i['issuer_id'],'TABLET_ACTIVATED',$i['id']);
            return ['issuer_id'=>$i['issuer_id'],'payload'=>$payload];
        });
        $expires=time()+(int)($this->config['tablet_device_seconds']??28800);
        session_regenerate_id(true);
        $_SESSION=['mode'=>'kiosk','kiosk_locked'=>true,'device_actor'=>$invite['issuer_id'],'device_expires_at'=>$expires,'csrf'=>uuid(),'last_activity'=>time()];
        $payload=$invite['payload'];
        if(($payload['kind']??'')==='holder'){
            $snapshot=$payload['snapshot'];$draft=uuid();$hash=hash('sha256',jencode($snapshot));
            $this->sql('INSERT INTO drafts(id,session_hash,data_enc,review_enc,review_hash,expires_at,updated_at) VALUES(?,?,?,?,?,?,?)',[$draft,$this->sessionHash(),$this->seal(['type'=>'holder','mandate_id'=>$snapshot['mandate_id']]),$this->seal($snapshot),$hash,gmdate('Y-m-d\TH:i:s\Z',time()+1800),instant()]);
            $_SESSION['holder_mandate']=$snapshot['mandate_id'];$_SESSION['draft_id']=$draft;
        }elseif(!empty($payload['prefill']))$this->newDraft($payload['prefill']);
        return ['activated'=>true,'csrf'=>$_SESSION['csrf'],'device_expires_at'=>$expires];
    }
    public function lockTablet():array {
        $this->kiosk();$this->cancelDraft();$_SESSION=['csrf'=>uuid()];session_regenerate_id(true);
        return ['csrf'=>$_SESSION['csrf'],'locked'=>true];
    }
}
