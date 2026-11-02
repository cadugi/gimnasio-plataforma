<?php
declare(strict_types=1);
/** Exportación de socios dados de alta al formato "Plantilla - Socios" del centro (.xlsx). Sin extensiones PHP: el zip se escribe a mano. */
trait MemberExportOperations {
    private const EXPORT_HEADERS=['CI','Fechas/otros ','Nº Socio ','Nombre','Apellido','Apellido ','FNacimiento','DNI','Teléfono','Mail ','Dirección ','Localidad','Plan ','IBAN','Primer mes ','F.Pago  ','Nota - Remesa  Control '];

    /** Primer apellido (con partículas "de la", "del"...) y resto. */
    private function splitSurname(string $surname):array{
        $w=preg_split('/\s+/u',trim($surname))?:[];$parts=['de','del','la','las','los','y','da','di','van','von','san'];$first=[];
        while($w){$x=array_shift($w);$first[]=$x;if(!in_array(mb_strtolower($x),$parts,true))break;}
        return [implode(' ',$first),implode(' ',$w)];
    }

    private function excelDate(string $iso):?int{
        $d=DateTimeImmutable::createFromFormat('!Y-m-d',substr($iso,0,10));if(!$d)return null;
        return (int)(($d->getTimestamp()-(new DateTimeImmutable('1899-12-30 00:00:00 UTC'))->getTimestamp())/86400);
    }

    /** Un socio por fila (su contrato firmado más reciente), por orden de alta. */
    public function membersExportRows():array{
        $rows=$this->sql("SELECT c.id,c.member_id,c.created_at,c.payment_method,c.initial_cents,c.snapshot_enc,m.innux_number,t.name tariff FROM contracts c JOIN members m ON m.id=c.member_id LEFT JOIN tariffs t ON t.id=c.tariff_id WHERE c.state='SIGNED' AND c.is_demo=0 ORDER BY c.created_at DESC");
        $seen=[];$out=[];
        foreach($rows as $r){
            if(isset($seen[$r['member_id']]))continue;$seen[$r['member_id']]=true;
            $s=$this->open($r['snapshot_enc']);$p=$s['personal'];[$a1,$a2]=$this->splitSurname((string)$p['surname']);
            $num=(string)($r['innux_number']??'');$debit=$r['payment_method']==='debit';
            $out[]=[
                '',
                ['d',$this->excelDate((string)$r['created_at'])],
                $num!==''&&ctype_digit($num)?['n',(int)$num]:$num,
                (string)$p['name'],$a1,$a2,
                ['d',$this->excelDate((string)$p['birth_date'])],
                (string)$p['document'],(string)$p['phone'],(string)$p['email'],(string)$p['address'],
                trim(((string)($p['postal_code']??'')).' '.(string)$p['town']),
                (string)($r['tariff']??($s['tariff']['name']??'')),
                $debit?(string)($s['bank']['iban']??''):'',
                ['n',(int)$r['initial_cents']/100],
                $debit?'Domiciliación':'Efectivo',
                '',
            ];
        }
        return array_reverse($out);
    }

    /** Mismas filas que el Excel, listas para JSON (fechas dd/mm/aaaa, importes como número). Para la hoja de Google. */
    public function membersExportSheet():array{
        $rows=array_map(fn($r)=>array_map(fn($v)=>is_array($v)?($v[0]==='d'?($v[1]===null?'':gmdate('d/m/Y',($v[1]-25569)*86400)):$v[1]):$v,$r),$this->membersExportRows());
        return ['headers'=>self::EXPORT_HEADERS,'rows'=>$rows];
    }

    public function membersExportXlsx():array{
        $rows=$this->membersExportRows();
        $x=fn(string $v)=>htmlspecialchars($v,ENT_XML1|ENT_QUOTES,'UTF-8');
        $col=fn(int $i)=>chr(65+$i);
        $cells=function(array $row,int $n,bool $head)use($x,$col){
            $o='';foreach($row as $i=>$v){
                $ref=$col($i).$n;
                if($head){$o.='<c r="'.$ref.'" s="1" t="inlineStr"><is><t xml:space="preserve">'.$x((string)$v).'</t></is></c>';continue;}
                if(is_array($v)){if($v[1]===null)continue;$o.='<c r="'.$ref.'" s="'.($v[0]==='d'?'3':'0').'"><v>'.$v[1].'</v></c>';continue;}
                if($v==='')continue;
                $o.='<c r="'.$ref.'" s="0" t="inlineStr"><is><t xml:space="preserve">'.$x((string)$v).'</t></is></c>';
            }
            return '<row r="'.$n.'">'.$o.'</row>';
        };
        $data=$cells(self::EXPORT_HEADERS,1,true);foreach($rows as $i=>$r)$data.=$cells($r,$i+2,false);
        $widths=[1=>9.75,2=>12.38,3=>10,4=>16,5=>16,6=>16,7=>13,8=>13,9=>14,10=>30,11=>34,12=>22,13=>26,14=>28,15=>11,16=>15,17=>24];
        $cols='';foreach($widths as $i=>$w)$cols.='<col customWidth="1" min="'.$i.'" max="'.$i.'" width="'.$w.'"/>';
        $ns='xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';$hd='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
        $files=[
            '[Content_Types].xml'=>$hd.'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
            '_rels/.rels'=>$hd.'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
            'xl/workbook.xml'=>$hd.'<workbook '.$ns.' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Hoja 1" sheetId="1" r:id="rId1"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels'=>$hd.'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
            'xl/styles.xml'=>$hd.'<styleSheet '.$ns.'><numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts><fonts count="2"><font><sz val="10"/><color rgb="FF000000"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FF000000"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEFEFEF"/><bgColor rgb="FFEFEFEF"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"><alignment horizontal="left"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
            'xl/worksheets/sheet1.xml'=>$hd.'<worksheet '.$ns.'><sheetFormatPr defaultColWidth="12.63" defaultRowHeight="15.75"/><cols>'.$cols.'</cols><sheetData>'.$data.'</sheetData></worksheet>',
        ];
        return ['bytes'=>$this->zipStore($files),'count'=>count($rows)];
    }

    private function zipStore(array $files):string{
        $out='';$cd='';$n=0;$time=0;$date=(2026-1980)<<9|1<<5|1;
        foreach($files as $name=>$data){
            $crc=crc32($data);$len=strlen($data);$off=strlen($out);
            $out.=pack('VvvvvvVVVvv',0x04034b50,20,0x0800,0,$time,$date,$crc,$len,$len,strlen($name),0).$name.$data;
            $cd.=pack('VvvvvvvVVVvvvvvVV',0x02014b50,20,20,0x0800,0,$time,$date,$crc,$len,$len,strlen($name),0,0,0,0,0,$off).$name;$n++;
        }
        return $out.$cd.pack('VvvvvVVv',0x06054b50,0,0,$n,$n,strlen($cd),strlen($out),0);
    }
}
