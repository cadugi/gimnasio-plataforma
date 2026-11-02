"""Demo avanzada optativa y aislada; nunca usa el conector real para sus mutaciones."""
from .transport import Backend
from .portable.portable_flow import PortableFlow
from .portable.store import Store as PortableStore
from .branding import button_appearance


class DemoRouter:
    def __init__(self, config, primary_flow, primary_store, local):
        self.primary,self.store=primary_flow,primary_store
        self.demo_store=PortableStore(local/'demo_multicanal_state.sqlite')
        backend=Backend(config['DEMO_BACKEND_URL'],config['DEMO_BACKEND_SECRET'],portable=True)
        self.demo=PortableFlow(backend,self.demo_store,pilot=False)

    def mode(self,user):
        row=self.store.c.execute('SELECT value FROM metadata WHERE key=?',('channel_mode:'+user,)).fetchone()
        return row[0] if row else 'real'

    def set_mode(self,user,value):
        self.store.c.execute('INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('channel_mode:'+user,value));self.store.c.commit()

    def handle(self,user,text=None,token=None):
        command=(text or '').split(' ',1)[0].split('@',1)[0].lower()
        if command in ('/demo','/real'):
            self.set_mode(user,'demo' if command=='/demo' else 'real');text='/start';token=None
        mode=self.mode(user);store=self.demo_store if mode=='demo' else self.store
        if token:
            saved=store.get_button(token,user)
            if saved and saved[1].get('kind') in ('channel_demo','channel_real'):
                mode='demo' if saved[1]['kind']=='channel_demo' else 'real'
                self.set_mode(user,mode);text='/start';token=None
            elif not saved:
                return self.primary.reply('Este botón pertenece a otro menú o ha caducado. Pulsa /demo para la demo ficticia o /real para tus reservas reales.')
        flow=self.demo if mode=='demo' else self.primary
        reply=flow.handle(user,text=text,token=token)
        if mode=='demo':
            if 'DEMO · Datos ficticios' not in reply['text']:
                reply=dict(reply,text='<b>DEMO · Datos ficticios</b>\n\n'+reply['text'])
            target_store=self.demo_store;label='↩ Volver a reservas reales';kind='channel_real'
        else:
            target_store=self.store;label='🧪 Demo de funciones WhatsApp';kind='channel_demo'
        rows=reply.get('reply_markup',{}).get('inline_keyboard',[])
        if reply.get('attachment'):reply['attachment_scope']=mode
        if not reply.get('attachment') and sum(len(row) for row in rows)<10:
            token=target_store.button(user,target_store.selected(user),{'kind':kind})
            reply['reply_markup']={'inline_keyboard':rows+[[dict(button_appearance(label,{'kind':kind}),callback_data=token)]]}
        return reply

    def refresh_calendar(self,user,reply):
        mode=self.mode(user)
        if reply.get('attachment_scope')!=mode:return self.primary.reply('Este calendario pertenece a otro modo. Abre de nuevo Mi calendario.')
        flow=self.demo if mode=='demo' else self.primary
        return flow.refresh_calendar(user,reply)
