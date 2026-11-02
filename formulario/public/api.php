<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/app/Service.php';require_once dirname(__DIR__).'/app/Http.php';
secureHeaders();
try{
    $root=dirname(__DIR__);$s=new Service($root,readConfig($root));
    if(isset($_SERVER['HTTP_X_TF_CONNECTOR'])){
        ensure(($_SERVER['REQUEST_METHOD']??'')==='POST','Método no permitido.',405);
        ensure($s->demo()||($_SERVER['HTTPS']??'')==='on','HTTPS obligatorio.',426);
        $s->config['request_portal']=(string)($_SERVER['TF_PORTAL']??'');
        $raw=file_get_contents('php://input',false,null,0,100001);ensure(strlen($raw)<=100000,'Solicitud demasiado grande.',413);
        $device=$s->authenticateInnuxDevice($raw,['id'=>$_SERVER['HTTP_X_TF_CONNECTOR'],'timestamp'=>$_SERVER['HTTP_X_TF_TIMESTAMP']??'','nonce'=>$_SERVER['HTTP_X_TF_NONCE']??'','signature'=>$_SERVER['HTTP_X_TF_SIGNATURE']??'']);
        $payload=json_decode($raw,true,32,JSON_THROW_ON_ERROR);ensure(is_array($payload),'Solicitud no válida.');
        jsonResponse(['ok'=>true,'data'=>$s->innuxDeviceOperation($device,$payload)]);
    }
    if(($_SERVER['REQUEST_METHOD']??'')==='GET'&&($_GET['action']??'')==='sheets_members'){
        $s->limit('sheets:'.($_SERVER['REMOTE_ADDR']??''),40,900);
        $hash=$s->one("SELECT value FROM settings WHERE name='sheets_token_hash'")['value']??'';
        $given=(string)($_SERVER['HTTP_X_TF_SHEETS']??'');
        ensure($hash!==''&&$given!==''&&hash_equals($hash,hash('sha256',$given)),'No autorizado.',403);
        jsonResponse(['ok'=>true,'data'=>$s->membersExportSheet()]);
    }
    startHttp($s);$method=$_SERVER['REQUEST_METHOD']??'GET';$r=[];
    if($method==='POST'){ensure((int)($_SERVER['CONTENT_LENGTH']??0)<=1200000,'Solicitud demasiado grande.',413);ensure(str_starts_with($_SERVER['CONTENT_TYPE']??'','application/json'),'Se requiere JSON.',415);$raw=file_get_contents('php://input',false,null,0,1200001);ensure(strlen($raw)<=1200000,'Solicitud demasiado grande.',413);$r=json_decode($raw,true,64,JSON_THROW_ON_ERROR);ensure(is_array($r),'Solicitud no válida.');if(($r['action']??'')!=='sso_logout')ensure(hash_equals($_SESSION['csrf'],$_SERVER['HTTP_X_CSRF_TOKEN']??''),'La sesión ha cambiado. Recarga la página.',403);ensure(is_string($r['action']??null),'Operación no válida.');$action=$r['action'];if(array_key_exists('data',$r))ensure(is_array($r['data']),'Formulario no válido.');}
    else{ensure($method==='GET','Método no permitido.',405);$action=(string)($_GET['action']??'bootstrap');ensure(in_array($action,['bootstrap','ping','document','review_document','preview_pdf','withdrawal_review','withdrawal_preview','withdrawal_document','mandate_document','export_file','export_members','backup_file','enrollment_photo','draft_photo','retirement_file'],true),'Método no permitido.',405);}
    // QA_TOTAL: registrar también las consultas; nunca registrar cuerpos ni contraseñas.
    if(($_SESSION['mode']??'')==='admin'){
        $qa=$s->one("SELECT id,username,active,epoch FROM users WHERE id=?",[$_SESSION['user_id']??'']);
        if($qa&&$qa['username']==='qa_total'&&(int)$qa['active']===1&&(int)$qa['epoch']===($_SESSION['epoch']??0))
            $s->transaction(fn()=>$s->audit('qa_total','QA_REQUEST',substr($action,0,80),['method'=>$method]));
    }
    checkPortalAction($s,$action);
    $result=null;
    if($action==='bootstrap'){$user=null;if(($_SESSION['mode']??'')==='admin'){try{$user=$s->staff();}catch(AppError $e){$_SESSION=['csrf'=>uuid()];}}$catalog=$s->catalog();$draft=null;if(($_SESSION['mode']??'')==='kiosk'&&!empty($_SESSION['draft_id'])){try{$d=$s->draft();$data=$s->open($d['data_enc']);$draft=['photo'=>$s->draftPhotoInfo(),'id'=>$d['id'],'data'=>$data,'member_number'=>isset($data['member_id'])?($s->one('SELECT innux_number FROM members WHERE id=?',[$data['member_id']])['innux_number']??null):null,'review_hash'=>$d['review_hash']];if(($data['type']??'')==='holder'&&$d['review_enc']){$snap=$s->open($d['review_enc']);$draft['holder']=['name'=>$snap['bank']['holder'],'iban_masked'=>'•••• '.substr($snap['bank']['iban'],-4)];}}catch(AppError $e){unset($_SESSION['draft_id']);}}$result=['portal'=>$s->config['request_portal']??null,'innux_number_lookup'=>$s->numberLookupCapabilities(),'server_date'=>date('d-m-Y'),'csrf'=>$_SESSION['csrf'],'mode'=>$_SESSION['mode']??'guest','user'=>$user,'environment'=>$s->config['environment'],'demo_login'=>empty($_SESSION['kiosk_locked'])&&$s->demo()&&($s->config['demo_loopback_login']??false)&&in_array($_SERVER['REMOTE_ADDR']??'',['127.0.0.1','::1'],true),'catalog'=>$catalog,'draft'=>$draft,'tablet_connection_test'=>$draft?$s->tabletConnectionTest($draft['id']):false,'receipt'=>$_SESSION['receipt']??null,'receipt_mandate'=>$_SESSION['receipt_mandate']??null,'expired'=>$_SESSION['expired']??false,'kiosk_idle_seconds'=>$s->config['kiosk_idle_seconds']??300];unset($_SESSION['expired']);}
    elseif($action==='ping'){$result=['mode'=>$_SESSION['mode']??'guest','expired'=>$_SESSION['expired']??false];unset($_SESSION['expired']);}
    elseif($action==='login'){$name=trim((string)($r['username']??''));$s->limit('login-ip:'.($_SERVER['REMOTE_ADDR']??''),12,900);$s->limit('login-user:'.strtolower($name),8,900);$u=$s->one('SELECT * FROM users WHERE username=? AND active=1',[$name]);$valid=$u&&!(int)($u['sso']??0)&&verifyAccessPassword((string)($r['password']??''),$u['password_hash']);ensure($valid,'Usuario o contraseña incorrectos.',401);if(password_needs_rehash($u['password_hash'],PASSWORD_ARGON2ID))$s->sql('UPDATE users SET password_hash=? WHERE id=? AND password_hash=?',[password_hash((string)$r['password'],PASSWORD_ARGON2ID),$u['id'],$u['password_hash']]);session_regenerate_id(true);$_SESSION=['mode'=>'admin','user_id'=>$u['id'],'epoch'=>(int)$u['epoch'],'csrf'=>uuid(),'last_activity'=>time()];$s->transaction(fn()=>$s->audit($u['id'],'LOGIN',$u['id']));$result=['csrf'=>$_SESSION['csrf']];}
    elseif($action==='sso_logout'){
        ensure(($s->config['request_portal']??'')==='admin','Portal no válido.',403);
        $s->ssoLogout($s->ssoVerify((string)($r['ticket']??''),null,'logout'));
        $result=['revoked'=>true];
    }
    elseif($action==='sso_login'){$s->limit('sso-ip:'.($_SERVER['REMOTE_ADDR']??''),30,900);ensure(($s->config['request_portal']??'')==='admin','Portal de recepción requerido.',403);$u=$s->ssoLogin($s->ssoVerify((string)($r['ticket']??'')));session_regenerate_id(true);$_SESSION=['mode'=>'admin','user_id'=>$u['id'],'epoch'=>(int)$u['epoch'],'csrf'=>uuid(),'last_activity'=>time(),'sso'=>true];$result=['csrf'=>$_SESSION['csrf'],'role'=>$u['role']];}
    elseif($action==='demo_login'){ensure(empty($_SESSION['kiosk_locked'])&&$s->demo()&&($s->config['demo_loopback_login']??false)&&in_array($_SERVER['REMOTE_ADDR']??'',['127.0.0.1','::1'],true),'El acceso demo solo está disponible en loopback y con datos ficticios.',403);$u=$s->one("SELECT * FROM users WHERE role='admin' AND active=1 ORDER BY created_at LIMIT 1");ensure($u,'Falta preparar el entorno demo.',503);session_regenerate_id(true);$_SESSION=['mode'=>'admin','user_id'=>$u['id'],'epoch'=>(int)$u['epoch'],'csrf'=>uuid(),'last_activity'=>time()];$result=['csrf'=>$_SESSION['csrf']];}
    elseif($action==='logout'){$locked=(bool)($_SESSION['kiosk_locked']??false);$_SESSION=['csrf'=>uuid(),'kiosk_locked'=>$locked];session_regenerate_id(true);$result=['csrf'=>$_SESSION['csrf']];}
    else{
        $s->limit('api:'.session_id(),180,60);
        $roles=['history'=>['admin','staff','viewer'],'withdrawals'=>['admin','staff','viewer'],'withdrawal_detail'=>['admin','staff','viewer'],'withdrawal_accept'=>['admin','staff'],'withdrawal_reject'=>['admin','staff'],'withdrawal_return'=>['admin','staff'],'export_members'=>['admin'],'tablet_invitation'=>['admin','staff'],'lookup_innux_number'=>['admin','staff'],'enrollment_inbox'=>['admin','staff'],'dashboard'=>['admin','staff','finance','viewer'],'contracts'=>['admin','staff','viewer'],'contract_detail'=>['admin','staff','viewer'],'accept_contract'=>['admin','staff'],'annul_contract'=>['admin','staff'],'new_version'=>['admin','staff'],'pending_drafts'=>['admin','staff'],'discount_draft'=>['admin','staff'],'handoff'=>['admin','staff'],'mark_innux'=>['admin','staff'],'billing'=>['admin','finance'],'prepare_dues'=>['admin','finance'],'profiles'=>['admin','finance'],'export_preview'=>['admin','finance'],'generate_batch'=>['admin','finance'],'batches'=>['admin','finance'],'export_file'=>['admin','finance'],'change_due'=>['admin','finance'],'configuration'=>['admin'],'save_tariff'=>['admin'],'save_legal'=>['admin'],'save_profile'=>['admin'],'save_user'=>['admin'],'save_settings'=>['admin'],'audit'=>['admin'],'backup'=>['admin'],'backup_file'=>['admin'],'privacy_request'=>['admin'],'queue_email'=>['admin','staff'],'begin_holder'=>['admin','staff','finance'],'retirement_candidates'=>['admin'],'innux_search'=>['admin'],'innux_search_result'=>['admin'],'retirement_list'=>['admin'],'retirement_request'=>['admin'],'retirement_retry'=>['admin'],'retirement_cancel'=>['admin'],'retirement_archive'=>['admin'],'retirement_file'=>['admin']];if(isset($roles[$action]))$s->staff($roles[$action]);
        switch($action){
            case 'member_search':$result=$s->memberSearch($r);break;
            case 'member_detail':$result=$s->memberDetail($r);break;
            case 'member_innux_start':$result=$s->memberInnuxStart($r);break;
            case 'member_innux_result':$result=$s->memberInnuxResult($r);break;
            case 'innux_status':$result=$s->innuxStatus((string)($r['member_id']??''));break;
            case 'innux_link_existing':$s->staff(['admin','staff']);ensure(($r['confirmed']??false)===true,'Confirma la vinculación sin modificar Innux.');$result=$s->authorizeExistingInnux(textField($r,'job_id',32));break;
            case 'accept_and_sync':$s->staff(['admin','staff']);$id=textField($r,'id',32);$s->acceptContract($id);$result=$s->enqueueInnux($id,$r);break;
            case 'tablet_invitation':$result=$s->issueTabletInvite();break;
            case 'tablet_activate':$result=$s->activateTablet($r);break;
            case 'tablet_lock':$result=$s->lockTablet();break;
            case 'kiosk_start':$u=$s->staff(['admin','staff']);$id=$u['id'];$_SESSION=['mode'=>'kiosk','kiosk_locked'=>true,'device_actor'=>$id,'csrf'=>uuid(),'last_activity'=>time()];session_regenerate_id(true);$result=['csrf'=>$_SESSION['csrf']];break;
            case 'photo_save':$result=$s->savePhoto($r);break;
            case 'photo_remove':$result=$s->removeDraftPhoto();break;
            case 'draft_photo':fileResponse($s->photoDocument('',true),'image/jpeg','foto-alta.jpg',true);
            case 'enrollment_photo':fileResponse($s->photoDocument((string)($_GET['id']??'')),'image/jpeg','foto-alta.jpg',true);
            case 'enrollment_inbox':$result=$s->enrollmentInbox();break;
            case 'draft_new':$result=$s->newDraft();unset($_SESSION['receipt_mandate']);break;
case 'withdrawal_start':$result=$s->withdrawalStart(textField($r,'kind',12));break;
case 'withdrawal_identify':$result=$s->withdrawalIdentify($r);break;
case 'withdrawal_save':$result=$s->withdrawalSave($r);break;
case 'withdrawal_prepare':$result=$s->withdrawalPrepare();break;
case 'withdrawal_sign':$result=$s->withdrawalSign($r);session_regenerate_id(true);$_SESSION['csrf']=uuid();$result['csrf']=$_SESSION['csrf'];break;
case 'withdrawal_cancel':$result=$s->withdrawalCancel();session_regenerate_id(true);$_SESSION['csrf']=uuid();$result['csrf']=$_SESSION['csrf'];break;
case 'withdrawal_review':header('Content-Type: text/html; charset=utf-8');echo $s->withdrawalReviewHtml();exit;
case 'withdrawal_preview':fileResponse($s->withdrawalPreviewPdf(),'application/pdf','vista-previa-baja.pdf',true);
case 'withdrawal_document':fileResponse($s->withdrawalDocument((string)($_GET['id']??'')),'application/pdf','solicitud-baja-topfitness.pdf',isset($_GET['inline']));
            case 'draft_save':$result=$s->saveDraft($r['data']??[]);break;
            case 'draft_prepare':$result=$s->prepareContract();break;
            case 'review_document':$d=$s->draft();ensure($d['review_enc']!==null,'Revisa antes el contrato.');header('Content-Type: text/html; charset=utf-8');echo contractReview($s->open($d['review_enc']));exit;
            case 'preview_pdf':fileResponse($s->previewPdf(),'application/pdf','vista-previa.pdf',true);
            case 'contract_sign':$result=$s->signContract($r);session_regenerate_id(true);$_SESSION['csrf']=uuid();$result['csrf']=$_SESSION['csrf'];break;
            case 'draft_cancel':$result=$s->cancelDraft();unset($_SESSION['holder_mandate'],$_SESSION['receipt_mandate']);session_regenerate_id(true);$_SESSION['csrf']=uuid();$result['csrf']=$_SESSION['csrf'];break;
            case 'document':fileResponse($s->document((string)($_GET['id']??'')),'application/pdf','contrato-topfitness.pdf',isset($_GET['inline']));
            case 'mandate_document':fileResponse($s->mandateDocument((string)($_GET['id']??'')),'application/pdf','mandato-topfitness.pdf',isset($_GET['inline']));
            case 'dashboard':$result=$s->dashboard();break;
case 'history':$result=$s->movementHistory($r);break;
case 'withdrawals':$result=$s->withdrawalList($r);break;
case 'withdrawal_detail':$result=$s->withdrawalDetail(textField($r,'id',36));break;
case 'withdrawal_accept':ensure(($r['confirmed']??false)===true,'Confirma que la has tramitado en Innux.');$result=$s->acceptWithdrawal(textField($r,'id',36));break;
case 'withdrawal_reject':$result=$s->rejectWithdrawal(textField($r,'id',36),textField($r,'reason',300));break;
case 'withdrawal_return':$result=$s->withdrawalReturn(textField($r,'id',36),textField($r,'date',10),textField($r,'tariff_id',36));break;
            case 'contracts':$result=['items'=>$s->contractList($r)];break;
            case 'contract_detail':$result=$s->contractDetail(textField($r,'id',32));break;
            case 'accept_contract':$result=$s->acceptContract(textField($r,'id',32));break;
            case 'annul_contract':$result=$s->annulContract(textField($r,'id',32),textField($r,'reason',600));break;
            case 'new_version':$old=$s->one('SELECT * FROM contracts WHERE id=?',[textField($r,'id',32)]);ensure($old,'Contrato no encontrado.',404);$snapshot=$s->open($old['snapshot_enc']);if(($s->config['request_portal']??'')==='admin'){$result=$s->issueTabletInvite(['kind'=>'contract','prefill'=>['personal'=>$snapshot['personal'],'brand'=>$snapshot['tariff']['brand'],'tariff_id'=>$snapshot['tariff']['id'],'payment_method'=>'cash','consents'=>['marketing'=>false],'member_id'=>$old['member_id'],'previous_id'=>$old['id']]]);break;}$actor=$s->actor();$_SESSION=['mode'=>'kiosk','kiosk_locked'=>true,'device_actor'=>$actor,'csrf'=>uuid(),'last_activity'=>time()];session_regenerate_id(true);$s->newDraft(['personal'=>$snapshot['personal'],'brand'=>$snapshot['tariff']['brand'],'tariff_id'=>$snapshot['tariff']['id'],'payment_method'=>'cash','consents'=>['marketing'=>false],'member_id'=>$old['member_id'],'previous_id'=>$old['id']]);$result=['csrf'=>$_SESSION['csrf']];break;
            case 'pending_drafts':$result=['items'=>$s->pendingDrafts()];break;
            case 'discount_draft':$result=$s->discountDraft($r);break;
            case 'handoff':$result=$s->manualHandoff(textField($r,'member_id',32));break;
            case 'lookup_innux_number':$result=$s->lookupInnuxNumber(textField($r,'member_id',32));break;
            case 'mark_innux':$result=$s->markInnux($r);break;
            case 'billing':$result=['items'=>$s->billingList($r)];break;
            case 'prepare_dues':$result=$s->prepareDues($r);break;
            case 'profiles':$result=['items'=>$s->sql('SELECT * FROM export_profiles WHERE active=1 ORDER BY name')];break;
            case 'export_preview':$result=$s->exportPreview($r);break;
            case 'generate_batch':$result=$s->generateBatch($r);break;
            case 'batches':$result=['items'=>$s->batches()];break;
            case 'export_members':$x=$s->membersExportXlsx();$s->transaction(fn()=>$s->audit($s->actor(),'MEMBERS_EXPORTED','socios',['count'=>$x['count']]));fileResponse($x['bytes'],'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','Socios-TopFitness-'.date('Y-m-d').'.xlsx');
            case 'export_file':$f=$s->exportDocument((string)($_GET['id']??''));fileResponse($f['bytes'],$f['mime'],$f['filename']);
            case 'change_due':$result=$s->changeDue($r);break;
            case 'configuration':$result=$s->configView();break;
            case 'save_tariff':$result=$s->saveTariff($r);break;
            case 'save_legal':$result=$s->saveLegal($r);break;
            case 'save_profile':$result=$s->saveProfile($r);break;
            case 'save_user':$result=$s->saveUser($r);break;
            case 'save_settings':$result=$s->saveSettings($r);break;
            case 'audit':$result=['items'=>$s->auditList(),'integrity_ok'=>$s->verifyAudit(),'privacy_requests'=>$s->sql('SELECT id,member_id,state,actor,created_at FROM privacy_requests ORDER BY created_at DESC')];break;
            case 'backup':$result=$s->createBackup();break;
            case 'backup_file':$id=(string)($_GET['id']??'');ensure(preg_match('/^[a-f0-9]{32}$/',$id)===1,'Referencia no válida.');$path=$root.'/.private/backups/'.$id.'.tfbackup';ensure(is_file($path),'Copia no encontrada.',404);$s->transaction(fn()=>$s->audit($s->actor(),'ENCRYPTED_BACKUP_DOWNLOADED',$id));fileResponse(file_get_contents($path),'application/octet-stream','TopFitness-'.$id.'.tfbackup');
            case 'privacy_request':$result=$s->privacyRequest($r);break;
            case 'queue_email':$id=textField($r,'id',32);ensure($s->one('SELECT id FROM contracts WHERE id=?',[$id]),'Contrato no encontrado.');
                if($s->mailEnabled()){$job=$s->transaction(function()use($s,$id){$j=$s->queueContractEmail($id,true);if($j['id'])$s->audit($s->actor(),'EMAIL_QUEUED',$id,['job'=>$j['id']]);return $j;});$result=['state'=>$job['state'],'message'=>'Correo en cola. Se enviará en menos de un minuto.'];break;}
                $s->sql('INSERT INTO email_jobs(id,contract_id,state,created_at) VALUES(?,?,?,?)',[uuid(),$id,'PROVIDER_REQUIRED',instant()]);$s->transaction(fn()=>$s->audit($s->actor(),'EMAIL_PROVIDER_PENDING',$id));$result=['state'=>'PROVIDER_REQUIRED','message'=>'No se ha enviado ningún correo. El envío de correos todavía no está configurado.'];break;
            case 'innux_search':$result=$s->innuxSearchStart($r);break;
            case 'innux_search_result':$result=$s->innuxSearchResult(textField($r,'id',32));break;
            case 'retirement_candidates':$result=['items'=>$s->retirementCandidates($r)];break;
            case 'retirement_list':$result=['items'=>$s->retirementList()];break;
            case 'retirement_request':$result=$s->requestRetirement($r);break;
            case 'retirement_retry':$result=$s->retryRetirement($r);break;
            case 'retirement_cancel':$result=$s->cancelRetirement(textField($r,'id',32));break;
            case 'retirement_archive':$result=$s->retirementArchive(textField($r,'id',32));break;
            case 'retirement_file':$id=(string)($_GET['id']??'');ensure(preg_match('/^[a-f0-9]{32}$/',$id)===1,'Referencia no válida.');fileResponse(jencode($s->retirementArchive($id)),'application/json; charset=utf-8','baja-topfitness-'.$id.'.json');
            case 'begin_holder':$result=$s->beginHolder($r);break;
            case 'holder_sign':$result=$s->signHolder($r);session_regenerate_id(true);$_SESSION['csrf']=uuid();$result['csrf']=$_SESSION['csrf'];break;
            default:throw new AppError('Operación no disponible.',404);
        }
    }
    jsonResponse(['ok'=>true,'data'=>$result]);
}catch(AppError $e){jsonResponse(['ok'=>false,'error'=>$e->getMessage()],$e->status);}
catch(JsonException $e){jsonResponse(['ok'=>false,'error'=>'JSON no válido.'],400);}
catch(PDOException $e){jsonResponse(['ok'=>false,'error'=>str_contains($e->getMessage(),'UNIQUE')?'El registro ya existe o la cuota ya se exportó. No se ha duplicado.':'La operación no pudo completarse. Revisa el estado y vuelve a intentarlo.'],409);}
catch(Throwable $e){error_log('[altas] '.get_class($e).' en '.basename($e->getFile()).':'.$e->getLine());jsonResponse(['ok'=>false,'error'=>'No se pudo completar la operación. No se muestran detalles sensibles.'],500);}
