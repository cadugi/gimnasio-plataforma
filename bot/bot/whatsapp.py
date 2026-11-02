"""Adaptador Cloud API: mismo Flow, contrato conservador y envío desactivado por defecto."""
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import hmac
import json
import re
import time
import urllib.request
import urllib.error
from .transport import TemporaryFailure, Rejected
from .calendar_export import attachment_bytes
from .flow import summary


class _Text(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.parts=[]
    def handle_data(self,data): self.parts.append(data)


def plain(reply):
    parser=_Text();parser.feed(reply['text']);return ''.join(parser.parts)


def units(text): return len(text.encode('utf-16-le'))//2


def limited(text, maximum):
    result=[];size=0
    for char in text:
        width=units(char)
        if size+width>maximum:break
        result.append(char);size+=width
    return ''.join(result)


def button_title(text):
    aliases={'Sí, reservar plaza':'Confirmar reserva','Sí, entrar en lista de espera':'Entrar en espera',
             'Sí, cancelar la reserva':'Cancelar reserva','Sí, salir de la lista de espera':'Salir de la espera',
             'No, volver':'Volver'}
    return limited(aliases.get(text,text),20)


def whatsapp_payload(recipient, reply):
    payload=_whatsapp_payload(recipient,reply)
    # La bienvenida lleva una imagen previa; se sube y se envía al entregar, no se guarda en la cola.
    return dict(payload,__tf_welcome_image=True) if reply.get('whatsapp_welcome_image') else payload


def _whatsapp_payload(recipient, reply):
    if reply.get('attachment'):raise ValueError('Usa WhatsAppPolicy para preparar archivos e imágenes')
    if not re.fullmatch(r'[1-9][0-9]{6,18}',str(recipient)): raise ValueError('Destinatario no válido')
    body=plain(reply)
    if units(body)>1024: raise ValueError('La vista común supera el límite portable de 1024 caracteres')
    buttons=[b for row in reply.get('reply_markup',{}).get('inline_keyboard',[]) for b in row]
    result={'messaging_product':'whatsapp','recipient_type':'individual','to':str(recipient)}
    if reply.get('whatsapp_reservations_cta'):
        from .whatsapp_welcome import RESERVATIONS_URL
        return dict(result,type='interactive',interactive={
            'type':'cta_url','body':{'text':body},'action':{'name':'cta_url',
            'parameters':{'display_text':'Reservar clases','url':RESERVATIONS_URL}}})
    if reply.get('whatsapp_web_access'):
        # Persist only the intent. Mint the bearer link in memory at delivery time.
        return dict(result,type='interactive',__tf_web_access=reply['whatsapp_web_access'],interactive={
            'type':'cta_url','body':{'text':body},'action':{'name':'cta_url','parameters':{'display_text':'Reservar clases','url':'https://whatsapp.gimnasio.example/reservas/'}}})
    if reply.get('whatsapp_native_flow'):
        flow=reply['whatsapp_native_flow']
        if not re.fullmatch(r'[0-9]+',flow['id']):raise ValueError('Flow ID no válido')
        mode=flow.get('mode','published')
        if mode not in ('draft','published'):raise ValueError('Flow mode no válido')
        return dict(result,type='interactive',interactive={'type':'flow','body':{'text':body},'action':{
            'name':'flow','parameters':{'flow_message_version':'3','flow_id':flow['id'],
            'flow_token':flow['token'],'flow_cta':'Reservar clase','flow_action':'data_exchange','mode':mode}}})
    if not buttons: return dict(result,type='text',text={'body':body})
    if len(buttons)>10: raise ValueError('La vista debe paginar antes de superar 10 opciones')
    for b in buttons:
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',b['callback_data']): raise ValueError('Identificador de acción no válido')
    if len(buttons)<=3 and not reply.get('whatsapp_list'):
        titles=[button_title(b['text']) for b in buttons]
        if len(set(titles))<len(titles):titles=[limited(f'{i+1}. '+b['text'],20) for i,b in enumerate(buttons)]
        choices=[{'type':'reply','reply':{'id':b['callback_data'],'title':titles[i]}} for i,b in enumerate(buttons)]
        interactive={'type':'button','body':{'text':body},'action':{'buttons':choices}}
    else:
        rows=[{'id':b['callback_data'],'title':limited(f'{i+1}. '+b['text'].split(' · ')[0],24),'description':limited(b['text'],72)} for i,b in enumerate(buttons)]
        interactive={'type':'list','body':{'text':body},'action':{'button':'Ver opciones','sections':[{'title':'TopFitness','rows':rows}]}}
    return dict(result,type='interactive',interactive=interactive)


@dataclass(frozen=True)
class DeliveryDecision:
    allowed: bool
    reason: str
    payload: dict | None = None
    attachment: dict | None = None


class WhatsAppPolicy:
    def __init__(self, approved_templates=None, clock=time.time, calendar_downloads=None):
        # Manifest is account-specific and must be filled only after approval by Meta.
        self.templates=approved_templates or {};self.clock=clock
        self.calendar_downloads=calendar_downloads

    def prepare(self, recipient, reply, last_inbound, consent, event=None):
        if not re.fullmatch(r'[1-9][0-9]{6,18}',str(recipient)): return DeliveryDecision(False,'INVALID_RECIPIENT')
        category='weekly' if event in ('WEEKLY_SUMMARY','ROUTINE_PLAN') else ('reminders' if event in ('REMINDER_24H','REMINDER_1H') else 'service')
        if consent.get(category) is not True: return DeliveryDecision(False,'CONSENT_REQUIRED')
        delta=self.clock()-last_inbound
        if last_inbound>0 and 0<=delta<86400:
            attachment=reply.get('attachment')
            if attachment:
                clean={k:v for k,v in reply.items() if k not in ('attachment','attachment_scope')}
                if event:return DeliveryDecision(False,'CALENDAR_USER_REQUEST_REQUIRED')
                if attachment['kind']=='calendar_ics':
                    if self.calendar_downloads is None:return DeliveryDecision(False,'CALENDAR_DOWNLOAD_SERVICE_REQUIRED')
                    from .calendar_export import calendar_bytes
                    try:link=self.calendar_downloads.publish(calendar_bytes(attachment['snapshot']))
                    except (ValueError,OSError):return DeliveryDecision(False,'CALENDAR_DOWNLOAD_UNAVAILABLE')
                    # URL is plain HTTPS, not a spoofed supported document MIME type.
                    return DeliveryDecision(True,'SESSION_CALENDAR_LINK',whatsapp_payload(recipient,dict(clean,text=clean['text']+'\n\nDescarga privada (15 minutos):\n'+link)))
                if attachment['kind'] not in ('calendar_image','static_image'):return DeliveryDecision(False,'UNSUPPORTED_ATTACHMENT')
                payload=whatsapp_payload(recipient,clean)
                if payload['type']=='interactive' and payload['interactive']['type']!='button':return DeliveryDecision(False,'MEDIA_BUTTON_LIMIT')
                return DeliveryDecision(True,'SESSION_CALENDAR_IMAGE' if attachment['kind']=='calendar_image' else 'SESSION_STATIC_IMAGE',payload,attachment)
            return DeliveryDecision(True,'SESSION',whatsapp_payload(recipient,reply))
        if reply.get('whatsapp_reservations_cta'):
            return DeliveryDecision(False,'APPROVED_URL_TEMPLATE_REQUIRED')
        if reply.get('attachment'):return DeliveryDecision(False,'CALENDAR_USER_REQUEST_REQUIRED')
        spec=self.templates.get(event or 'SESSION_REOPEN')
        if not spec or spec.get('approved') is not True or not spec.get('name') or not spec.get('language'):
            return DeliveryDecision(False,'APPROVED_TEMPLATE_REQUIRED')
        # Restrict templates to one body parameter containing the view's current text.
        # Buttons carry the original opaque callbacks, never an unverified booking/person ID.
        text=' '.join(plain(reply).split())
        if units(text)>1024: return DeliveryDecision(False,'TEMPLATE_TEXT_TOO_LONG')
        components=[{'type':'body','parameters':[{'type':'text','text':text}]}]
        buttons=[b for row in reply.get('reply_markup',{}).get('inline_keyboard',[]) for b in row]
        if len(buttons)!=int(spec.get('quick_replies',0)): return DeliveryDecision(False,'TEMPLATE_BUTTONS_MISMATCH')
        for i,b in enumerate(buttons):
            components.append({'type':'button','sub_type':'quick_reply','index':str(i),'parameters':[{'type':'payload','payload':b['callback_data']}]})
        payload={'messaging_product':'whatsapp','to':str(recipient),'type':'template','template':{'name':spec['name'],'language':{'code':spec['language']},'components':components}}
        return DeliveryDecision(True,'APPROVED_TEMPLATE',payload)


class WhatsAppGateway:
    """Signed inbound conversion and durable deduplication; no network sends here."""
    def __init__(self, flow, store, directory, app_secret, phone_number_id, clock=time.time, status_handler=None, handoff=None, guest_flow=None):
        if not app_secret or not phone_number_id: raise ValueError('Falta configuración privada de Meta')
        self.flow,self.store,self.directory=flow,store,directory
        self.secret,self.phone_number_id,self.clock=app_secret,phone_number_id,clock
        self.status_handler=status_handler
        # Números fuera del directorio: solo reciben el enlace público a la web, nunca acceso a reservas.
        self.guest_flow=guest_flow
        self.handoff=handoff
        if handoff is not None:self.flow.handoff=handoff
        self.store.c.executescript('''
          CREATE TABLE IF NOT EXISTS whatsapp_inbox(id TEXT PRIMARY KEY,principal TEXT NOT NULL,reply TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS whatsapp_claims(id TEXT PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS whatsapp_sessions(recipient TEXT PRIMARY KEY,last_inbound REAL NOT NULL,unsubscribed INTEGER NOT NULL DEFAULT 0);
        ''')

    def verify_challenge(self, query, verify_token):
        if not verify_token or query.get('hub.mode')!='subscribe' or not hmac.compare_digest(query.get('hub.verify_token',''),verify_token): raise Rejected('WEBHOOK_VERIFICATION_FAILED')
        return query.get('hub.challenge','')

    def accept(self, raw, signature):
        if len(raw)>65536: raise Rejected('WEBHOOK_TOO_LARGE')
        expected='sha256='+hmac.new(self.secret.encode(),raw,sha256).hexdigest()
        if not hmac.compare_digest(expected,signature or ''): raise Rejected('WEBHOOK_SIGNATURE_INVALID')
        try: envelope=json.loads(raw)
        except (ValueError,UnicodeError): raise Rejected('WEBHOOK_INVALID') from None
        if not isinstance(envelope,dict) or envelope.get('object')!='whatsapp_business_account': raise Rejected('WEBHOOK_INVALID')
        results=[]
        for entry in envelope.get('entry',[]):
            for change in entry.get('changes',[]):
                value=change.get('value',{})
                if change.get('field')!='messages' or str(value.get('metadata',{}).get('phone_number_id'))!=self.phone_number_id: continue
                if self.status_handler:
                    for status in value.get('statuses',[]):self.status_handler(status)
                for msg in value.get('messages',[]):
                    recipient=msg.get('from','');identity=self.directory.get(recipient);guest=False
                    if not identity or not identity.get('principal'):
                        if self.guest_flow is None or not re.fullmatch(r'[1-9][0-9]{6,18}',str(recipient)): continue
                        identity={'principal':recipient,'consent':{'service':True}};guest=True
                    principal=str(identity['principal']);message_id=msg.get('id','')
                    if not isinstance(message_id,str) or not 1<=len(message_id)<=200: continue
                    previous=self.store.c.execute('SELECT principal,reply FROM whatsapp_inbox WHERE id=?',(message_id,)).fetchone()
                    if previous:
                        if previous[0]==principal:
                            paused=self.handoff and self.handoff.active(principal)
                            results.append({'recipient':recipient,'reply':None if paused else json.loads(previous[1]),'duplicate':True})
                        continue
                    try: stamp=int(msg.get('timestamp',0))
                    except (ValueError,TypeError): continue
                    if stamp<=0 or stamp>self.clock()+300: continue
                    # The Flow also rechecks backend authorization for every callback.
                    text=None;token=None
                    native_completion=None
                    if msg.get('type')=='text': text=msg.get('text',{}).get('body','')
                    elif msg.get('type')=='interactive':
                        interactive=msg.get('interactive',{});kind=interactive.get('type')
                        if kind in ('button_reply','list_reply'): token=interactive.get(kind,{}).get('id')
                        elif kind=='nfm_reply':
                            try:
                                data=json.loads(interactive.get('nfm_reply',{}).get('response_json',''))
                                native_completion=data.get('flow_token') if isinstance(data,dict) else None
                            except (ValueError,TypeError):continue
                    elif msg.get('type')=='button': token=msg.get('button',{}).get('payload')
                    elif msg.get('type') in ('audio','image','video','document','sticker','location','contacts','unknown'):
                        text='__unsupported_media__'
                    else: continue  # Los eventos del sistema no son peticiones del usuario.
                    if not isinstance(text or token or native_completion,str): continue
                    # Claim before any backend effect. A crash/ambiguous response requires
                    # review instead of replaying a reservation from another envelope.
                    claim=self.store.c.execute('INSERT OR IGNORE INTO whatsapp_claims VALUES (?)',(message_id,))
                    self.store.c.commit()
                    if not claim.rowcount:
                        results.append({'recipient':recipient,'reply':None,'duplicate':True})
                        continue
                    if guest:
                        reply=self.guest_flow.handle_inbound(principal,stamp,text=text,token=token)
                        unsubscribed=None
                    elif getattr(self.flow,'reservation_landing',False):
                        reply=self.flow.handle_inbound(principal,stamp,text=text,token=token)
                        unsubscribed=1 if text and text.strip().casefold() in ('baja','stop','parar avisos') else None
                    elif native_completion:
                        native=getattr(getattr(self.flow,'flow',None),'native_booking',None)
                        if not native or (self.handoff and self.handoff.active(principal)):reply=None
                        else:
                            try:
                                booking=native[1].completion(principal,native_completion)
                                person=self.store.selected(principal)
                                reply=self.flow.reply(summary(booking),[
                                    self.flow.button(principal,person,'Mis reservas',kind='reserved'),
                                    self.flow.button(principal,person,'Reservar otra',kind='dates'),
                                    self.flow.button(principal,person,'Menú',kind='menu')]) if person is not None else self.flow.reply(summary(booking))
                            except Rejected:reply=self.flow.reply('No se pudo verificar la reserva. Abre Mis reservas.')
                        unsubscribed=None
                    elif text and text.strip().casefold() in ('baja','stop','parar avisos'):
                        reply=self.flow.reply('Has dado de baja los avisos por WhatsApp. Puedes seguir consultando y gestionando tus clases desde el menú.')
                        unsubscribed=1
                    elif self.handoff and self.handoff.active(principal):
                        unsubscribed=None
                        saved=self.store.get_button(token,principal) if token else None
                        resume_text=text and text.strip().casefold() in ('volver al bot','volver al asistente','/bot')
                        resume_button=saved and saved[1].get('kind')=='portable_human_resume'
                        if resume_text:
                            self.handoff.resume(principal)
                            reply=self.flow.handle(principal,text='/start')
                        elif resume_button:
                            reply=self.flow.handle(principal,token=token)
                        else:
                            reply=None  # The employee reads this message in the coexisting Business app.
                    elif text=='__unsupported_media__':
                        reply=self.flow.reply('Por ahora puedo ayudarte con texto y botones. No he interpretado el archivo o audio.\n\nEscribe «menú» para ver tus opciones o, por ejemplo, «Quiero Pilates mañana».');unsubscribed=None
                    else:
                        reply=self.flow.handle(principal,text=text,token=token);unsubscribed=None
                    self.store.c.execute('INSERT INTO whatsapp_sessions(recipient,last_inbound,unsubscribed) VALUES (?,?,?) ON CONFLICT(recipient) DO UPDATE SET last_inbound=MAX(last_inbound,excluded.last_inbound),unsubscribed=COALESCE(?,unsubscribed)',(recipient,stamp,unsubscribed or 0,unsubscribed))
                    self.store.c.execute('INSERT INTO whatsapp_inbox VALUES (?,?,?)',(message_id,principal,json.dumps(reply)))
                    self.store.c.commit()
                    results.append({'recipient':recipient,'reply':reply,'duplicate':False})
        return results

    def decision(self, recipient, reply, policy, event=None):
        identity=self.directory.get(recipient) or ({'principal':recipient,'consent':{'service':True}} if self.guest_flow is not None else {})
        session=self.store.c.execute('SELECT last_inbound,unsubscribed FROM whatsapp_sessions WHERE recipient=?',(recipient,)).fetchone()
        consent=dict(identity.get('consent',{}))
        # A reply to the user remains possible after opt-out; proactive events stay suppressed.
        if event and session and session[1]: return DeliveryDecision(False,'UNSUBSCRIBED')
        if reply is None or (event and self.handoff and self.handoff.active(str(identity.get('principal','')))):
            return DeliveryDecision(False,'HUMAN_HANDOFF')
        return policy.prepare(recipient,reply,session[0] if session else 0,consent,event)


class WhatsAppTransport:
    def __init__(self, token, phone_number_id, api_version, enabled=False):
        if not token or not re.fullmatch(r'\d+',phone_number_id) or not re.fullmatch(r'v\d+\.\d+',api_version): raise ValueError('Falta configuración válida de Cloud API')
        self._token,self._phone,self._version,self.enabled=token,phone_number_id,api_version,enabled is True

    def send(self, decision):
        if not self.enabled: raise Rejected('WHATSAPP_NOT_ENABLED')
        if not decision.allowed or not decision.payload: raise Rejected(decision.reason)
        payload=json.loads(json.dumps(decision.payload))
        if '__tf_web_access' in payload:
            intent=payload.pop('__tf_web_access')
            backend=getattr(self,'web_backend',None)
            if backend is None:raise Rejected('WEB_ACCESS_UNAVAILABLE')
            link=backend.call(intent['user'],action='web_link',persona_id=int(intent['person']))['url']
            if not re.fullmatch(r'https://whatsapp\.topfitness\.es/reservas/entrar\.php\?t=[a-f0-9]{64}',link):raise Rejected('WEB_ACCESS_UNAVAILABLE')
            payload['interactive']['action']['parameters']['url']=link
        if decision.attachment:
            from .branding import ROOT
            filename,mime,content=attachment_bytes(decision.attachment,ROOT)
            if mime!='image/png' or len(content)>5*1024*1024:raise Rejected('UNSUPPORTED_ATTACHMENT')
            media=self._upload_image(filename,content)
            payload=json.loads(json.dumps(payload))
            if payload['type']=='interactive':payload['interactive']['header']={'type':'image','image':{'id':media}}
            else:
                payload={'messaging_product':'whatsapp','to':payload['to'],'type':'image','image':{'id':media,'caption':payload['text']['body']}}
        welcome=payload.pop('__tf_welcome_image',False)
        if welcome:
            try:self._welcome_image(payload['to'])
            except (Rejected,TemporaryFailure,OSError) as error:  # La imagen es decoración: nunca bloquea el menú.
                print('Imagen de bienvenida no enviada:',getattr(error,'code',type(error).__name__),flush=True)
        result=self._post(payload)
        return result  # Accepted by Meta; delivery must still be verified using status webhooks.

    def _post(self,payload):
        url='https://graph.facebook.com/'+self._version+'/'+self._phone+'/messages'
        request=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+self._token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=20) as response: result=json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (400,401,403,404):
                code='WHATSAPP_REJECTED'
                try:
                    detail=json.loads(error.read(16384)).get('error',{})
                    number=detail.get('code')
                    if isinstance(number,int) and 0<number<10000000:code+='_'+str(number)
                except (ValueError,OSError,AttributeError):pass
                raise Rejected(code) from None
            raise TemporaryFailure('WHATSAPP_TEMPORARY') from None
        except (OSError,ValueError): raise TemporaryFailure('WHATSAPP_TEMPORARY') from None
        return result

    def _welcome_image(self,to):
        from .branding import ROOT
        content=(ROOT/'assets'/'topfitness-bienvenida.png').read_bytes()
        if len(content)>5*1024*1024:return
        media=self._upload_image('topfitness-bienvenida.png',content)
        self._post({'messaging_product':'whatsapp','recipient_type':'individual','to':to,'type':'image','image':{'id':media}})

    def _upload_image(self,filename,content):
        import uuid
        boundary='topfitness-'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="messaging_product"\r\n\r\nwhatsapp\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        url='https://graph.facebook.com/'+self._version+'/'+self._phone+'/media'
        req=urllib.request.Request(url,data=body,headers={'Authorization':'Bearer '+self._token,'Content-Type':'multipart/form-data; boundary='+boundary})
        try:
            with urllib.request.urlopen(req,timeout=25) as response:result=json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (400,401,403):raise Rejected('WHATSAPP_MEDIA_REJECTED') from None
            raise TemporaryFailure('WHATSAPP_MEDIA_TEMPORARY') from None
        except (OSError,ValueError):raise TemporaryFailure('WHATSAPP_MEDIA_TEMPORARY') from None
        if not re.fullmatch(r'[0-9]+',str(result.get('id',''))):raise Rejected('WHATSAPP_MEDIA_REJECTED')
        return str(result['id'])


class DeliveryTracker:
    """An HTTP 200 from Meta is not a delivery receipt, especially for expiring offers."""
    def __init__(self, store, backend):
        self.store,self.backend=store,backend
        store.c.execute('''CREATE TABLE IF NOT EXISTS whatsapp_deliveries(
          id TEXT PRIMARY KEY,principal TEXT NOT NULL,recipient TEXT NOT NULL,
          event_id INTEGER NOT NULL,lease TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL)''')
        store.c.commit()

    def accepted(self, meta_message_id, principal, recipient, event, kind='BOOKING'):
        if kind not in ('BOOKING','ASSISTANT'):raise ValueError('Tipo de evento no válido')
        self.store.c.execute('INSERT OR IGNORE INTO whatsapp_deliveries VALUES (?,?,?,?,?,?,?)',(meta_message_id,principal,recipient,event['id'],event['lease'],kind,'ACCEPTED'))
        self.store.c.commit()

    def status(self, payload):
        row=self.store.c.execute('SELECT principal,recipient,event_id,lease,kind,state FROM whatsapp_deliveries WHERE id=?',(payload.get('id',''),)).fetchone()
        if not row or str(payload.get('recipient_id',''))!=row[1] or row[5]=='DELIVERED':return
        state=payload.get('status')
        if state not in ('delivered','read','failed'):return
        delivery='SENT' if state in ('delivered','read') else 'PENDING'
        self.backend.call(row[0],action='outbox_ack' if row[4]=='BOOKING' else 'assistant_ack',event_id=row[2],lease=row[3],delivery=delivery)
        self.store.c.execute('UPDATE whatsapp_deliveries SET state=? WHERE id=?',('DELIVERED' if delivery=='SENT' else 'FAILED',payload['id']))
        self.store.c.commit()
