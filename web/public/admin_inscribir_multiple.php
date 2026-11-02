<?php
declare(strict_types=1);
// Solo administración: apunta a una persona a varias clases (varios días) de una vez.
// Respeta el aforo: las clases completas van a lista de espera.
header('Content-Type: application/json; charset=UTF-8');
if (empty($_SERVER['REMOTE_USER'])) { http_response_code(401); echo '{"success":false,"error":"AUTH_REQUIRED"}'; exit; }
require_once __DIR__ . '/conexion.php';
require_once dirname(__DIR__) . '/sso/booking_identity.php';
require_once dirname(__DIR__) . '/sso/offers.php';
try {
    $name = trim((string)($_POST['nombre'] ?? ''));
    $phone = trim((string)($_POST['telefono'] ?? ''));
    $items = json_decode((string)($_POST['sesiones'] ?? '[]'), true);
    if (!$name || !$phone || mb_strlen($name) > 100 || strlen($phone) > 15 || !is_array($items) || !$items) {
        http_response_code(400); echo '{"success":false,"error":"PARAMS"}'; exit;
    }
    $dias = ['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
    $results = [];
    $seen = [];
    foreach ($items as $it) {
        $schedule = (int)($it['horario_id'] ?? 0);
        $date = trim((string)($it['fecha'] ?? ''));
        $res = ['horario_id' => $schedule, 'fecha' => $date, 'estado' => 'ERROR'];
        $d = DateTimeImmutable::createFromFormat('!Y-m-d', $date);
        $key = $schedule . '|' . $date;
        if ($schedule <= 0 || !$d || $d->format('Y-m-d') !== $date) { $results[] = $res; continue; }
        $seen[$key] = true;
        try {
            $conn->begin_transaction();
            $conn->query('SELECT id FROM tf_mutex WHERE id=1 FOR UPDATE');
            $stmt = $conn->prepare('SELECT clase, dia, hora, limite FROM horarios WHERE id=? FOR UPDATE');
            $stmt->bind_param('i', $schedule); $stmt->execute();
            $h = $stmt->get_result()->fetch_assoc(); $stmt->close();
            if (!$h || $h['dia'] !== $dias[(int)$d->format('w')]) { $conn->rollback(); $res['estado'] = 'DIA_NO_COINCIDE'; $results[] = $res; continue; }
            $res['clase'] = $h['clase']; $res['hora'] = $h['hora'];
            // Una clase cancelada no admite inscripciones (también se rechaza aquí, no solo en la pantalla)
            if (tfIdCancelled($conn, $schedule, $date)) { $conn->rollback(); $res['estado'] = 'CANCELADA'; $results[] = $res; continue; }
            // Nunca dos veces a la misma persona en la misma sesión
            if (tfIdFindInscription($conn, $schedule, $date, $name, $phone)) { $conn->rollback(); $res['estado'] = 'YA_APUNTADO'; $results[] = $res; continue; }
            // Una clase completa se resuelve por la cola, igual que la inscripción individual.
            $limite = (int)$h['limite'];
            if ($limite > 0) {
                $stmt = $conn->prepare('SELECT COUNT(*) AS n FROM inscripciones WHERE horario_id=? AND fecha=?'); $stmt->bind_param('is', $schedule, $date); $stmt->execute();
                $n = (int)$stmt->get_result()->fetch_assoc()['n']; $stmt->close();
                $n += tfHeld($conn, $schedule, $date);   // plazas retenidas por ofertas
                if ($n >= $limite) {
                    $waiting=tfIdFindWaiting($conn,$schedule,$date,$phone);
                    if($waiting&&!tfIdSame($name,$phone,(string)$waiting['nombre'],(string)$waiting['telefono'])){
                        $conn->rollback();$res['estado']='ESPERA_OTRA_PERSONA';$results[]=$res;continue;
                    }
                    if(!$waiting){
                        try{tfRequireNoticesForWaitlist($conn,$schedule,$date,$name,$phone);}catch(WebError $e){$conn->rollback();$res['estado']='REQUIERE_AVISOS';$results[]=$res;continue;}
                        $stmt=$conn->prepare('INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())');
                        $stmt->bind_param('ssis',$name,$phone,$schedule,$date);$stmt->execute();$id=$conn->insert_id;$stmt->close();
                        tfIdAudit($conn,'ADMIN_WAITLIST_ADDED',['horario_id'=>$schedule,'fecha'=>$date,'espera'=>$id]);
                    }
                    $conn->commit();$res['estado']=$waiting?'YA_EN_ESPERA':'EN_ESPERA';$results[]=$res;continue;
                }
            }
            $stmt = $conn->prepare('INSERT INTO inscripciones(nombre,telefono,horario_id,fecha,creado_en) VALUES(?,?,?,?,NOW())');
            $stmt->bind_param('ssis', $name, $phone, $schedule, $date); $stmt->execute(); $stmt->close();
            $newId = (int)$conn->insert_id;
            $res['avisos'] = tfNotifyReceptionBooking($conn, $name, $phone, $schedule, $date, $newId) > 0;   // false = esa persona no recibirá avisos
            $conn->commit(); $res['estado'] = 'APUNTADO'; $results[] = $res;
        } catch (Throwable $e) {
            try { $conn->rollback(); } catch (Throwable $e2) {}
            $res['estado'] = 'ERROR'; $results[] = $res;
        }
    }
    echo json_encode(['success' => true, 'resultados' => $results], JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) { http_response_code(500); echo '{"success":false,"error":"SERVICE_ERROR"}'; }
