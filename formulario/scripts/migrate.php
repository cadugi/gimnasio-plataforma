<?php
declare(strict_types=1);
/* Aplica SOLO las migraciones pendientes (aditivas) a la base configurada. A diferencia de setup.php no crea usuarios,
   tarifas ni textos. Pensado para los despliegues: TF_CONFIG_FILE=... TF_KEY_FILE=... php migrate.php */
require_once dirname(__DIR__).'/app/Service.php';
ensure(PHP_SAPI==='cli','Solo consola.',403);
$root=dirname(__DIR__);$config=readConfig($root);$s=new Service($root,$config);
$id=(int)$s->one('PRAGMA application_id')['application_id'];
ensure($id===1413894963,'Esta base de datos no pertenece al módulo de contratos. No se ha migrado.',409);
ensure((bool)$s->one("SELECT name FROM sqlite_master WHERE type='table' AND name='migrations'"),'Falta la tabla de migraciones.',409);
$done=0;
foreach(glob($root.'/migrations/*.sql') as $migration){
    $name=basename($migration);if($s->one('SELECT version FROM migrations WHERE version=?',[$name]))continue;
    $s->transaction(function()use($s,$migration,$name){$sql=file_get_contents($migration);
        ensure(!preg_match('/\b(DROP|TRUNCATE|DELETE)\b/i',$sql),'Migración destructiva rechazada.');
        $s->db->exec($sql);$s->sql('INSERT INTO migrations VALUES(?,?)',[$name,instant()]);});
    echo "aplicada $name\n";$done++;
}
echo $done?"Migraciones aplicadas: $done\n":"Sin migraciones pendientes.\n";
