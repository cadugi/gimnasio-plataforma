"""Long polling en el host. Estado y claves solo en .local, fuera del paquete."""
import hmac
import json
import os
import time
from pathlib import Path
from .transport import Backend, Telegram, TemporaryFailure, Rejected
from .store import Store
from .flow import Flow, summary
from .branding import send_reply

ROOT = Path(__file__).resolve().parents[1]


def atomic_json(path, value):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,indent=2),encoding='utf-8')
    os.replace(temp,path)


class Runner:
    def __init__(self, config, auth_file, invite_file, store, telegram, backend):
        self.config,self.auth_file,self.invite_file=config,auth_file,invite_file
        self.store,self.telegram,self.backend=store,telegram,backend
        self.flow=Flow(backend,store,pilot=config.get('PILOT_MODE',False))
        self.demo_router=None
        if config.get('PORTABLE_DEMO_ENABLED'):
            from .demo_router import DemoRouter
            self.demo_router=DemoRouter(config,self.flow,store,ROOT/'.local')

    def users(self):
        return json.loads(self.auth_file.read_text(encoding='utf-8'))

    def envelope(self, update):
        cb=update.get('callback_query')
        message=(cb or {}).get('message') if cb else update.get('message')
        sender=(cb or message or {}).get('from',{})
        chat=(message or {}).get('chat',{})
        uid=sender.get('id')
        if not isinstance(uid,int) or uid<=0 or sender.get('is_bot') or chat.get('type')!='private' or chat.get('id')!=uid:
            return None
        return str(uid),cb,message

    def pair(self,user,message):
        # Possession of the one-use invitation is the demo owner's explicit authorization.
        # No discovery by username or phone and no automatic registration of unknown visitors.
        if self.config.get('PILOT_MODE') or not self.invite_file.is_file():
            return False
        invite=json.loads(self.invite_file.read_text(encoding='utf-8'))
        text=message.get('text','')
        if invite.get('used') or invite['expires']<time.time() or not isinstance(text,str):
            return False
        if not hmac.compare_digest(text,'/start '+invite['code']):
            return False
        users=self.users();users[user]=[1,2]
        # Consume first: a crash cannot leave the invitation reusable for another private chat.
        invite['used']=True;atomic_json(self.invite_file,invite)
        atomic_json(self.auth_file,users)
        return True

    def process(self,update):
        update_id=update.get('update_id')
        if not isinstance(update_id,int):
            return
        envelope=self.envelope(update)
        if not envelope:
            self.store.save_reply(update_id,'ignored',{});self.store.sent(update_id);return
        user,cb,message=envelope
        if user not in self.users() and not (not cb and self.pair(user,message)):
            # Unknown users get no catalogue or unsolicited replies.
            self.store.save_reply(update_id,'ignored',{});self.store.sent(update_id);return
        saved=self.store.reply(update_id)
        if saved and saved[1]:
            return
        if saved:
            reply=saved[0]
            if reply.get('attachment'):reply=(self.demo_router or self.flow).refresh_calendar(user,reply)
        else:
            conversation=self.demo_router or self.flow
            reply=conversation.handle(user,text=message.get('text') if not cb else None,token=cb.get('data') if cb else None)
            self.store.save_reply(update_id,user,reply)
        if cb:
            try:self.telegram.call('answerCallbackQuery',callback_query_id=cb['id'])
            except (Rejected,TemporaryFailure):pass
        welcome = not cb and str(message.get('text', '')).split(' ', 1)[0].split('@', 1)[0] in ('/start','/demo','/real')
        send_reply(self.telegram, user, reply, welcome=welcome)
        self.store.sent(update_id)

    def notifications(self):
        for user,ids in self.users().items():
            if not user.isdigit():
                continue
            events=self.backend.call(user,action='outbox_claim')['events']
            for event in events:
                payload=event['payload'];delivery='PENDING'
                try:
                    if payload['persona_id'] not in self.users().get(user,[]):
                        delivery='SUPPRESSED'
                    else:
                        current=self.backend.call(user,action='list',persona_id=payload['persona_id'])['bookings']
                        if not any(b['id']==payload['id'] and b['version']==payload['version'] and b['estado']=='RESERVED' for b in current):
                            delivery='SUPPRESSED'
                        else:
                            self.telegram.call('sendMessage',chat_id=int(user),text='Ya tienes plaza.\n'+summary(payload))
                            delivery='SENT'
                except Rejected:
                    delivery='FAILED'
                except TemporaryFailure:
                    delivery='PENDING'
                self.backend.call(user,action='outbox_ack',event_id=event['id'],lease=event['lease'],delivery=delivery)


def main():
    local=ROOT/'.local';config=json.loads((local/'config.json').read_text(encoding='utf-8'))
    if not config.get('TELEGRAM_TOKEN'):
        raise SystemExit('Configura el token local. Las pruebas simuladas no lo necesitan.')
    # One host polling process only; OS-level lock is released even after a crash.
    lock=open(local/'bot.lock','a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    if os.name=='nt':
        import msvcrt
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit('Ya hay un bot de la demo en ejecución.') from None
    else:
        import fcntl
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise SystemExit('Ya hay un bot de la demo en ejecución.') from None
    telegram=Telegram(config['TELEGRAM_TOKEN']);backend=Backend(config['BACKEND_URL'],config['BACKEND_SECRET'])
    try:
        identity=telegram.call('getMe')
        atomic_json(local/'telegram_identity.json',{'username':identity['username'],'id':identity['id']})
        if telegram.call('getWebhookInfo').get('url'):
            raise SystemExit('El bot tiene un webhook. No se ha alterado. Retíralo expresamente antes de usar polling.')
        telegram.call('setMyCommands',commands=[{'command':'demo','description':'?? Demo WhatsApp ? Datos ficticios'},{'command':'real','description':'Reservas reales ? Piloto autorizado'},{'command':'start','description':'🟢 Inicio · Reservas TopFitness'},{'command':'ayuda','description':'❔ Cómo reservar y gestionar tus clases'}])
    except (TemporaryFailure,Rejected):
        raise SystemExit('Telegram no está disponible o la clave no es válida. No se muestran detalles secretos.') from None
    pilot=config.get('PILOT_MODE',False)
    auth_file=local/'access'/('production_users.json' if pilot else 'allowed_users.json')
    state_file=local/('bot_production_state.sqlite' if pilot else 'bot_state.sqlite')
    runner=Runner(config,auth_file,local/'invite.json',Store(state_file),telegram,backend)
    print(('Bot de prueba en producción: @' if pilot else 'Bot de demostración en marcha: @')+identity['username']+'. Ctrl+C para parar solo este proceso.')
    while True:
        try:
            runner.notifications()
            updates=telegram.call('getUpdates',offset=runner.store.offset(),timeout=20,allowed_updates=['message','callback_query'])
            for update in updates:runner.process(update)
        except TemporaryFailure:
            print('Conexión temporalmente no disponible; reintento sin perder la operación.')
            time.sleep(3)
        except Rejected as e:
            if e.code in ('TELEGRAM_401','TELEGRAM_409'):
                raise SystemExit('Clave rechazada o existe otro proceso de polling. No se ha alterado ningún servicio.') from None
            print('Operación rechazada; revisa acceso o estado del bot.')
            time.sleep(3)
        except KeyboardInterrupt:
            print('Bot de demo detenido.');return
        except Exception:
            # Avoid traceback URLs, payloads or accidental secret disclosure from unexpected failures.
            print('Error interno recuperable. Se conserva la operación pendiente para reintentar.')
            time.sleep(3)


if __name__=='__main__':
    main()
