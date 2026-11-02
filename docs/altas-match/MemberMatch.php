<?php
declare(strict_types=1);
/**
 * Coincidencia EXACTA nombre + teléfono para Reservas. Nunca devuelve datos personales:
 * solo NONE | ONE | MANY y, si es ONE, la referencia interna de la ficha. No crea, vincula ni modifica nada.
 * Los datos siguen cifrados: se descifran aquí dentro, ficha a ficha.
 */
trait MemberMatchOperations {
    public static function matchPhone(string $raw):string{
        $d=preg_replace('/\D/','',$raw)??'';
        if(str_starts_with($d,'00'))$d=substr($d,2);
        if(strlen($d)===11&&str_starts_with($d,'34'))$d=substr($d,2);
        return preg_match('/^[6-9]\d{8}$/',$d)===1?$d:'';
    }
    public static function matchName(string $raw):string{
        $s=mb_strtolower(trim($raw),'UTF-8');$s=preg_replace('/\s+/u',' ',$s)??$s;
        // Sin depender de la extensión intl (no está en este PHP): tabla explícita de letras con tilde.
        return strtr($s,['á'=>'a','à'=>'a','ä'=>'a','â'=>'a','é'=>'e','è'=>'e','ë'=>'e','ê'=>'e','í'=>'i','ì'=>'i','ï'=>'i','î'=>'i','ó'=>'o','ò'=>'o','ö'=>'o','ô'=>'o','ú'=>'u','ù'=>'u','ü'=>'u','û'=>'u','ç'=>'c']);
    }
    /** Comprueba el token de servicio de Reservas (hash en settings.reservas_match_token_hash). */
    public function matchAuthorize(string $given):void{
        $hash=$this->one("SELECT value FROM settings WHERE name='reservas_match_token_hash'")['value']??'';
        ensure($hash!==''&&$given!==''&&hash_equals($hash,hash('sha256',$given)),'No autorizado.',403);
    }
    public function memberMatch(array $r):array{
        $name=self::matchName((string)($r['name']??''));$phone=self::matchPhone((string)($r['phone']??''));
        ensure(mb_strlen($name)>=3&&mb_strlen($name)<=120&&$phone!=='','Datos no válidos.');
        $refs=[];
        foreach($this->sql("SELECT id,personal_enc FROM members WHERE state='ACTIVE'") as $m){
            $p=$this->open($m['personal_enc']);
            if(self::matchPhone((string)($p['phone']??''))!==$phone)continue;
            if(self::matchName(trim(($p['name']??'').' '.($p['surname']??'')))!==$name)continue;
            $refs[]=$m['id'];if(count($refs)>1)break;
        }
        return count($refs)===0?['result'=>'NONE']:(count($refs)===1?['result'=>'ONE','ref'=>$refs[0]]:['result'=>'MANY']);
    }
}
