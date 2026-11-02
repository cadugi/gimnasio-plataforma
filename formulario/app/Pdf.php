<?php
declare(strict_types=1);
/** Small server-side PDF renderer: embedded system TrueType, Unicode and vector ink. */
final class ContractPdf {
    private string $subtitle='TOP FITNESS / ALTAS DE SOCIOS';private array $paper=[];private array $pages=[];private string $page='';private int $y=110;private array $used=[];private array $map=[];private array $tables=[];private string $font;
    private function u16(int $p):int{return unpack('n',substr($this->font,$p,2))[1];}
    private function u32(int $p):int{return unpack('N',substr($this->font,$p,4))[1];}
    public function __construct(private string $root,array $config){$file=$config['pdf_font']??'';ensure(is_file($file),'Configura una fuente TrueType Unicode para generar PDF.',503);$this->font=file_get_contents($file);$n=$this->u16(4);for($i=0;$i<$n;$i++){$p=12+$i*16;$this->tables[substr($this->font,$p,4)]=$this->u32($p+8);}ensure(isset($this->tables['cmap'],$this->tables['head'],$this->tables['hhea'],$this->tables['hmtx']),'Fuente PDF no compatible.',503);
        $base=$this->tables['cmap'];$count=$this->u16($base+2);$chosen=null;for($i=0;$i<$count;$i++){$p=$base+4+$i*8;$offset=$base+$this->u32($p+4);if($this->u16($offset)===4&&($this->u16($p)===0||$this->u16($p)===3))$chosen=$offset;}
        ensure($chosen!==null,'La fuente requiere mapa Unicode BMP.',503);$seg=intdiv($this->u16($chosen+6),2);$ends=$chosen+14;$starts=$ends+2*$seg+2;$deltas=$starts+2*$seg;$ranges=$deltas+2*$seg;
        for($i=0;$i<$seg;$i++){$start=$this->u16($starts+2*$i);$end=$this->u16($ends+2*$i);$delta=$this->u16($deltas+2*$i);$range=$this->u16($ranges+2*$i);for($c=$start;$c<=$end&&$c<65535;$c++){$g=$range?$this->u16($ranges+2*$i+$range+2*($c-$start)):$c;if($g)$g=($g+$delta)&65535;if($g)$this->map[$c]=$g;}}
        if(isset($this->tables['OS/2']))ensure(($this->u16($this->tables['OS/2']+8)&2)===0,'La fuente no permite incrustación documental.',503);
    }
    private function text(string $s,int $x,int $y,int $size=10):string{$bytes=iconv('UTF-8','UTF-16BE',$s);ensure($bytes!==false,'Texto PDF no válido.');foreach(unpack('n*',$bytes) as $c){ensure(isset($this->map[$c])||$c===32,'La fuente no representa algún carácter. Requiere revisión documental.');$this->used[$c]=true;}return "BT /F1 $size Tf 0.08 0.09 0.09 rg 1 0 0 1 $x ".(842-$y)." Tm <".strtoupper(bin2hex($bytes))."> Tj ET\n";}
    private function coloredText(string $value,int $x,int $y,int $size,string $rgb):string{
        return str_replace('0.08 0.09 0.09 rg',$rgb.' rg',$this->text($value,$x,$y,$size));
    }
    private function newPage():void{
        if($this->page!=='')$this->pages[]=$this->page;
        $this->page="q 0.06 0.075 0.065 rg 32 738 531 78 re f Q\nq 60 0 0 60 42 747 cm /Logo Do Q\n";
        $this->page.="q 109 0 0 18 122 780 cm /LogoF Do Q\n";
        $this->page.=$this->coloredText($this->subtitle,122,79,9,'0.90 0.94 0.90');
        $contacts=[$this->paper['phone']??'',$this->paper['phone_secondary']??'',$this->paper['email']??'',$this->paper['website']??''];
        foreach($contacts as $i=>$value)if($value!=='')$this->page.=$this->coloredText($value,422,47+$i*13,8,'0.95 0.96 0.94');
        $this->y=120;
    }
    private function width(string $value,int $size):float{$units=$this->u16($this->tables['head']+18);$metrics=$this->u16($this->tables['hhea']+34);$total=0;foreach(unpack('n*',iconv('UTF-8','UTF-16BE',$value))?:[] as $code){$glyph=$this->map[$code]??0;$total+=$this->u16($this->tables['hmtx']+4*min($glyph,$metrics-1))*$size/$units;}return $total;}
    private function wrapped(string $value,int $size,int $maxWidth=510):array{$out=[];$buffer='';foreach(preg_split('/(\s+)/u',$value,-1,PREG_SPLIT_DELIM_CAPTURE)?:[] as $word){if($this->width($buffer.$word,$size)<=$maxWidth){$buffer.=$word;continue;}if(trim($buffer)!==''){$out[]=rtrim($buffer);$buffer='';}$word=ltrim($word);if($this->width($word,$size)<=$maxWidth){$buffer=$word;continue;}foreach(preg_split('//u',$word,-1,PREG_SPLIT_NO_EMPTY)?:[] as $char){if($this->width($buffer.$char,$size)>$maxWidth){$out[]=$buffer;$buffer='';}$buffer.=$char;}}if($buffer!==''||!$out)$out[]=rtrim($buffer);return $out;}
    private function line(string $s,bool $title=false):void{if($title){if($this->y>685)$this->newPage();else $this->y+=7;}$size=$title?12:10;foreach(explode("\n",str_replace("\r",'',$s)) as $line)foreach($this->wrapped($line,$size) as $chunk){if($this->y>746)$this->newPage();$this->page.=$this->text($chunk,42,$this->y,$size);$this->y+=$title?21:15;}}
    private function paperSection(string $title):void{
        if($this->y>700)$this->newPage();
        $this->y+=7;$this->page.=$this->text($title,42,$this->y,10);$this->y+=18;
    }
    private function fieldRow(array $fields):void{
        $width=intdiv(510-(count($fields)-1)*12,count($fields));$lines=[];$max=1;
        foreach($fields as $label=>$value){$rows=$this->wrapped((string)$value,9,$width-12);$lines[]=[$label,$rows];$max=max($max,count($rows));}
        $height=18+$max*12;if($this->y+$height>740)$this->newPage();
        foreach($lines as $i=>[$label,$rows]){
            $x=42+$i*($width+12);$this->page.=$this->text((string)$label,$x,$this->y,8);
            $rectY=842-$this->y-7-$max*12;
            $this->page.="q 0.955 0.96 0.95 rg $x $rectY $width ".($max*12+5)." re f Q\n";
            foreach($rows as $j=>$value)$this->page.=$this->text($value,$x+5,$this->y+15+$j*12,9);
        }
        $this->y+=$height;
    }
    private function compactText(string $value,int $size=9):void{
        foreach(explode("\n",str_replace("\r",'',$value)) as $line)foreach($this->wrapped($line,$size) as $row){
            if($this->y>740)$this->newPage();$this->page.=$this->text($row,42,$this->y,$size);$this->y+=12;
        }
    }
    private function signatures(array $signature,bool $holder=false,string $label=''):void{
        if($this->y>636)$this->newPage();$this->y+=8;
        $this->page.=$this->text($label?:($holder?'Por el titular de la cuenta':'Por el titular del contrato'),42,$this->y,10);
        $this->page.=$this->text('Por el Centro',312,$this->y,10);$this->y+=10;
        $bottom=842-$this->y-60;
        $this->page.="q 0.45 0.49 0.44 RG 0.6 w 42 $bottom 240 60 re S 312 $bottom 240 60 re S Q\n";
        foreach($signature as $stroke){$first=true;$this->page.="0.10 0.15 0.10 RG 1.1 w\n";foreach($stroke as [$x,$y]){$this->page.=sprintf('%.3F %.3F %s ',47+$x*230,842-$this->y-5-$y*50,$first?'m':'l');$first=false;}$this->page.="S\n";}
        $this->page.=$this->text('Pendiente de aceptación del centro',320,$this->y+25,8);
        $this->y+=78;$this->compactText('La aceptación del centro se registra de forma auditada, vinculada a este PDF.',8);
    }
    private function renderPaper(array $s,array $signature,bool $preview):void{
        $p=$s['personal'];$legal=$s['legal'];$this->newPage();
        $this->compactText(($preview?'VISTA PREVIA - ':($s['is_demo']?'DEMO SIN VALIDEZ LEGAL - ':'')).$s['reference'],9);
        $this->fieldRow(['N.º SOCIO'=>($s['member_number']??null)?:'Se asigna al firmar','FECHA'=>$s['date_local']]);
        $this->paperSection('DATOS DEL TITULAR');
        $this->fieldRow(['Nombre'=>$p['name'],'Apellidos'=>$p['surname']]);
        $this->fieldRow(['Fecha de nacimiento'=>date('d-m-Y',strtotime($p['birth_date'])),'DNI / NIF / Pasaporte'=>$p['document_type'].' '.$p['document']]);
        $this->fieldRow(['Dirección'=>$p['address'],'Población'=>trim($p['town'].' '.$p['postal_code'])]);
        $this->fieldRow(['Teléfono 1'=>$p['phone'],'Teléfono 2'=>$p['phone_secondary']?:'—','E-mail'=>$p['email']]);
        $this->compactText('Información comercial de Top Fitness: '.($s['consents']['marketing']?'autorizada expresamente':'no autorizada'),8);
        $this->paperSection('TARIFAS SOCIO');
        $this->fieldRow(['Tipo de contrato'=>$s['tariff']['name'],'Cuota mensual'=>centsString($s['monthly_cents'])]);
        if(!empty($s['first_month_from']))$this->fieldRow(['Primer mes (del '.$s['first_month_from'].' al '.$s['first_month_to'].')'=>centsString($s['first_month_cents']),'Matrícula'=>centsString($s['enrollment_cents'])]);else $this->fieldRow(['Matrícula'=>centsString($s['enrollment_cents'])]);
        $this->fieldRow(['TOTAL A PAGAR'=>centsString($s['initial_cents'])]);
        if($s['discount_percent'])$this->compactText('Descuento autorizado aplicado a la cuota: '.$s['discount_percent'].' %.',8);
        $this->paperSection('FORMA DE PAGO');
        $this->compactText(['cash'=>'Efectivo','card'=>'Tarjeta (solo registro del método, sin cobro)','debit'=>'Domiciliación bancaria'][$s['payment_method']]);
        if($s['bank']){
            $this->fieldRow(['TITULAR - '.($s['bank']['holder_same']?'El mismo':'Otro titular')=>$s['bank']['holder']]);
            $this->fieldRow(['IBAN completo'=>trim(chunk_split($s['bank']['iban'],4,' '))]);
            $parts=spanishIbanParts($s['bank']['iban']);if($parts)$this->fieldRow($parts);
            $this->compactText($legal['bank_text'],8);
            if(!$s['bank']['holder_same'])$this->compactText('La firma del socio no sustituye a la del titular de la cuenta: mandato pendiente.',8);
        }
        $this->signatures($signature);
        $this->compactText('Condiciones, privacidad y autorización aplicables: anexo de este mismo documento.',8);
        $this->newPage();$this->line('ANEXO AL CONTRATO '.$s['reference'],true);
        $this->line('Versión de condiciones: '.$legal['version']);
        $this->line('CONDICIONES DE CONTRATACIÓN',true);$this->line($legal['contract_text']);
        $this->line('CONDICIONES DE LA TARIFA',true);$this->line($s['tariff']['conditions']);
        $this->line('PROTECCIÓN DE DATOS',true);$this->line($legal['privacy_text']);
        if($s['bank']){
            $this->line('MANDATO SEPA',true);$this->line($legal['sepa_text']);
            $this->line('Referencia de mandato: '.$s['mandate_reference']);
            $this->line('Acreedor: '.($s['creditor']['name']?:'PENDIENTE - SOLO DEMO'));
            $this->line('Identificador acreedor: '.($s['creditor']['id']?:'PENDIENTE'));
        }
        $this->line('EVIDENCIAS Y ACEPTACIÓN DEL CENTRO',true);
        $this->line('Confirmación expresa y firma vinculadas a esta referencia. Firma dibujada: no se declara firma electrónica cualificada.');
        $this->line('La aceptación posterior del centro se registra con usuario, fecha y hash del PDF. No modifica el documento firmado.');
    }
    // Solicitud de baja definitiva o mantenimiento firmada por el socio.
    private function renderWithdrawal(array $s,array $signature,bool $preview):void{
        $p=$s['personal'];$maintenance=$s['type']==='MAINTENANCE';$this->subtitle='TOP FITNESS / BAJAS Y MANTENIMIENTOS';$this->newPage();
        $this->compactText(($preview?'VISTA PREVIA - ':($s['is_demo']?'DEMO SIN VALIDEZ LEGAL - ':'')).$s['reference'],9);
        $this->line($maintenance?'SOLICITUD DE MANTENIMIENTO (BAJA TEMPORAL)':'SOLICITUD DE BAJA DEFINITIVA',true);
        $this->fieldRow(['N.º SOCIO'=>($s['member_number']??null)?:'No indicado','FECHA DE SOLICITUD'=>$s['date_local']]);
        $this->paperSection('DATOS DEL SOCIO');
        $this->fieldRow(['Nombre'=>$p['name'],'Apellidos'=>$p['surname']]);
        $this->fieldRow(['Fecha de nacimiento'=>date('d-m-Y',strtotime($p['birth_date'])),'DNI / NIF / Pasaporte'=>$p['document_type'].' '.$p['document']]);
        $this->fieldRow(['Teléfono'=>$p['phone']?:'—','E-mail'=>$p['email']?:'—']);
        $this->paperSection('FECHAS');
        $this->fieldRow(['Puede entrenar hasta'=>date('d-m-Y',strtotime($s['last_day'])),($maintenance?'Inicio del mantenimiento':'Baja efectiva desde')=>date('d-m-Y',strtotime($s['effective_date']))]);
        if($maintenance)$this->fieldRow(['Recargo de mantenimiento'=>centsString($s['fee_cents_per_month']).' por mes completo, acumulado y abonado a la vuelta','Matrícula a la vuelta'=>'No se vuelve a pagar']);
        if(!empty($s['reason_label']))$this->fieldRow(['Motivo indicado'=>$s['reason_label'].(!empty($s['reason_text'])?' - '.$s['reason_text']:'')]);
        $this->paperSection('CONDICIONES');$this->compactText($s['legal']['text'],8);
        $this->compactText('Versión de condiciones: '.$s['legal']['version'],7);
        $this->signatures($signature,false,'Por el socio');
        $this->compactText('Firma dibujada en pantalla. No se declara firma electrónica cualificada.',8);
    }
    public function build(array $s,array $signature=[],bool $preview=false):string{
        $this->pages=[];$this->page='';$this->used=[];$this->paper=$s['paper_reference']??[];
        if(($s['kind']??'')==='withdrawal')$this->renderWithdrawal($s,$signature,$preview);
        elseif(($s['kind']??'')!=='holder')$this->renderPaper($s,$signature,$preview);
        else{
            $this->newPage();$this->line(($preview?'VISTA PREVIA - ':($s['is_demo']?'DEMO SIN VALIDEZ LEGAL - ':'')).$s['reference'],true);
            $this->line('MANDATO SEPA - FIRMA DEL TITULAR',true);$this->line('Fecha: '.$s['date_local']);
            $this->line('Socio: '.$s['personal']['name'].' '.$s['personal']['surname']);
            $this->line('Contrato relacionado: '.$s['related_contract_reference']);
            $this->line('SHA-256 del contrato: '.$s['related_pdf_hash']);
            $this->line('Titular: '.$s['bank']['holder']);
            $this->line('IBAN: '.trim(chunk_split($s['bank']['iban'],4,' ')));
            $this->line($s['legal']['bank_text']);$this->line($s['legal']['sepa_text']);
            $this->line('Referencia mandato: '.$s['mandate_reference']);
            $this->line('Acreedor: '.($s['creditor']['name']?:'PENDIENTE - SOLO DEMO'));
            $this->line('Identificador acreedor: '.($s['creditor']['id']?:'PENDIENTE'));
            $this->signatures($signature,true);
            $this->line('Firma dibujada: no se declara firma electrónica cualificada.');
        }
        $this->pages[]=$this->page;$logo=$this->root.'/public/assets/logo.jpg';$jpeg=file_get_contents($logo);$info=getimagesize($logo);
        $objects=[1=>'<< /Type /Catalog /Pages 2 0 R >>',2=>'',3=>'<< /Type /Font /Subtype /Type0 /BaseFont /TFUnicode /Encoding /Identity-H /DescendantFonts [4 0 R] /ToUnicode 8 0 R >>'];
        $units=$this->u16($this->tables['head']+18);$metrics=$this->u16($this->tables['hhea']+34);$widths='';$cid=str_repeat("\0",131072);foreach($this->map as $c=>$g){$cid[$c*2]=chr($g>>8);$cid[$c*2+1]=chr($g&255);}foreach(array_keys($this->used) as $c){$g=$this->map[$c]??0;$w=$this->u16($this->tables['hmtx']+4*min($g,$metrics-1));$widths.=$c.' ['.round($w*1000/$units).'] ';}
        $objects[4]='<< /Type /Font /Subtype /CIDFontType2 /BaseFont /TFUnicode /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor 5 0 R /CIDToGIDMap 7 0 R /DW 600 /W ['.$widths.'] >>';$objects[5]='<< /Type /FontDescriptor /FontName /TFUnicode /Flags 32 /FontBBox [-1000 -500 2000 1500] /ItalicAngle 0 /Ascent 1000 /Descent -300 /CapHeight 700 /StemV 80 /FontFile2 6 0 R >>';
        $stream=function(string $data,string $extra=''){$compressed=gzcompress($data);return '<< /Length '.strlen($compressed).' /Filter /FlateDecode '.$extra." >>\nstream\n".$compressed."\nendstream";};$objects[6]=$stream($this->font,'/Length1 '.strlen($this->font));$objects[7]=$stream($cid);$objects[8]=$stream('/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /TFUnicode def /CMapType 2 def 1 begincodespacerange <0000> <FFFF> endcodespacerange 1 beginbfrange <0000> <FFFF> <0000> endbfrange endcmap CMapName currentdict /CMap defineresource pop end end');
        $fighters=$this->root.'/public/assets/logo-fighters-pdf.jpg';$fjpeg=file_get_contents($fighters);$finfo=getimagesize($fighters);$objects[10]='<< /Type /XObject /Subtype /Image /Width '.$finfo[0].' /Height '.$finfo[1].' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length '.strlen($fjpeg)." >>\nstream\n".$fjpeg."\nendstream";
        $objects[9]='<< /Type /XObject /Subtype /Image /Width '.$info[0].' /Height '.$info[1].' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length '.strlen($jpeg)." >>\nstream\n".$jpeg."\nendstream";$kids=[];
        foreach($this->pages as $i=>$page){$id=count($objects)+1;$content=$id+1;$kids[]="$id 0 R";$page.=$this->text(($s['is_demo']?'DEMO · ':'').'Top Fitness · '.$s['reference'].' · '.($i+1).'/'.count($this->pages),42,810,8);$objects[$id]='<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> /XObject << /Logo 9 0 R /LogoF 10 0 R >> >> /Contents '.$content.' 0 R >>';$objects[$content]=$stream($page);}
        $objects[2]='<< /Type /Pages /Count '.count($kids).' /Kids ['.implode(' ',$kids).'] >>';ksort($objects);$pdf="%PDF-1.7\n%\xE2\xE3\xCF\xD3\n";$offsets=[0];foreach($objects as $id=>$object){$offsets[$id]=strlen($pdf);$pdf.="$id 0 obj\n$object\nendobj\n";}$xref=strlen($pdf);$pdf.='xref'."\n0 ".(count($objects)+1)."\n0000000000 65535 f \n";foreach($objects as $id=>$v)$pdf.=sprintf('%010d 00000 n ', $offsets[$id])."\n";$pdf.='trailer << /Size '.(count($objects)+1).' /Root 1 0 R >>'."\nstartxref\n$xref\n%%EOF\n";return $pdf;
    }
}
