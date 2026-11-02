<?php
// Solo CLI en el VPS. La contraseña entra por stdin, nunca por argumentos ni logs.
declare(strict_types=1);
if(PHP_SAPI!=='cli')exit(1);
$root=realpath('/opt/topfitness-formulario/current');
require_once $root.'/app/Service.php';
$s=new Service($root,readConfig($root));
$r=json_decode(stream_get_contents(STDIN),true,16,JSON_THROW_ON_ERROR);
$u=$s->one("SELECT * FROM users WHERE username='qa_total'");
if($r['action']==='create'){
    ensure(!$u,'qa_total ya existe; no se sobrescribe.');
    $_SESSION=['user_id'=>'qa_total_provision'];
    $s->saveUser(['username'=>'qa_total','role'=>'admin','active'=>true,'password'=>$r['password']]);
    echo json_encode(['hash'=>password_hash($r['password'],PASSWORD_ARGON2ID)]);
}elseif(in_array($r['action'],['disable','purge'],true)){
    if($u)$s->transaction(function()use($s,$u,$r){
        $s->sql('UPDATE users SET active=0,epoch=epoch+1 WHERE id=?',[$u['id']]);
        // Invitaciones y sesiones emitidas por QA se revocan; nunca se tocan socios.
        $s->sql('DELETE FROM tablet_invitations WHERE issuer_id=?',[$u['id']]);
        if($r['action']==='purge')$s->sql('DELETE FROM users WHERE id=?',[$u['id']]);
        $s->audit('qa_total','QA_'.strtoupper($r['action']),'qa_total');
    });
    echo '{}';
}else{exit(1);}
