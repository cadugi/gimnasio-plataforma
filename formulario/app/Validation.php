<?php
declare(strict_types=1);
function fieldLabel(string $key):string{static $m=['reason'=>'el motivo','reason_text'=>'el motivo','name'=>'el nombre','surname'=>'los apellidos','birth_date'=>'la fecha de nacimiento','document_type'=>'el tipo de documento','document'=>'el documento','address'=>'la dirección','town'=>'la población','postal_code'=>'el código postal','phone'=>'el teléfono','phone_secondary'=>'el segundo teléfono','email'=>'el correo electrónico','iban'=>'el IBAN','holder'=>'el titular de la cuenta','holder_name'=>'el nombre del titular','holder_surname'=>'los apellidos del titular','username'=>'el usuario','role'=>'el rol','member_number'=>'el número de socio','due_date'=>'la fecha de cobro','period'=>'el periodo','brand'=>'el centro','tariff_id'=>'la tarifa','approval_reference'=>'la referencia de aprobación','bank_reference'=>'la referencia bancaria','policy_reference'=>'la referencia de la política','approved_by'=>'quién aprueba','instructions'=>'las instrucciones','version'=>'la versión','code'=>'el código','date'=>'la fecha','conditions'=>'las condiciones'];return $m[$key]??str_replace('_',' ',$key);}
function textField(array $v,string $key,int $max=120,bool $required=true):string{ensure(!isset($v[$key])||is_string($v[$key]),'Revisa '.fieldLabel($key).'.');$x=trim((string)($v[$key]??''));ensure(!$required||$x!=='','Completa '.fieldLabel($key).'.');ensure(preg_match('//u',$x)===1&&strlen($x)<=$max&&!preg_match('/[\x00-\x08\x0B\x0C\x0E-\x1F]/',$x),'Revisa '.fieldLabel($key).'.');return $x;}
function validatePersonal(array $p):array{
    $out=[];foreach(['name'=>100,'surname'=>160,'birth_date'=>10,'document_type'=>12,'document'=>35,'address'=>240,'town'=>120,'phone'=>24,'email'=>180] as $key=>$max)$out[$key]=textField($p,$key,$max);
    $out['postal_code']=textField($p,'postal_code',16,false);$out['phone_secondary']=textField($p,'phone_secondary',24,false);
    $d=DateTimeImmutable::createFromFormat('!Y-m-d',$out['birth_date']);ensure($d&&$d->format('Y-m-d')===$out['birth_date']&&$out['birth_date']<madridToday()&&$out['birth_date']>='1900-01-01','Fecha de nacimiento no válida.');
    ensure(filter_var($out['email'],FILTER_VALIDATE_EMAIL)!==false,'Correo electrónico no válido.');$out['email']=strtolower($out['email']);
    foreach(['phone','phone_secondary'] as $key){if($out[$key]==='')continue;$n=preg_replace('/[\s().-]/','',$out[$key]);ensure(preg_match('/^\+?[0-9]{7,15}$/',$n)===1,'Teléfono no válido.');$out[$key]=$n;}
    $out['document']=validateDocument($out['document_type'],$out['document']);return $out;
}
function validateDocument(string $kind,string $document):string{
    $doc=strtoupper(preg_replace('/\s/','',$document));ensure(in_array($kind,['DNI','NIE','PASSPORT'],true),'Tipo de documento no válido.');$letters='TRWAGMYFPDXBNJZSQVHLCKE';
    if($kind==='DNI'){ensure(preg_match('/^[0-9]{8}[A-Z]$/',$doc)===1,'DNI no válido.');ensure($letters[((int)substr($doc,0,8))%23]===substr($doc,-1),'La letra del DNI no es correcta.');}
    elseif($kind==='NIE'){ensure(preg_match('/^[XYZ][0-9]{7}[A-Z]$/',$doc)===1,'NIE no válido.');$num=strpos('XYZ',$doc[0]).substr($doc,1,7);ensure($letters[((int)$num)%23]===substr($doc,-1),'La letra del NIE no es correcta.');}
    else ensure(preg_match('/^[A-Z0-9][A-Z0-9-]{3,29}$/',$doc)===1,'Revisa el pasaporte. No se aplica el algoritmo de DNI.');
    return $doc;
}
function validateBirthDate(string $date):string{$d=DateTimeImmutable::createFromFormat('!Y-m-d',$date);ensure($d&&$d->format('Y-m-d')===$date&&$date<madridToday()&&$date>='1900-01-01','Fecha de nacimiento no válida.');return $date;}
function validateIban(string $input):string{
    $iban=strtoupper(preg_replace('/\s+/','',$input));
    $lengths=['AD'=>24,'AL'=>28,'AT'=>20,'BE'=>16,'BG'=>22,'CH'=>21,'CY'=>28,'CZ'=>24,'DE'=>22,'DK'=>18,'EE'=>20,'ES'=>24,'FI'=>18,'FR'=>27,'GB'=>22,'GI'=>23,'GR'=>27,'HR'=>21,'HU'=>28,'IE'=>22,'IS'=>26,'IT'=>27,'LI'=>21,'LT'=>20,'LU'=>20,'LV'=>21,'MC'=>27,'MD'=>24,'ME'=>22,'MK'=>19,'MT'=>31,'NL'=>18,'NO'=>15,'PL'=>28,'PT'=>25,'RO'=>24,'RS'=>22,'SE'=>24,'SI'=>19,'SK'=>24,'SM'=>27,'VA'=>22];
    $country=substr($iban,0,2);ensure(isset($lengths[$country])&&strlen($iban)===$lengths[$country]&&preg_match('/^[A-Z]{2}[0-9]{2}[A-Z0-9]+$/',$iban)===1,'IBAN: revisa el país y su longitud SEPA.');
    if($country==='ES')ensure(preg_match('/^ES[0-9]{22}$/',$iban)===1,'El IBAN español debe contener ES y 22 cifras.');
    $reordered=substr($iban,4).substr($iban,0,4);$mod=0;foreach(str_split($reordered) as $c){$digits=ctype_alpha($c)?(string)(ord($c)-55):$c;foreach(str_split($digits) as $digit)$mod=($mod*10+(int)$digit)%97;}ensure($mod===1,'Los dígitos de control del IBAN no son correctos.');return $iban;
}
function validateBank(array $b,array $person):array{
    $same=($b['holder_same']??false)===true;
    if($same){$name=$person['name'];$surname=$person['surname'];$holder=$name.' '.$surname;}
    elseif(($b['holder_name']??'')!==''||($b['holder_surname']??'')!==''){$name=textField($b,'holder_name',100);$surname=textField($b,'holder_surname',160);$holder=$name.' '.$surname;}
    else{$name='';$surname='';$holder=textField($b,'holder',180);}
    return ['holder_same'=>$same,'holder'=>$holder,'holder_name'=>$name,'holder_surname'=>$surname,'iban'=>validateIban(textField($b,'iban',60))];
}
function validateSignature(mixed $value):array{ensure(is_array($value)&&count($value)>0&&count($value)<=100,'Firma dentro del recuadro.');$points=0;$distance=0;$clean=[];foreach($value as $stroke){ensure(is_array($stroke)&&count($stroke)>=2&&count($stroke)<=3000,'Firma no válida.');$s=[];$prev=null;foreach($stroke as $point){ensure(is_array($point)&&count($point)===2&&is_numeric($point[0])&&is_numeric($point[1]),'Firma no válida.');$x=(float)$point[0];$y=(float)$point[1];ensure(is_finite($x)&&is_finite($y)&&$x>=0&&$x<=1&&$y>=0&&$y<=1,'Firma fuera del recuadro.');if($prev)$distance+=hypot($x-$prev[0],$y-$prev[1]);$prev=[$x,$y];$s[]=$prev;$points++;ensure($points<=10000,'Firma demasiado grande.');}$clean[]=$s;}ensure($distance>=0.03,'La firma está vacía o es demasiado pequeña.');return $clean;}
function centsString(int $v):string{return number_format($v/100,2,',','.').' €';}
