<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/app/Service.php';
ensure(PHP_SAPI==='cli'&&function_exists('posix_geteuid')&&posix_geteuid()===0,'Solo preparación del administrador.',403);
$s=new Service(dirname(__DIR__),readConfig(dirname(__DIR__)));
if(is_file(dirname($s->config['database']).'/bootstrap.done')){echo "Acceso inicial ya preparado.\n";exit;}
$s->transaction(function()use($s){
    $created=0;
    foreach(file('/etc/nginx/topfitness-admin.htpasswd',FILE_IGNORE_NEW_LINES|FILE_SKIP_EMPTY_LINES) as $line){
        if(trim($line)===''||str_starts_with(trim($line),'#'))continue;
        [$name,$hash]=explode(':',$line,2);
        ensure(preg_match('/^\$(2[aby]|apr1)\$/',$hash)===1,'El formato de acceso existente no es compatible.');
        if($s->one('SELECT id FROM users WHERE username=?',[$name])){
            $s->sql('UPDATE users SET password_hash=?,epoch=epoch+1,active=1 WHERE username=?',[$hash,$name]);continue;
        }
        $id=uuid();
        $s->sql("INSERT INTO users(id,username,password_hash,role,active,epoch,created_at) VALUES(?,?,?,'admin',1,1,?)",[$id,$name,$hash,instant()]);
        $s->audit('vps-provisioning','ADMIN_ACCESS_INITIALIZED',$id,['source'=>'existing_password_hash']);$created++;
    }
    ensure($s->one("SELECT id FROM users WHERE username<>'demo.admin' AND active=1"),'Falta un administrador autorizado.');
    $s->sql("UPDATE users SET active=0,epoch=epoch+1 WHERE username='demo.admin'");
});
echo "Acceso inicial preparado sin mostrar credenciales.\n";
