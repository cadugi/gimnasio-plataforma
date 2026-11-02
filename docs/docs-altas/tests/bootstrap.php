<?php
declare(strict_types=1);
// Arnés común: SOLO contra la copia /var/tmp/tf-bajas-test.
$root='/var/tmp/tf-bajas-test';
require_once $root.'/app/Service.php';
$s=new Service($root,readConfig($root));
if(!str_starts_with($s->config['database'],$root.'/')){fwrite(STDERR,"¡No es la copia!\n");exit(2);}
$GLOBALS['fails']=0;$GLOBALS['passes']=0;
function eq($got,$want,string $msg):void{if($got===$want){$GLOBALS['passes']++;return;}$GLOBALS['fails']++;echo "FAIL $msg: got ".var_export($got,true)." want ".var_export($want,true)."\n";}
function ok($cond,string $msg):void{eq((bool)$cond,true,$msg);}
function throws(callable $f,string $needle,string $msg):void{try{$f();}catch(Throwable $e){ok(str_contains($e->getMessage(),$needle),$msg.' (mensaje: '.$e->getMessage().')');return;}$GLOBALS['fails']++;echo "FAIL $msg: no lanzó excepción\n";}
function done():void{echo ($GLOBALS['fails']?'RESULT: FAIL':'RESULT: PASS')." ({$GLOBALS['passes']} ok, {$GLOBALS['fails']} fallos)\n";exit($GLOBALS['fails']?1:0);}
function kiosk():void{if(session_status()!==PHP_SESSION_ACTIVE){@session_id('tfbajastest'.bin2hex(random_bytes(4)));}$_SESSION=['mode'=>'kiosk','kiosk_locked'=>true,'device_actor'=>'prueba','csrf'=>'x'];}
function staff(Service $s,string $role='admin'):void{$u=$s->one('SELECT id,epoch FROM users WHERE role=? AND active=1 LIMIT 1',[$role]);
  if(!$u){$id=bin2hex(random_bytes(16));$s->sql("INSERT INTO users(id,username,password_hash,role,active,epoch,created_at) VALUES(?,?,'x',?,1,1,?)",[$id,'prueba-'.$role,$role,instant()]);$u=['id'=>$id,'epoch'=>1];}
  $_SESSION=['mode'=>'admin','user_id'=>$u['id'],'epoch'=>(int)$u['epoch'],'csrf'=>'x'];}
// Borrador de alta con datos ficticios, listo para prepareContract().
function altaDraft(Service $s,array $over=[]):string{
    kiosk();$t=$s->one("SELECT * FROM tariffs WHERE active=1 AND brand='fitness' ORDER BY monthly_cents DESC LIMIT 1");
    $l=$s->one("SELECT id FROM legal_versions WHERE brand='fitness' AND active=1 ORDER BY created_at DESC LIMIT 1");
    $n=random_int(10000000,99999999);
    $data=array_replace_recursive(['personal'=>['name'=>'Prueba','surname'=>'Prorrateo','birth_date'=>'1990-01-01','document_type'=>'DNI','document'=>$n.'TRWAGMYFPDXBNJZSQVHLCKE'[$n%23],'address'=>'C/ Prueba 1','town'=>'Ciudad','phone'=>'600000000','email'=>'prueba@example.com','postal_code'=>'28001','phone_secondary'=>''],
      'brand'=>'fitness','tariff_id'=>$t['id'],'payment_method'=>'cash','bank'=>['holder_same'=>true],'consents'=>['legal_id'=>$l['id'],'contract'=>true,'privacy'=>true,'marketing'=>false]],$over);
    $id=bin2hex(random_bytes(16));
    (function()use($id,$data){$cols=array_column($this->sql('PRAGMA table_info(drafts)'),'name');
      $row=array_intersect_key(['id'=>$id,'session_hash'=>$this->sessionHash(),'data_enc'=>$this->seal($data),'expires_at'=>gmdate('Y-m-d\TH:i:s\Z',time()+3600),'updated_at'=>instant(),'created_at'=>instant()],array_flip($cols));
      $this->sql('INSERT INTO drafts('.implode(',',array_keys($row)).') VALUES('.implode(',',array_fill(0,count($row),'?')).')',array_values($row));})->call($s);
    $_SESSION['draft_id']=$id;return $id;
}
const SIG=[[[0.1,0.5],[0.3,0.3],[0.5,0.6],[0.9,0.4]]];
function priv(Service $s,callable $f){return Closure::bind($f,$s,Service::class)();}
