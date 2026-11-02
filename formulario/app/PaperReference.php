<?php
declare(strict_types=1);
function paperReference(string $root):array {
    return json_decode(file_get_contents($root.'/fixtures/paper_reference.json'),true,16,JSON_THROW_ON_ERROR);
}
function paperLegalDefaults(string $root,string $brand):array {
    $p=paperReference($root);
    return [
        'brand'=>$brand,'version'=>'IMPRESO-20261016-COTEJADO',
        'contract_text'=>trim(file_get_contents($root.'/fixtures/condiciones_generales_20261016.txt')),
        'privacy_text'=>trim(file_get_contents($root.'/fixtures/privacidad_impreso_20261016.txt')),
        'bank_text'=>$p['source_note']."\n\n".$p['bank_authorization_source'],
        'sepa_text'=>'PENDIENTE: revisión del mandato SEPA, acreedor, referencia y procedimiento de autorización. La cláusula del impreso no se declara por sí sola un mandato SEPA validado.',
        'approved'=>false,'approval_reference'=>'Uso de la cláusula de privacidad del impreso autorizado expresamente por el responsable en esta conversación el 16/10/2026. No implica revisión jurídica. Sección cuarta cotejada con la fotografía ampliada aportada por el responsable.'
    ];
}
function spanishIbanParts(string $iban):?array {
    if(!preg_match('/^ES[0-9]{22}$/',$iban))return null;
    return ['IBAN'=>substr($iban,0,4),'Entidad'=>substr($iban,4,4),'Sucursal'=>substr($iban,8,4),'DC'=>substr($iban,12,2),'N.º cuenta'=>substr($iban,14,10)];
}
