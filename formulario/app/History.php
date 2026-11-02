<?php
declare(strict_types=1);
/* Historial de altas y bajas: solo lectura. Une contratos firmados y solicitudes de baja/mantenimiento,
   que la base ya protege contra borrados, para que recepción vea siempre todo lo tramitado. */

trait HistoryOperations {
    public function movementHistory(array $r):array{
        $this->staff(['admin','staff','viewer']);$out=[];
        foreach($this->sql('SELECT c.id,c.reference,c.created_at,c.state,c.center_accepted_at,c.center_actor,c.previous_id,c.payment_method,c.monthly_cents,m.innux_number,m.personal_enc FROM contracts c JOIN members m ON m.id=c.member_id ORDER BY c.created_at DESC') as $c){
            $p=$this->open($c['personal_enc']);
            $out[]=['id'=>$c['id'],'source'=>'contract','kind'=>$c['previous_id']?'NEW_VERSION':'ENROLLMENT','reference'=>$c['reference'],'name'=>$p['name'].' '.$p['surname'],
                'member_number'=>$c['innux_number'],'created_at'=>$c['created_at'],'state'=>$c['state']==='CANCELLED'?'ANNULLED':($c['center_accepted_at']?'ACCEPTED':'PENDING'),
                'decided_at'=>$c['center_accepted_at'],'decided_actor'=>$c['center_actor'],'effective_date'=>null,'returned_at'=>null,'payment_method'=>$c['payment_method'],'monthly_cents'=>(int)$c['monthly_cents']];
        }
        foreach($this->sql('SELECT id,reference,kind,state,snapshot_enc,created_at,effective_date,decided_at,decided_actor,returned_at FROM withdrawals ORDER BY created_at DESC') as $w){
            $s=$this->open($w['snapshot_enc']);
            $out[]=['id'=>$w['id'],'source'=>'withdrawal','kind'=>$w['kind'],'reference'=>$w['reference'],'name'=>$s['personal']['name'].' '.$s['personal']['surname'],
                'member_number'=>$s['member_number'],'created_at'=>$w['created_at'],'state'=>$w['state'],'decided_at'=>$w['decided_at'],'decided_actor'=>$w['decided_actor'],
                'effective_date'=>$w['effective_date'],'returned_at'=>$w['returned_at'],'payment_method'=>null,'monthly_cents'=>null];
        }
        foreach($out as &$row)$row['decided_actor_name']=$this->actorDisplay($row['decided_actor']);unset($row);
        usort($out,fn($a,$b)=>strcmp($b['created_at'],$a['created_at']));
        return $out;
    }
}
