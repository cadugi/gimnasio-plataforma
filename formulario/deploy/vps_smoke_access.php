<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/app/Service.php';
ensure(PHP_SAPI==='cli','Solo CLI.',403);
$s=new Service(dirname(__DIR__),readConfig(dirname(__DIR__)));
$r=json_decode(stream_get_contents(STDIN),true,8,JSON_THROW_ON_ERROR);
ensure(preg_match('/^[a-f0-9]{32}$/',$r['id']??'')===1,'Referencia de prueba inválida.');
if($r['operation']==='create'){
    ensure(str_starts_with($r['username'],'qa_deploy_'),'Solo usuario temporal.');
    $s->transaction(function()use($s,$r){$s->sql("INSERT INTO users(id,username,password_hash,role,active,epoch,created_at) VALUES(?,?,?,'staff',1,1,?)",[$r['id'],$r['username'],$r['hash'],instant()]);$s->audit('deployment-test','TEMPORARY_TEST_ACCESS',$r['id']);});
    echo "{}";
}elseif($r['operation']==='status'){
    $u=$s->one('SELECT password_hash FROM users WHERE id=?',[$r['id']]);
    echo jencode(['rehash_argon2id'=>$u&&str_starts_with($u['password_hash'],'$argon2id$'),'contracts'=>(int)$s->one('SELECT COUNT(*) n FROM contracts')['n'],'drafts'=>(int)$s->one('SELECT COUNT(*) n FROM drafts')['n']]);
}elseif($r['operation']==='delete'){
    if($s->one("SELECT id FROM users WHERE id=? AND username LIKE 'qa_deploy_%'",[$r['id']]))$s->transaction(function()use($s,$r){
        if($s->one("SELECT name FROM sqlite_master WHERE type='table' AND name='tablet_invitations'"))$s->sql('DELETE FROM tablet_invitations WHERE issuer_id=?',[$r['id']]);
        $s->sql("DELETE FROM users WHERE id=? AND username LIKE 'qa_deploy_%'",[$r['id']]);
    });echo "{}";
}
