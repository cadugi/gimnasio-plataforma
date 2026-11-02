<?php
declare(strict_types=1);
// Initial import of an Apache password hash, without receiving its plaintext.
// A successful legacy login is upgraded to Argon2id in this app only.
function verifyAccessPassword(string $password,string $hash):bool {
    if(strlen($password)>1024||str_contains($password,"\0")||str_contains($password,"\n")||str_contains($password,"\r"))return false;
    if(!str_starts_with($hash,'$apr1$'))return password_verify($password,$hash);
    if(preg_match('/^\$apr1\$([A-Za-z0-9.\/]{1,8})\$[A-Za-z0-9.\/]{22}$/',$hash,$m)!==1)return false;
    $binary=PHP_OS_FAMILY==='Windows'?'C:/Users/User/Documents/xampp/apache/bin/openssl.exe':'/usr/bin/openssl';
    if(!is_file($binary))return false;
    $pipes=[];
    $process=proc_open([$binary,'passwd','-apr1','-salt',$m[1],'-stdin'],[['pipe','r'],['pipe','w'],['file',PHP_OS_FAMILY==='Windows'?'NUL':'/dev/null','w']],$pipes,null,null,['bypass_shell'=>true,'create_new_console'=>false]);
    if(!is_resource($process))return false;
    fwrite($pipes[0],$password."\n");fclose($pipes[0]);
    $value=trim(stream_get_contents($pipes[1],256));fclose($pipes[1]);$status=proc_close($process);
    return $status===0&&hash_equals($hash,$value);
}
