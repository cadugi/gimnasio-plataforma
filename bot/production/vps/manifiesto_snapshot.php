<?php
declare(strict_types=1);
ini_set('display_errors','0');
try {
    $mode=getenv('SNAPSHOT_MODE')?:'real';
    if(getenv('SNAPSHOT_CONFIG')){
        $p=json_decode(file_get_contents(getenv('SNAPSHOT_CONFIG')),true);
        if($mode==='demo')$p=['host'=>'127.0.0.1','port'=>13322,'user'=>'root','password'=>$p['DEMO_ROOT_PASSWORD'],'database'=>'demo_reservas'];
    }else{
        $prefix=$mode==='demo'?'DEMO_':'TF_REAL_';
        $p=['host'=>getenv($prefix.'DB_HOST'),'port'=>3306,'user'=>getenv($prefix.'DB_USER'),'password'=>getenv($prefix.'DB_PASSWORD'),'database'=>getenv($prefix.'DB_NAME')];
    }
    mysqli_report(MYSQLI_REPORT_ERROR|MYSQLI_REPORT_STRICT);
    $c=new mysqli($p['host'],$p['user'],$p['password'],$p['database'],(int)$p['port']);
    $c->set_charset('utf8mb4');$c->query("SET time_zone='+00:00'");
    $c->query('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ');$c->query('START TRANSACTION WITH CONSISTENT SNAPSHOT');
    $out=[];
    foreach($c->query('SHOW FULL TABLES')->fetch_all(MYSQLI_NUM) as $table){
        if($table[1]!=='BASE TABLE')continue;
        $name='`'.str_replace('`','``',$table[0]).'`';
        $keys=$c->query('SHOW KEYS FROM '.$name." WHERE Key_name='PRIMARY'")->fetch_all(MYSQLI_ASSOC);
        usort($keys,fn($a,$b)=>$a['Seq_in_index']<=>$b['Seq_in_index']);
        $order=implode(',',array_map(fn($k)=>'`'.$k['Column_name'].'`',$keys));
        $r=$c->query('SELECT * FROM '.$name.($order?' ORDER BY '.$order:''));
        $hash=hash_init('sha256');$n=0;
        while($row=$r->fetch_row()){$n++;hash_update($hash,json_encode(array_map(fn($v)=>$v===null?null:(string)$v,$row),JSON_UNESCAPED_UNICODE)."\n");}
        $out[$table[0]]=['rows'=>$n,'sha256'=>hash_final($hash)];
    }
    $c->commit();ksort($out);echo json_encode($out);
}catch(Throwable $e){fwrite(STDERR,'No se pudo verificar la copia. Codigo: '.(int)$e->getCode());exit(1);}
