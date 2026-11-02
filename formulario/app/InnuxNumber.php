<?php
declare(strict_types=1);

final class InnuxNumberReader {
    public function __construct(private string $python,private string $script){}
    public function read(array $personal):array {
        ensure(is_file($this->python)&&is_file($this->script),'No está configurado el lector local de Innux.',503);
        $pipes=[];$process=proc_open([$this->python,$this->script],[['pipe','r'],['pipe','w'],['pipe','w']],$pipes,null,null,['bypass_shell'=>true,'create_process_group'=>false,'create_new_console'=>false]);
        ensure(is_resource($process),'No se pudo iniciar la consulta de Innux.',503);
        fwrite($pipes[0],jencode(['document'=>$personal['document'],'birth_date'=>$personal['birth_date']]));fclose($pipes[0]);
        stream_set_blocking($pipes[1],false);stream_set_blocking($pipes[2],false);
        $output='';$start=microtime(true);$timeout=false;
        try{
            while(true){
                $output.=stream_get_contents($pipes[1],4097);stream_get_contents($pipes[2],4097);
                ensure(strlen($output)<=4096,'Respuesta de Innux no válida.',503);
                $state=proc_get_status($process);if(!$state['running'])break;
                if(microtime(true)-$start>12){$timeout=true;break;}
                usleep(25000);
            }
            ensure(!$timeout,'Innux no responde. No se ha asignado ningún número.',503);
            $output.=stream_get_contents($pipes[1],4097);
            $result=json_decode($output,true);
            ensure(is_array($result)&&in_array($result['status']??'', ['FOUND','NOT_FOUND','AMBIGUOUS','NUMBER_PENDING','UNAVAILABLE','INVALID_INPUT'],true),'No se pudo comprobar el número de socio.',503);
            return $result;
        }finally{
            $state=proc_get_status($process);if($state['running'])proc_terminate($process);
            fclose($pipes[1]);fclose($pipes[2]);proc_close($process);
        }
    }
}

trait InnuxNumberOperations {
    public function numberLookupCapabilities():array {
        $cfg=$this->config['innux_number_lookup']??[];
        return ['available'=>!$this->demo()&&($cfg['enabled']??false)===true,'read_only'=>true,'assigns_free_number'=>false,'creates_member'=>false];
    }
    public function lookupInnuxNumber(string $member):array {
        $this->staff(['admin','staff']);
        ensure(!$this->demo(),'La demo no consulta ni vincula personas ficticias con socios reales de Innux.',409);
        $cfg=$this->config['innux_number_lookup']??[];
        ensure(($cfg['enabled']??false)===true,'La consulta de Innux no está configurada.',409);
        $m=$this->one('SELECT * FROM members WHERE id=?',[$member]);ensure($m,'Socio no encontrado.',404);
        ensure($this->one("SELECT id FROM contracts WHERE member_id=? AND state='SIGNED' AND is_demo=0",[$member]),'Falta un contrato real firmado para esta ficha.',409);
        $personal=$this->open($m['personal_enc']);
        $result=(new InnuxNumberReader((string)($cfg['python']??''),$this->root.'/scripts/innux_number_reader.py'))->read($personal);
        $messages=['NOT_FOUND'=>'La ficha todavía no aparece en Innux con ese documento y fecha de nacimiento.','AMBIGUOUS'=>'Hay varias coincidencias. Un trabajador debe resolverlas en Innux.','NUMBER_PENDING'=>'Innux todavía no tiene un número de socio válido.','UNAVAILABLE'=>'No se pudo conectar con Innux. No se ha asignado ningún número.','INVALID_INPUT'=>'Revisa documento y fecha de nacimiento.'];
        if($result['status']!=='FOUND')return ['linked'=>false,'status'=>$result['status'],'message'=>$messages[$result['status']]];
        return $this->bindInnuxNumber($member,$personal,$result);
    }
    private function bindInnuxNumber(string $member,array $personal,array $result):array {
        ensure(preg_match('/^[1-9][0-9]{0,9}$/',(string)($result['client_id']??''))===1&&preg_match('/^[1-9][0-9]{0,9}$/',(string)($result['number']??''))===1,'Identificadores de Innux no válidos.',409);
        return $this->transaction(function()use($member,$personal,$result){
            $m=$this->one('SELECT * FROM members WHERE id=?',[$member]);ensure($m,'Socio no encontrado.',404);
            $current=$this->open($m['personal_enc']);
            ensure($current['document']===$personal['document']&&$current['birth_date']===$personal['birth_date'],'La ficha ha cambiado. Repite la comprobación.',409);
            $ref='INNUX:'.$result['client_id'];
            ensure(($m['innux_reference']===null||$m['innux_reference']===$ref)&&($m['innux_number']===null||$m['innux_number']===$result['number']),'Ya hay otra vinculación. Revísala antes de sustituirla.',409);
            ensure(!$this->one('SELECT id FROM members WHERE id<>? AND (innux_reference=? OR innux_number=?)',[$member,$ref,$result['number']]),'Ese socio de Innux ya está vinculado a otra ficha.',409);
            $this->sql("UPDATE members SET innux_reference=?,innux_number=?,innux_state='VERIFIED_READ_ONLY' WHERE id=?",[$ref,$result['number'],$member]);
            $this->audit($this->actor(),'INNUX_NUMBER_VERIFIED_READ_ONLY',$member,['source'=>'document_and_birth_date','client_id'=>$result['client_id'],'number'=>$result['number']]);
            return ['linked'=>true,'status'=>'FOUND','innux_number'=>$result['number'],'created_in_innux'=>false,'message'=>'Número recuperado de Innux y vinculado. No se ha creado una ficha nueva.'];
        });
    }
}
