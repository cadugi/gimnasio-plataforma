<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/app/Service.php';
ensure(PHP_SAPI==='cli','Solo consola.');
$root=dirname(__DIR__);$s=new Service($root,readConfig($root));
$authorized=in_array('--authorize-supplied-terms',$argv,true);
$_SESSION=['user_id'=>'supplied-paper-import'];
$pending=[];
foreach(['fitness','fighters'] as $brand){
    $legal=paperLegalDefaults($root,$brand);
    if($authorized){
        ensure($legal['version']==='IMPRESO-20261016-COTEJADO'&&!str_contains($legal['contract_text'],'[fragmento pendiente'),'La transcripción no está cotejada.');
        $legal['approved']=true;
        $legal['approval_reference']='Uso del impreso y privacidad autorizado expresamente por el responsable el 16/10/2026. Sección cuarta cotejada con su foto ampliada. Aprobación operativa del centro, no certificación jurídica. Se conservan los requisitos SEPA.';
    }
    $current=$s->one('SELECT id,approved,version FROM legal_versions WHERE brand=? AND active=1',[$brand]);
    if($s->one('SELECT id FROM legal_versions WHERE brand=? AND version=?',[$brand,$legal['version']]))continue;
    ensure(!$current||(int)$current['approved']===0,'No se sustituye una versión aprobada.',409);
    $pending[]=$legal;
}
if($pending){
    $s->createBackup();
    foreach($pending as $legal)$s->saveLegal($legal);
}
echo json_encode(['created'=>count($pending),'authorized_import'=>$authorized,'signed_contracts_modified'=>false],JSON_THROW_ON_ERROR)."\n";
