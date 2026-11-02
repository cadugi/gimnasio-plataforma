<?php
declare(strict_types=1);
trait PhotoOperations {
    public function draftPhotoInfo():?array {
        $d=$this->draft();
        return $this->one('SELECT image_hash,width,height FROM draft_photos WHERE draft_id=?',[$d['id']]);
    }
    public function savePhoto(array $r):array {
        $this->kiosk();
        ensure(($r['confirmed']??false)===true,'Confirma que quieres guardar esta foto.');
        $input=$r['image']??null;
        ensure(is_string($input)&&strlen($input)<=750000&&str_starts_with($input,'data:image/jpeg;base64,'),'Selecciona una foto JPEG de tamaño reducido.');
        $bytes=base64_decode(substr($input,23),true);
        ensure($bytes!==false&&strlen($bytes)<=550000&&str_starts_with($bytes,"\xff\xd8")&&str_ends_with($bytes,"\xff\xd9"),'La foto no tiene un formato válido.');
        $size=@getimagesizefromstring($bytes);
        ensure($size&&$size[2]===IMAGETYPE_JPEG&&$size[0]>=160&&$size[1]>=160&&$size[0]<=1280&&$size[1]<=1280,'La foto debe medir entre 160 y 1280 píxeles por lado.');
        // Canvas creates a fresh JPEG. Also remove application/comment segments
        // before the first scan, so EXIF/GPS and camera metadata are not retained.
        $clean="\xff\xd8";$at=2;$length=strlen($bytes);$scan=false;
        while($at<$length-2){
            ensure(ord($bytes[$at])===255,'Foto JPEG no válida.');
            while($at<$length&&ord($bytes[$at])===255)$at++;
            ensure($at+2<$length,'Foto JPEG incompleta.');
            $marker=ord($bytes[$at++]);
            ensure($marker!==0&&$marker!==216&&$marker!==217,'Foto JPEG no válida.');
            $segment=unpack('n',substr($bytes,$at,2))[1];
            ensure($segment>=2&&$at+$segment<=$length,'Foto JPEG incompleta.');
            if($marker===218){$clean.="\xff".chr($marker).substr($bytes,$at);$scan=true;break;}
            if(!(($marker>=224&&$marker<=239)||$marker===254))$clean.="\xff".chr($marker).substr($bytes,$at,$segment);
            $at+=$segment;
        }
        ensure($scan,'La foto no contiene una imagen JPEG.');
        return $this->transaction(function()use($r,$clean,$size){
            $d=$this->draft();$data=$this->open($d['data_enc']);
            ensure(($data['type']??'')!=='holder','Esta sesión es solo para el titular de la cuenta.',403);
            $hash=hash('sha256',$clean);
            $this->sql('INSERT INTO draft_photos(draft_id,image_enc,image_hash,width,height,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(draft_id) DO UPDATE SET image_enc=excluded.image_enc,image_hash=excluded.image_hash,width=excluded.width,height=excluded.height,created_at=excluded.created_at',[$d['id'],$this->vault->encrypt($clean,'photo'),$hash,$size[0],$size[1],instant()]);
            $this->sql('UPDATE drafts SET review_enc=NULL,review_hash=NULL,updated_at=? WHERE id=?',[instant(),$d['id']]);
            return ['image_hash'=>$hash,'width'=>$size[0],'height'=>$size[1]];
        });
    }
    public function removeDraftPhoto():array {
        return $this->transaction(function(){
            $d=$this->draft();$this->sql('DELETE FROM draft_photos WHERE draft_id=?',[$d['id']]);
            $this->sql('UPDATE drafts SET review_enc=NULL,review_hash=NULL WHERE id=?',[$d['id']]);
            return ['removed'=>true];
        });
    }
    public function photoDocument(string $id,bool $draft=false):string {
        if($draft){$d=$this->draft();$row=$this->one('SELECT * FROM draft_photos WHERE draft_id=?',[$d['id']]);}
        else{$this->staff(['admin','staff']);$row=$this->one('SELECT * FROM contract_photos WHERE contract_id=?',[$id]);}
        ensure($row,'No hay foto guardada.',404);
        $bytes=$this->vault->decrypt($row['image_enc'],'photo');
        ensure(hash_equals($row['image_hash'],hash('sha256',$bytes)),'La foto no supera la comprobación de integridad.',500);
        if(!$draft)$this->transaction(fn()=>$this->audit($this->actor(),'ENROLLMENT_PHOTO_VIEWED',$id));
        return $bytes;
    }
    public function enrollmentInbox():array {
        $this->staff(['admin','staff']);
        $rows=$this->contractList(['state'=>'SIGNED']);
        foreach($rows as &$row)$row['has_photo']=(bool)$this->one('SELECT contract_id FROM contract_photos WHERE contract_id=?',[$row['id']]);
        return ['items'=>$rows,'automatic_enrollment'=>false];
    }
}
