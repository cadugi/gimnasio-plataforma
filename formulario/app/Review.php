<?php
declare(strict_types=1);
/** Review of the frozen draft, following the fields and order of the supplied paper. */
function contractReview(array $s):string{
    $e=fn(mixed $v)=>htmlspecialchars((string)$v,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');
    $p=$s['personal'];$holder=($s['kind']??'')==='holder';$paper=$s['paper_reference']??[];
    $paragraph=fn($v)=>'<p>'.$e($v).'</p>';
    $section=fn($title,$content)=>'<section><h2>'.$e($title).'</h2>'.$content.'</section>';
    $fields=function(array $values,string $class='review-fields')use($e):string{
        $out='<dl class="'.$class.'">';foreach($values as $label=>$value)$out.='<div><dt>'.$e($label).'</dt><dd>'.$e($value).'</dd></div>';return $out.'</dl>';
    };
    $html='<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión del contrato</title><link rel="stylesheet" href="assets/review.css?v=20261020-logo"><body><header><img src="assets/logo.jpg" alt="Top Fitness"><div><img class="fighters-logo" src="assets/logo-fighters.png" alt="Top Fighters"><h1>'.($holder?'Mandato del titular':'Alta de socio').'</h1>'.$e($s['reference']).'</div></header>';
    if($paper)$html.='<div class="center-contact">'.$e(implode(' · ',array_filter([$paper['phone']??'',$paper['phone_secondary']??'',$paper['email']??'',$paper['website']??'']))).'</div>';
    if($s['is_demo'])$html.='<aside>DEMO SIN VALIDEZ LEGAL · Textos pendientes de aprobación.</aside>';
    if(!$holder){
        $html.=$fields(['N.º socio'=>($s['member_number']??null)?:'Se asigna al firmar','Fecha'=>$s['date_local']]);
        $html.=$section('Datos del titular',$fields([
            'Nombre'=>$p['name'],'Apellidos'=>$p['surname'],
            'Fecha de nacimiento'=>date('d-m-Y',strtotime($p['birth_date'])),'DNI / NIF / Pasaporte'=>$p['document_type'].' '.$p['document'],
            'Dirección'=>$p['address'],'Población'=>trim($p['town'].' '.$p['postal_code']),
            'Teléfono 1'=>$p['phone'],'Teléfono 2'=>$p['phone_secondary']?:'—','E-mail'=>$p['email']
        ]));
        $html.=$section('Tarifas socio',$fields(['Tipo de contrato'=>$s['tariff']['name'],'Cuota mensual'=>centsString($s['monthly_cents']),...(!empty($s['first_month_from'])?['Primer mes (del '.$s['first_month_from'].' al '.$s['first_month_to'].')'=>centsString($s['first_month_cents'])]:[]),'Matrícula'=>centsString($s['enrollment_cents']),'Total a pagar'=>centsString($s['initial_cents'])]).$paragraph('Descuento autorizado: '.$s['discount_percent'].' %.'));
        $html.=$section('Forma de pago',$paragraph(['cash'=>'Efectivo','card'=>'Tarjeta (solo registro del método, sin cobro)','debit'=>'Domiciliación bancaria'][$s['payment_method']]));
    }else $html.=$section('Contrato relacionado',$paragraph('Socio: '.$p['name'].' '.$p['surname']).$paragraph('Referencia: '.$s['related_contract_reference']).$paragraph('SHA-256: '.$s['related_pdf_hash']));
    if($s['bank']){
        $parts=spanishIbanParts($s['bank']['iban']);
        $html.=$section('Titular de la cuenta',$fields(['Titular'=>$s['bank']['holder'],'Relación con el socio'=>$s['bank']['holder_same']?'El mismo titular del contrato':'Otro titular','IBAN completo'=>trim(chunk_split($s['bank']['iban'],4,' '))]).($parts?$fields($parts,'review-parts'):''));
        $html.=$paragraph($s['legal']['bank_text']);
        if(!$holder&&!$s['bank']['holder_same'])$html.='<aside>La firma del socio no sustituye a la del titular de la cuenta. El mandato queda pendiente de la autorización de esa persona.</aside>';
        $html.=$section('Mandato SEPA',$paragraph($s['legal']['sepa_text']).$paragraph('Referencia: '.$s['mandate_reference']).$paragraph('Acreedor: '.($s['creditor']['name']?:'PENDIENTE · SOLO DEMO')).$paragraph('Identificador: '.($s['creditor']['id']?:'PENDIENTE')));
    }
    if(!$holder){
        $html.=$section('Condiciones · '.$s['legal']['version'],$paragraph($s['legal']['contract_text']).$paragraph($s['tariff']['conditions']));
        $html.=$section('Protección de datos',$paragraph($s['legal']['privacy_text']));
        $html.=$paragraph('Información comercial de Top Fitness: '.($s['consents']['marketing']?'autorizada expresamente':'no autorizada'));
    }
    $html.='<section class="signature-columns"><div><h2>'.($holder?'Por el titular de la cuenta':'Por el titular del contrato').'</h2><p>La firma se incorpora al PDF cuando confirmes.</p></div><div><h2>Por el Centro</h2><p>La aceptación se registra de forma auditada por un trabajador autorizado, vinculada al hash de este PDF.</p></div></section>';
    $html.=$paragraph('Firma dibujada en pantalla; no se declara firma electrónica cualificada.');
    return $html.'<footer>Versión revisada: '.$e(hash('sha256',jencode($s))).'</footer></body></html>';
}
