<?php
declare(strict_types=1);
date_default_timezone_set('Europe/Madrid');
final class AppError extends RuntimeException {public function __construct(string $message,public int $status=400){parent::__construct($message);}}
function ensure(mixed $ok,string $message,int $status=400):void {if(!$ok)throw new AppError($message,$status);}
function uuid():string{return bin2hex(random_bytes(16));}
function instant():string{return (new DateTimeImmutable('now',new DateTimeZone('UTC')))->format('Y-m-d\TH:i:s\Z');}
function madridToday():string{return (new DateTimeImmutable('now',new DateTimeZone('Europe/Madrid')))->format('Y-m-d');}
function jencode(mixed $v):string{return json_encode($v,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);}
function readConfig(string $root):array {
    $path=getenv('TF_CONFIG_FILE')?:$root.'/.private/config.json';
    ensure(is_file($path),'Ejecuta primero la preparación local.',503);$c=json_decode(file_get_contents($path),true,32,JSON_THROW_ON_ERROR);
    ensure(in_array($c['environment']??'',['demo','production','test'],true),'Entorno no válido.',503);
    $databaseDir=str_replace('\\','/',strtolower(realpath(dirname($c['database']))?:''));$publicDir=str_replace('\\','/',strtolower(realpath($root.'/public')?:''));
    ensure($databaseDir!==''&&$databaseDir!==$publicDir&&!str_starts_with($databaseDir,$publicDir.'/'),'La base de datos debe estar fuera de public.',503);
    $keyPath=str_replace('\\','/',strtolower(realpath(getenv('TF_KEY_FILE')?:($c['key_file']??''))?:''));$sourcePath=str_replace('\\','/',strtolower(realpath($root)));
    ensure($keyPath!==''&&!str_starts_with($keyPath,$sourcePath.'/')&&$keyPath!==str_replace('\\','/',strtolower($c['database'])),'La clave debe existir fuera del proyecto y de la base de datos.',503);return $c;
}
final class Vault {
    private array $keys;
    public function __construct(string $file){ensure(is_file($file),'Falta la clave externa de cifrado.',503);$this->keys=json_decode(file_get_contents($file),true,16,JSON_THROW_ON_ERROR);foreach(['encryption','audit','lookup','backup'] as $k)ensure(strlen(base64_decode($this->keys[$k]??'',true)?:'')===32,'Claves no válidas.',503);}
    public function key(string $name):string{return base64_decode($this->keys[$name],true);}
    public function encrypt(string $value,string $purpose='data'):string{$iv=random_bytes(12);$tag='';$cipher=openssl_encrypt($value,'aes-256-gcm',$this->key($purpose==='backup'?'backup':'encryption'),OPENSSL_RAW_DATA,$iv,$tag,'TF-CONTRACTS:'.$purpose,16);ensure($cipher!==false,'No se pudo cifrar.',503);return base64_encode($iv.$tag.$cipher);}
    public function decrypt(string $value,string $purpose='data'):string{$raw=base64_decode($value,true);ensure($raw!==false&&strlen($raw)>=28,'Documento no válido.',500);$clear=openssl_decrypt(substr($raw,28),'aes-256-gcm',$this->key($purpose==='backup'?'backup':'encryption'),OPENSSL_RAW_DATA,substr($raw,0,12),substr($raw,12,16),'TF-CONTRACTS:'.$purpose);ensure($clear!==false,'No se pudo verificar el documento.',500);return $clear;}
    public function fingerprint(string $v):string{return hash_hmac('sha256',$v,$this->key('lookup'));}
}
class Runtime {
    public PDO $db;public Vault $vault;
    public function __construct(public string $root,public array $config){$this->vault=new Vault(getenv('TF_KEY_FILE')?:$config['key_file']);$this->db=new PDO('sqlite:'.$config['database'],null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);$this->db->exec('PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;');}
    public function sql(string $sql,array $args=[]):array{$s=$this->db->prepare($sql);$s->execute($args);return $s->columnCount()?$s->fetchAll():[];}
    public function one(string $sql,array $args=[]):?array{return $this->sql($sql,$args)[0]??null;}
    public function seal(mixed $v,string $purpose='data'):string{return $this->vault->encrypt(jencode($v),$purpose);}
    public function open(string $v,string $purpose='data'):mixed{return json_decode($this->vault->decrypt($v,$purpose),true,64,JSON_THROW_ON_ERROR);}
    public function transaction(callable $fn):mixed{$this->db->exec('BEGIN IMMEDIATE');try{$v=$fn();$this->db->exec('COMMIT');return $v;}catch(Throwable $e){$this->db->exec('ROLLBACK');throw $e;}}
    public function audit(string $actor,string $action,string $target,array $detail=[]):void{if($this->one("SELECT id FROM users WHERE id=? AND username='qa_total'",[$actor]))$actor='qa_total';$previous=$this->one('SELECT hash FROM audit ORDER BY id DESC LIMIT 1')['hash']??'';$at=instant();$json=jencode(['encrypted'=>$this->seal($detail,'audit_detail')]);$hash=hash_hmac('sha256',jencode([$at,$actor,$action,$target,$json,$previous]),$this->vault->key('audit'));$this->sql('INSERT INTO audit(created_at,actor,action,target,detail_json,previous_hash,hash) VALUES(?,?,?,?,?,?,?)',[$at,$actor,$action,$target,$json,$previous,$hash]);}
    public function limit(string $key,int $max,int $seconds):void{$key=$this->vault->fingerprint($key);$this->transaction(function()use($key,$max,$seconds){$row=$this->one('SELECT * FROM rate_limits WHERE key=?',[$key]);if(!$row||(int)$row['reset_at']<time()){$this->sql('INSERT INTO rate_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=1,reset_at=excluded.reset_at',[$key,time()+$seconds]);return;}ensure((int)$row['count']<$max,'Demasiados intentos. Espera antes de repetir.',429);$this->sql('UPDATE rate_limits SET count=count+1 WHERE key=?',[$key]);});}
    public function bankingStatus(string $brand):array{
        $creditor=json_decode($this->one("SELECT value FROM settings WHERE name='creditor'")['value']??'{}',true);
        $legal=$this->one('SELECT approved,bank_text,sepa_text FROM legal_versions WHERE brand=? AND active=1 ORDER BY created_at DESC LIMIT 1',[$brand]);
        $configured=trim($creditor['name']??'')!==''&&trim($creditor['id']??'')!=='';
        $reviewed=$legal&&(int)$legal['approved']===1&&!preg_match('/(?:^|\n)\s*PENDIENTE\s*:|pendiente de (?:cotejo|revisi[oó]n)|Transcripción del texto visible/iu',($legal['bank_text']??'')."\n".($legal['sepa_text']??''));
        return ['ready'=>$configured&&$reviewed,'reason'=>!$configured?'La domiciliación está pendiente de configurar por recepción.':(!$reviewed?'La domiciliación está pendiente de revisar sus documentos.':''),'profile_ready'=>(bool)$this->one('SELECT id FROM export_profiles WHERE active=1 AND approved=1 LIMIT 1')];
    }
    public function actorDisplay(?string $actor):string{
        if(!$actor)return '—';
        $u=$this->one('SELECT username FROM users WHERE id=?',[$actor]);if($u)return $u['username'];
        if(str_starts_with($actor,'connector:'))return 'Conexión Innux';
        if(str_starts_with($actor,'deployment'))return 'Preparación del sistema';
        if(preg_match('/^[a-f0-9]{32}$/i',$actor))return 'Cuenta anterior';
        return ['mail-worker'=>'Envío de correos','maintenance'=>'Mantenimiento','sso'=>'Acceso del Centro','setup'=>'Preparación','qa_total_provision'=>'Preparación de QA'][$actor]??$actor;
    }
    public function actionDisplay(string $action):string{
        return ['MEMBERS_SEARCHED'=>'Búsqueda de socios','MEMBER_VIEWED'=>'Ficha de socio consultada','MEMBERS_INNUX_SEARCHED'=>'Búsqueda de socios en Innux','ADMIN_ACCESS_INITIALIZED'=>'Acceso del equipo preparado','EMAIL_PROVIDER_PENDING'=>'Correo pendiente del proveedor','ENCRYPTED_BACKUP_CREATED'=>'Copia de seguridad creada','ENROLLMENT_PHOTO_VIEWED'=>'Foto consultada','INNUX_CARD_ASSIGNED_MANUALLY'=>'Tarjeta de acceso asignada','INNUX_DEVICE_PAIRED'=>'Equipo Innux vinculado','INNUX_ENROLLMENT_QUEUED'=>'Alta enviada a Innux','INNUX_EXISTING_LINKED'=>'Socio existente vinculado','INNUX_EXISTING_LINK_AUTHORIZED'=>'Vinculación del socio autorizada','INNUX_FAILED_JOB_CANCELLED'=>'Operación fallida cancelada','INNUX_INTERRUPTED_RETRY_AUTHORIZED'=>'Reintento autorizado','INNUX_MEMBER_REMOVAL_REVIEW_REQUIRED'=>'Eliminación pendiente de revisión','INNUX_NUMBER_REASSIGNED_OCCUPIED'=>'Número ocupado reasignado','INNUX_QUEUED'=>'Operación enviada a Innux','INNUX_REVIEW_REQUIRED'=>'Operación pendiente de revisión','INNUX_TABLET_TEST_AUTHORIZED'=>'Prueba de tablet autorizada','INNUX_TEMP_DESCENDING_ENABLED'=>'Numeración temporal activada','INNUX_TEST_NUMBER_RESERVED'=>'Número de prueba reservado','INNUX_TEST_RANGE_CHANGED_BEFORE_START'=>'Rango de prueba actualizado','MEMBER_RETIREMENT_CLAIMED'=>'Eliminación recogida por Innux','MEMBER_RETIREMENT_REQUESTED'=>'Eliminación solicitada','OWNER_AUTHORIZED_TEST_RESET'=>'Reinicio de prueba autorizado','RETIREMENT_ARCHIVE_VIEWED'=>'Archivo de eliminación consultado','TABLET_CONNECTION_TEST_AUTHORIZED'=>'Prueba de conexión autorizada','TABLET_CONNECTION_TEST_BOUND'=>'Prueba asociada al borrador','TABLET_CONNECTION_TEST_COMPLETED'=>'Prueba de conexión terminada','TARIFF_SAVED'=>'Tarifa guardada','TEMPORARY_TEST_ACCESS'=>'Acceso temporal de pruebas','TEST_MEMBER_NUMBER_RELEASED'=>'Número de prueba liberado','WITHDRAWAL_ACCEPTED'=>'Baja o mantenimiento aceptado','WITHDRAWAL_SIGNED'=>'Baja o mantenimiento firmado','QA_REQUEST'=>'Consulta de pantalla','LOGIN'=>'Inicio de sesión','LOGIN_SSO'=>'Acceso desde el Centro','LOGOUT_SSO'=>'Sesión cerrada desde el Centro','USER_SAVED'=>'Usuario actualizado','USER_SSO_CREATED'=>'Usuario del Centro registrado','CONTRACT_SIGNED'=>'Contrato firmado','CENTER_ACCEPTED'=>'Contrato aceptado','EMAIL_SENT'=>'Correo enviado','MEMBERS_EXPORTED'=>'Listado de socios descargado','DOCUMENT_DOWNLOADED'=>'Documento descargado','TABLET_ACTIVATED'=>'Tablet activada','TABLET_ACTIVATION_ISSUED'=>'Código de tablet generado','INNUX_COMPLETED'=>'Alta terminada en Innux','LEGAL_VERSION_CREATED'=>'Textos actualizados','QA_DISABLE'=>'Cuenta de pruebas desactivada','QA_TEST_DRAFT_CANCELLED'=>'Borrador de pruebas retirado'][$action]??'Actividad registrada';
    }
    public function actor():string{return (string)($_SESSION['user_id']??$_SESSION['device_actor']??'reception');}
    public function staff(array $roles=['admin','staff','finance','viewer']):array{ensure(($_SESSION['mode']??'')==='admin','Acceso de trabajador requerido.',401);$u=$this->one('SELECT id,username,role,active,epoch FROM users WHERE id=?',[$_SESSION['user_id']??'']);ensure($u&&(int)$u['active']===1&&(int)$u['epoch']===($_SESSION['epoch']??0),'Sesión no válida.',401);ensure(in_array($u['role'],$roles,true),'No tienes permiso para esta operación.',403);return $u;}
    public function kiosk():void{ensure(($_SESSION['mode']??'')==='kiosk','Inicia el modo recepción con un trabajador.',403);}
    public function demo():bool{return $this->config['environment']!=='production';}
}
