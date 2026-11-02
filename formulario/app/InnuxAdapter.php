<?php
declare(strict_types=1);
interface EnrollmentAdapter {
    public function capabilities():array;
    public function prepare(array $member,array $personal):array;
}
final class ManualInnuxAdapter implements EnrollmentAdapter {
    public function capabilities():array{return ['provider'=>'Innux Sports','automatic_enrollment'=>false,'verified_api'=>false,'verified_import'=>false,'mode'=>'MANUAL_ASSISTED'];}
    public function prepare(array $member,array $personal):array{return ['member_id'=>$member['id'],'internal_reference'=>$member['internal_reference'],'personal'=>$personal,'state'=>$member['innux_state'],'automatic_available'=>false,'adapter'=>$this->capabilities(),'message'=>'Introduce estos datos en la aplicación oficial de Innux. Después registra la referencia y el número que Innux asigne. No se ha creado ningún socio en Innux.'];}
}
