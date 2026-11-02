"""Presentación de WhatsApp sobre el motor compartido, sin duplicar reservas."""
import html
from datetime import date
import re
import unicodedata
from .portable.portable_flow import PortableFlow
from .transport import Rejected, TemporaryFailure
from .whatsapp import button_title, limited, units
from .portable.branding import date_label
from .whatsapp_booking_flow import today


HEADER = re.compile(r'^🟢 <b>TOPFITNESS</b>\n\n(?:<b>PRUEBA EN PRODUCCIÓN · Plazas reales</b>\n\n)?')
WELCOME_EVERY = 12 * 3600
GREETINGS = ('hola', 'buenas', 'buenos dias', 'buenas tardes', 'buenas noches', 'menu', 'inicio', 'empezar', '/start')

FRIENDLY_ERRORS = {
    'WAITLIST_CONFIRMATION_REQUIRED': 'La clase se ha llenado mientras decidías. Vuelve a elegir la hora: podrás apuntarte a la lista de espera.',
    'DATE_OUTSIDE_WINDOW': 'Solo puedes reservar desde hoy hasta 5 días por delante.',
    'SESSION_CLOSED': 'Esa clase ya no admite reservas. Elige otra, por favor.',
    'SESSION_STARTED': 'Esa clase ya ha empezado. Elige otra, por favor.',
    'STALE_ACTION': 'Esa reserva ha cambiado desde que abriste el mensaje. Consulta tus reservas para ver cómo está ahora.',
}


def sort_time(value):
    return [int(n) for n in re.findall(r'\d+', str(value))]


class WhatsAppMenuFlow(PortableFlow):
    """Presentación de WhatsApp: solo mensajes interactivos, sin etiquetas técnicas ni de demo."""
    def button(self, user, person, text, **action):
        return dict(super().button(user,person,text,**action),text=text)

    def reply(self, text, buttons=(), layout=None):
        # Un botón de respuesta admite 20 caracteres: si un título se cortaría, se usa lista.
        if layout is None and any(units(b['text']) > 20 and button_title(b['text']) == limited(b['text'], 20) for b in buttons):
            layout = 'list'
        reply = super().reply(text, buttons, layout)
        reply = dict(reply, text=HEADER.sub('', reply['text'], count=1))
        if layout == 'list':
            reply['whatsapp_list'] = True
        return reply

    # ---- piezas de texto -------------------------------------------------
    WEEKDAYS = ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo')

    @staticmethod
    def _note(value):
        try:
            delta = (date.fromisoformat(value) - today()).days
        except (ValueError, TypeError):
            return ''
        return {0: 'Hoy', 1: 'Mañana'}.get(delta, '')

    def _day(self, value):
        """«Lunes 19 de octubre (hoy)»."""
        try:
            weekday = self.WEEKDAYS[date.fromisoformat(value).weekday()]
        except (ValueError, TypeError):
            return str(value)
        note = self._note(value)
        return f'{weekday} {date_label(value)}' + (f' ({note.lower()})' if note else '')

    def _card(self, b):
        text = f"{b['clase']}\n📅 {self._day(b['fecha'])} · {str(b['hora'])[:5]}\n👤 {b['nombre']}"
        if b.get('estado') == 'WAITLIST' and b.get('posicion'):
            text += f"\n⏳ Posición {b['posicion']} en la lista de espera"
        return text

    def _next_class(self, user, person):
        try:
            bookings = self.backend.call(user, action='list', persona_id=person)['bookings']
        except (Rejected, TemporaryFailure):
            return None
        today_ = today().isoformat()
        coming = sorted((b for b in bookings if b['estado'] == 'RESERVED' and b['fecha'] >= today_),
                        key=lambda b: (b['fecha'], sort_time(b['hora'])))
        return f"{coming[0]['clase']} · {self._day(coming[0]['fecha'])} · {str(coming[0]['hora'])[:5]}" if coming else None

    def _nav(self, user, person, *extra):
        return list(extra) + [self._back(user, person)]

    # ---- pantallas ---------------------------------------------------------
    def people(self, user):
        people = self.backend.call(user, action='people')['people']
        if len(people) == 1:
            p = people[0]
            self.store.select(user, int(p['id']))
            return self.menu(user, int(p['id']), p['nombre'])
        return self.reply('¿Para quién quieres reservar?',
                          [self.button(user, p['id'], p['nombre'], kind='person') for p in people], layout='list')

    def menu(self, user, person, name):
        nxt = self._next_class(user, person)
        text = f'Hola, {name} 👋\n\n' + (f'Tu próxima clase:\n{nxt}' if nxt else 'Aún no tienes clases reservadas.') + '\n\n¿Qué quieres hacer?'
        return self.reply(text, [
            self.button(user, person, label, kind=kind) for label, kind in (
                ('Reservar clase', 'dates'), ('Reservar en la web', 'wa_web'), ('Mis reservas', 'reserved'),
                ('Lista de espera', 'waiting'), ('Ver horario', 'wa_schedule'), ('Más opciones', 'wa_more'))], layout='list')

    def _day_picker(self, user, person):
        dates = self.backend.call(user, action='dates', persona_id=person)['dates']
        if not dates:
            return self.reply('Ahora mismo no hay días abiertos para reservar. Inténtalo más tarde.', [self._back(user, person)])
        buttons = []
        for fecha in dates:
            weekday = self.WEEKDAYS[date.fromisoformat(fecha).weekday()]
            label = ' · '.join(x for x in (date_label(fecha), weekday, self._note(fecha)) if x)
            buttons.append(self.button(user, person, label, kind='wa_day', fecha=fecha))
        return self.reply('¿Qué día quieres entrenar?', buttons + [self._back(user, person)], layout='list')

    def _day_sessions(self, user, person, fecha, part=None):
        """Todas las clases del día en una sola lista (la lista admite 10 filas: si hay más, mañana/tarde)."""
        rows = sorted((r for r in self.backend.call(user, action='schedules', persona_id=person, fecha=fecha)['schedules']
                       if r['limite'] > 0), key=lambda r: sort_time(r['hora']))
        days = self.button(user, person, 'Cambiar día', kind='dates')
        if not rows:
            return self.reply(f'{self._day(fecha)}\nNo hay clases ese día.', [days, self._back(user, person)])
        morning = [r for r in rows if sort_time(r['hora'])[0] < 14]
        evening = [r for r in rows if sort_time(r['hora'])[0] >= 14]
        if part is None and len(rows) > 8 and morning and evening:
            return self.reply(f'{self._day(fecha)}\nHay {len(rows)} clases. ¿Mañana o tarde?', [
                self.button(user, person, f'Mañana ({len(morning)})', kind='wa_day', fecha=fecha, part='morning'),
                self.button(user, person, f'Tarde ({len(evening)})', kind='wa_day', fecha=fecha, part='evening'),
                days])
        if part:
            rows = morning if part == 'morning' else evening
        buttons = []
        for r in rows:
            free = r['disponibles']
            note = 'completa, lista de espera' if free <= 0 else (f'{free} plazas' if free != 1 else '1 plaza')
            buttons.append(self.button(user, person, f"{str(r['hora'])[:5]} {r['clase']} · {note}", kind='wa_session',
                                       fecha=fecha, horario_id=r['id']))
        head = self._day(fecha) + ('' if not part else (' · mañana' if part == 'morning' else ' · tarde'))
        nav = [days, self._back(user, person)] if len(buttons) <= 8 else [self._back(user, person)]  # la lista admite 10 filas
        return self.reply(f'{head}\nElige la clase para reservar o entrar en la lista de espera.', buttons + nav, layout='list')

    def _review(self, user, person, name, action):
        hs = self.backend.call(user, action='schedules', persona_id=person, fecha=action['fecha'])['schedules']
        h = next((h for h in hs if h['id'] == action['horario_id'] and h['limite'] > 0), None)
        if not h:
            raise Rejected('SESSION_CLOSED')
        wait = h['disponibles'] <= 0
        head = f"{h['clase']}\n📅 {self._day(h['fecha'])} · {str(h['hora'])[:5]}\n"
        if wait:
            body = head + '\n⚠️ Esta clase está completa.\nPuedes apuntarte a la lista de espera: no tendrás plaza asegurada hasta que se libere una.\n\n¿Quieres entrar?'
        else:
            n = h['disponibles']
            body = head + ('Queda 1 plaza.' if n == 1 else f'Quedan {n} plazas.') + f'\n\n¿Confirmas la reserva para {name}?'
        return self.reply(body, [
            self.button(user, person, 'Entrar en espera' if wait else 'Confirmar reserva', kind='confirm_reserve',
                        fecha=h['fecha'], horario_id=h['id'], accept_waitlist=wait),
            self.button(user, person, 'Cambiar clase', kind='wa_day', fecha=h['fecha']),
            self._back(user, person)])

    def _after_buttons(self, user, person, again='dates', again_label='Reservar otra'):
        return [self.button(user, person, 'Mis reservas', kind='reserved'),
                self.button(user, person, again_label, kind=again),
                self._back(user, person)]

    def _reserve(self, user, person, action, token):
        r = self.backend.call(user, action='reserve', persona_id=person, horario_id=action['horario_id'], fecha=action['fecha'],
                              accept_waitlist=action['accept_waitlist'], request_key='button:' + token)
        b = r['booking']
        if b['estado'] == 'OFFERED':
            return self.offer_reply(user, b)
        head = '✅ ¡Reserva confirmada!' if b['estado'] == 'RESERVED' else '⏳ Te hemos apuntado a la lista de espera'
        tail = '\n\nTe esperamos.' if b['estado'] == 'RESERVED' else '\n\nPuedes ver tu posición en Lista de espera.'
        return self.reply(head + '\n\n' + self._card(b) + tail, self._after_buttons(user, person))

    def _my_bookings(self, user, person, kind):
        wanted = ('RESERVED',) if kind == 'reserved' else ('WAITLIST', 'OFFERED')
        bs = sorted((b for b in self.backend.call(user, action='list', persona_id=person)['bookings'] if b['estado'] in wanted),
                    key=lambda b: (b['fecha'], sort_time(b['hora'])))
        if not bs:
            text = 'No tienes clases reservadas.' if kind == 'reserved' else 'No estás en ninguna lista de espera.'
            return self.reply(text, [self.button(user, person, 'Reservar clase', kind='dates'), self._back(user, person)])
        buttons = []
        for b in bs:
            label = f"{b['clase']} · {self._day(b['fecha'])} · {str(b['hora'])[:5]}"
            if b['estado'] == 'OFFERED':
                buttons.append(self.button(user, person, 'Plaza ofrecida · ' + label, kind='show_offer', offer_id=b['offer_id']))
            else:
                buttons.append(self.button(user, person, label, kind='wa_booking', booking_id=b['id'], version=b['version'], expected=b['estado']))
        text = ('Tus reservas' if kind == 'reserved' else 'Tu lista de espera') + '\nToca una para verla o cancelarla.'
        return self.reply(text, buttons + [self._back(user, person)], layout='list')

    def _find(self, user, person, action):
        b = next((b for b in self.backend.call(user, action='list', persona_id=person)['bookings']
                  if b['id'] == action['booking_id'] and b['version'] == action['version'] and b['estado'] == action['expected']), None)
        if not b:
            raise Rejected('STALE_ACTION')
        return b

    def _booking(self, user, person, action):
        b = self._find(user, person, action)
        waiting = b['estado'] != 'RESERVED'
        return self.reply(self._card(b), [
            self.button(user, person, 'Salir de la espera' if waiting else 'Cancelar reserva', kind='review_cancel',
                        booking_id=b['id'], version=b['version'], expected=b['estado']),
            self.button(user, person, 'Volver', kind='waiting' if waiting else 'reserved'),
            self._back(user, person)])

    def _review_cancel(self, user, person, action):
        b = self._find(user, person, action)
        waiting = b['estado'] != 'RESERVED'
        ask = '¿Seguro que quieres salir de la lista de espera?' if waiting else '¿Seguro que quieres cancelar esta reserva?\nLiberarás tu plaza.'
        return self.reply(ask + '\n\n' + self._card(b), [
            self.button(user, person, 'Sí, salir' if waiting else 'Sí, cancelar', kind='confirm_cancel',
                        booking_id=b['id'], version=b['version'], expected=b['estado']),
            self.button(user, person, 'No, quedarme' if waiting else 'No, mantenerla', kind='waiting' if waiting else 'reserved'),
            self._back(user, person)])

    def _confirm_cancel(self, user, person, action, token):
        waiting = action['expected'] != 'RESERVED'
        self.backend.call(user, action='leave_waitlist' if waiting else 'cancel', persona_id=person,
                          booking_id=action['booking_id'], version=action['version'], request_key='button:' + token)
        text = 'Has salido de la lista de espera.' if waiting else 'Reserva cancelada. Tu plaza ha quedado libre.'
        return self.reply('✅ ' + text, [self.button(user, person, 'Reservar clase', kind='dates'),
                                         self.button(user, person, 'Mis reservas', kind='reserved'), self._back(user, person)])

    def _schedule(self, user, person):
        reply = self.reply('Horario de clases de TopFitness 🗓\n\nPara apuntarte, pulsa «Reservar clase».',
                           [self.button(user, person, 'Reservar clase', kind='dates'), self._back(user, person)])
        return dict(reply, attachment={'kind': 'static_image', 'name': 'horario'})

    def _help(self, user, person):
        text = ('Así funciona\n\n1. Pulsa «Reservar clase» y elige el día.\n2. Verás todas las clases de ese día: elige una.\n3. Confirma y te mandamos el resumen.\n\n'
                'Si una clase está completa, puedes apuntarte a la lista de espera.\n\n'
                'Límites: 10 clases por persona y semana (de lunes a domingo; cuentan las realizadas y las esperas, no las canceladas). '
                'Puedes reservar hasta 5 días por delante, con un máximo de 3 clases al día y 5 futuras por teléfono.')
        if self.portable:
            text += '\n\nTambién puedes escribirme, por ejemplo: «Quiero yoga mañana por la tarde».'
        return self.reply(text, [self.button(user, person, 'Reservar clase', kind='dates'), self._back(user, person)])

    def _human(self, user, person):
        if self.handoff and self.handoff.available:
            return super()._human(user, person)
        return self.reply('Ahora mismo no puedo ponerte en contacto con recepción desde este chat. Puedes gestionar tus clases con los botones.',
                          [self._back(user, person)])

    def _error(self, user, person, error):
        if error.code in FRIENDLY_ERRORS:
            text = FRIENDLY_ERRORS[error.code]
        else:
            text = html.unescape(super()._error(user, person, error)['text'])
        return self.reply(text, [self.button(user, person, 'Reservar clase', kind='dates'),
                                 self.button(user, person, 'Mis reservas', kind='reserved'), self._back(user, person)])

    def _page(self, user, person, action):
        items, page = action['items'], action['page']
        start = page * 8
        buttons = items[start:start + 8]
        if page:
            buttons.append(self.button(user, person, '‹ Anterior', kind='portable_page', items=items, page=page - 1, body=action['body']))
        if start + 8 < len(items):
            buttons.append(self.button(user, person, 'Más opciones ›', kind='portable_page', items=items, page=page + 1, body=action['body']))
        return self.reply(action['body'], buttons, layout='list')

    def _valid(self, user, token):
        """Acción guardada solo si la persona sigue autorizada y es la seleccionada."""
        saved = self.store.get_button(token, user) if token else None
        if not saved:
            return None
        person, action = saved
        names = {int(p['id']): p['nombre'] for p in self.backend.call(user, action='people')['people']}
        if person not in names or person != self.store.selected(user):
            return None
        return person, action, names[person]

    def _dispatch(self, user, person, name, action, token):
        kind = action['kind']
        if kind == 'dates': return self._day_picker(user, person)
        if kind == 'wa_day': return self._day_sessions(user, person, action['fecha'], action.get('part'))
        if kind in ('review', 'wa_session'): return self._review(user, person, name, action)
        if kind == 'confirm_reserve': return self._reserve(user, person, action, token)
        if kind in ('reserved', 'waiting'): return self._my_bookings(user, person, kind)
        if kind == 'wa_booking': return self._booking(user, person, action)
        if kind == 'review_cancel': return self._review_cancel(user, person, action)
        if kind == 'confirm_cancel': return self._confirm_cancel(user, person, action, token)
        if kind == 'portable_page': return self._page(user, person, action)
        if kind == 'help': return self._help(user, person)
        if kind == 'wa_schedule': return self._schedule(user, person)
        if kind == 'portable_human': return self._human(user, person)
        return None

    def _more(self, user, person):
        people = self.backend.call(user, action='people')
        options = [('Ayuda', 'help'), ('Mi calendario', 'calendar')]
        if len(people['people']) > 1: options.append(('Cambiar persona', 'people'))
        if self.handoff and self.handoff.available: options.append(('Hablar con empleado', 'portable_human'))
        if people.get('notifications_enabled'): options.append(('Notificaciones', 'notifications'))
        options.append(('Volver al menú', 'menu'))
        return self.reply('Más opciones', [self.button(user, person, label, kind=kind) for label, kind in options], layout='list')

    def handle(self, user, text=None, token=None):
        self._principal = user
        saved=self.store.get_button(token,user) if token else None
        if saved and saved[1].get('kind')=='wa_web':
            response=self.backend.call(user,action='people')
            if saved[0]!=self.store.selected(user) or saved[0] not in {int(p['id']) for p in response['people']}:
                return self.reply('La persona ha cambiado. Escribe «menú».')
            return dict(self.reply('Abre tu agenda de clases. El enlace es personal, de un solo uso y válido durante 5 minutos.'),
                        whatsapp_web_access={'user':str(user),'person':saved[0]})
        if saved and saved[1].get('kind')=='wa_classic_booking':
            return super().handle(user,token=self.store.button(user,saved[0],{'kind':'dates'}))
        if self.native_booking and saved and saved[1].get('kind')=='dates':
            response=self.backend.call(user,action='people')
            if saved[0]!=self.store.selected(user) or saved[0] not in {int(p['id']) for p in response['people']}:
                return self.reply('La persona ha cambiado. Escribe «menú».')
            if self.flow_blocked():return self.native_unavailable(user)
            flow_id,service=self.native_booking
            return dict(self.reply('Elige actividad, día y hora. Son cuatro pasos.'),
                        whatsapp_native_flow={'id':flow_id,'token':service.start(user),
                                              'mode':self.native_booking_mode})
        if saved:
            valid = self._valid(user, token)
            if valid:
                person, action, name = valid
                try:
                    if action['kind'] == 'wa_more': return self._more(user, person)
                    reply = self._dispatch(user, person, name, action, token)
                except Rejected as error:
                    return self._error(user, person, error)
                if reply is not None: return reply
            elif saved[1].get('kind') == 'wa_more':
                return self.reply('La persona ha cambiado o ya no está autorizada. Escribe «menú».')
        return super().handle(user,text=text,token=token)

    FLOW_RETRY_SECONDS=900

    def flow_blocked(self):
        """Meta rechazó el Flow hace poco. El bloqueo caduca para volver a probar cuando se active."""
        row=self.store.c.execute("SELECT value FROM metadata WHERE key='wa_flow_blocked'").fetchone()
        try:return bool(row) and 0<=self.store.clock()-float(row[0])<self.FLOW_RETRY_SECONDS
        except ValueError:return False  # Valor antiguo «1»: se vuelve a intentar.

    def native_unavailable(self,user):
        person=self.store.selected(user)
        return self.reply('El formulario de reserva no está disponible ahora.\nPuedes reservar por chat sin perder nada.',[
            self.button(user,person,'Reservar por chat',kind='wa_classic_booking'),
            self.button(user,person,'Volver al menú',kind='menu')])

    native_booking = None
    native_booking_mode = 'published'


def normalized(text):
    value=''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^\w\s/]',' ',value).split())


class WhatsAppFlow:
    def __init__(self, flow):
        self.flow=flow
        self.store=flow.store

    def reply(self,*args,**kwargs):
        return self.flow.reply(*args,**kwargs)

    def native_unavailable(self,user):
        self.store.c.execute("INSERT INTO metadata VALUES ('wa_flow_blocked',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(self.store.clock()),))
        self.store.c.commit()
        return self.flow.native_unavailable(user)

    def _welcome_due(self,user):
        """La imagen de bienvenida se manda al saludar, como mucho una vez cada 12 horas."""
        key='wa_welcome:'+str(user)
        row=self.store.c.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
        now=self.store.clock()
        try:
            if row and 0<=now-float(row[0])<WELCOME_EVERY:return False
        except ValueError:pass
        self.store.c.execute('INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(now)))
        self.store.c.commit()
        return True

    def handle(self,user,text=None,token=None):
        person=self.store.selected(user)
        greeting=False
        if token and not self.store.get_button(token,user):
            reply=self.flow.handle(user,text='/start')
            reply=dict(reply,text='Este botón ha caducado. Abre una opción nueva para continuar.\n\n'+reply['text'])
        else:
            if text:
                clean=normalized(text)
                if clean in ('cambiar persona','otra persona','/persona'):
                    text='/persona'
                elif clean in GREETINGS:
                    greeting=True
                    if person is not None:
                        token=self.flow.button(user,person,'Menú',kind='menu')['callback_data']
                        text=None
                    else:
                        text='/start'
                elif person is not None:
                    shortcuts={'reservar':'dates','reservar clase':'dates','reservar clases':'dates','horarios':'dates',
                               'mis reservas':'reserved','cancelar':'reserved','cancelar reserva':'reserved',
                               'lista de espera':'waiting','mas opciones':'wa_more','ayuda':'help','/ayuda':'help',
                               'web':'wa_web','reservar en la web':'wa_web','reservar por web':'wa_web'}
                    if clean in shortcuts:
                        token=self.flow.button(user,person,'Continuar',kind=shortcuts[clean])['callback_data']
                        text=None
            reply=self.flow.handle(user,text=text,token=token)
        # Los botones y las comprobaciones de autorización siguen siendo del motor común.
        reply=dict(reply,text=reply['text'].replace('/start','«menú»').replace('/persona','«cambiar persona»'))
        if greeting and self._welcome_due(user):reply['whatsapp_welcome_image']=True
        return reply
