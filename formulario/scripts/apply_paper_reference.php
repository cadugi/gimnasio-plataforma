<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/app/Service.php';
ensure(PHP_SAPI==='cli','Solo consola.');$root=dirname(__DIR__);$s=new Service($root,readConfig($root));
ensure($s->demo(),'No se cambian textos de producción mediante este script.',403);
$_SESSION=['user_id'=>'local-reference-update'];
foreach(['fitness','fighters'] as $brand){
    $current=$s->one('SELECT * FROM legal_versions WHERE brand=? AND active=1',[$brand]);
    if($current&&(int)$current['approved']===1)continue;
    $legal=paperLegalDefaults($root,$brand);
    if($s->one('SELECT id FROM legal_versions WHERE brand=? AND version=?',[$brand,$legal['version']]))continue;
    $s->saveLegal($legal);
}
echo "Referencia del impreso preparada en la demo, pendiente de revisión. Los contratos firmados conservan su versión y PDF.\n";
