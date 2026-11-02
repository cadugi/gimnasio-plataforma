<?php
declare(strict_types=1);
/**
 * Acceso desde el Centro de control con tickets firmados de un solo uso (SSO interno).
 * El Centro de control ya autenticó a la persona (usuario + contraseña + 2FA) y firma un ticket de 60 s con una clave
 * compartida (fichero 600, nunca llega al navegador). Aquí se comprueba firma, módulo, caducidad y uso único y se abre
 * sesión a nombre de ESA persona con SU rol: los permisos son los del rol y la auditoría identifica a quien actúa.
 */
trait SsoOperations {
    private const SSO_ROLES=['admin','staff','viewer'];
    private function ssoKey():string{
        $file=$this->config['sso_key_file']??dirname($this->config['database']).'/sso.key';
        $key=is_file($file)?trim((string)file_get_contents($file)):'';
        ensure(strlen($key)>=32,'Acceso desde el Centro de control no configurado.',401);
        return $key;
    }
    private static function b64u(string $v):string{return rtrim(strtr(base64_encode($v),'+/','-_'),'=');}
    private static function b64ud(string $v):string{$r=base64_decode(strtr($v,'-_','+/').str_repeat('=',(4-strlen($v)%4)%4),true);return $r===false?'':$r;}
    /** Solo para pruebas y para el emisor: misma construcción que Cuentas. */
    public static function ssoSign(string $key,array $payload):string{
        ksort($payload);$body=self::b64u(json_encode($payload,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE));
        return 'v1.'.$body.'.'.hash_hmac('sha256','v1.'.$body,$key);
    }
    public function ssoVerify(string $ticket,?int $now=null,string $operation='login'):array{
        $bad=fn()=>new AppError('Ticket no válido.',401);
        $parts=explode('.',$ticket);if(count($parts)!==3||$parts[0]!=='v1')throw $bad();
        $key=$this->ssoKey();
        if(!hash_equals(hash_hmac('sha256','v1.'.$parts[1],$key),$parts[2]))throw $bad();
        $p=json_decode(self::b64ud($parts[1]),true);if(!is_array($p))throw $bad();
        $t=$now??time();
        if(($p['mod']??'')!=='altas'||($p['op']??'login')!==$operation)throw $bad();
        if(!is_int($p['iat']??null)||!is_int($p['exp']??null)||$p['exp']<$t||$p['iat']>$t+30||$p['exp']-$p['iat']>120)throw new AppError('Ticket caducado.',401);
        if(!in_array($p['role']??'',self::SSO_ROLES,true))throw new AppError('Rol no válido.',401);
        $sub=(string)($p['sub']??'');
        if($sub===''||strlen($sub)>40||preg_match('/^[A-Za-z0-9._-]+$/',$sub)!==1||$sub[0]==='.'||empty($p['jti'])||!is_string($p['jti'])||strlen($p['jti'])>64)throw $bad();
        return $p;
    }
    public function ssoLogout(array $p):void{
        $this->transaction(function()use($p){
            ensure(!$this->one('SELECT jti FROM sso_tickets WHERE jti=?',[$p['jti']]),'Ticket ya utilizado.',401);
            $this->sql('INSERT INTO sso_tickets(jti,expires) VALUES(?,?)',[$p['jti'],time()+600]);
            $name=$p['sub']==='qa_total'?'qa_total':'cc.'.$p['sub'];
            $u=$this->one('SELECT id FROM users WHERE username=?',[$name]);
            if($u){$this->sql('UPDATE users SET epoch=epoch+1 WHERE id=?',[$u['id']]);$this->audit($u['id'],'LOGOUT_SSO',$u['id']);}
        });
    }
    /** Consume el ticket y devuelve la fila del usuario (rol refrescado en cada entrada). */
    public function ssoLogin(array $p):array{
        return $this->transaction(function()use($p){
            $this->sql('DELETE FROM sso_tickets WHERE expires<?',[time()]);
            ensure(!$this->one('SELECT jti FROM sso_tickets WHERE jti=?',[$p['jti']]),'Ticket ya utilizado.',401);
            $this->sql('INSERT INTO sso_tickets(jti,expires) VALUES(?,?)',[$p['jti'],time()+600]);
            $username=$p['sub']==='qa_total'?'qa_total':'cc.'.$p['sub'];$u=$this->one('SELECT * FROM users WHERE username=?',[$username]);
            // QA_TOTAL: identidad nominal preexistente; SSO no puede crearla ni reactivarla.
            if($p['sub']==='qa_total'){
                ensure($u&&(int)$u['active']===1&&$u['role']==='admin'&&$p['role']==='admin','Cuenta QA no disponible.',401);
            }elseif($u){
                ensure((int)$u['sso']===1,'Ticket no válido.',401);   // nunca se pisa una cuenta de personal normal
                $this->sql('UPDATE users SET role=?,active=1 WHERE id=?',[$p['role'],$u['id']]);
            }else{
                $id=uuid();
                $this->sql('INSERT INTO users(id,username,password_hash,role,active,epoch,created_at,sso) VALUES(?,?,?,?,1,1,?,1)',[$id,$username,password_hash(bin2hex(random_bytes(32)),PASSWORD_DEFAULT),$p['role'],instant()]);
                $this->audit('sso','USER_SSO_CREATED',$id,['username'=>$username,'role'=>$p['role']]);
            }
            $u=$this->one('SELECT * FROM users WHERE username=?',[$username]);
            $this->audit($u['id'],'LOGIN_SSO',$u['id'],['display'=>(string)($p['name']??$p['sub']),'role'=>$p['role']]);
            return $u;
        });
    }
}
