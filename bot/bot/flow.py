"""Servicio de conversación independiente del transporte Telegram."""
from .calendar_export import CalendarMenu
from .transport import Rejected, TemporaryFailure
from .branding import message, button_appearance, date_label, display_dates

ERRORS = {
    'WEEKLY_PERSON_LIMIT': 'Has alcanzado las 10 clases de esta semana. Las clases realizadas y la espera también cuentan; las canceladas no.',
    'IDENTITY_REVIEW_REQUIRED': 'Hay reservas anteriores pendientes de vincular a tu ficha. Recepción debe revisarlas antes de añadir más.',
    'CALENDAR_UNAVAILABLE': 'No se puede consultar el calendario ahora. Vuelve a abrir Mis reservas.',
    'CALENDAR_TOO_LARGE': 'Hay demasiadas reservas para esta exportación. Consulta Mis reservas o contacta con recepción.',
    'CALENDAR_IMAGE_UNAVAILABLE': 'No se pudo generar la imagen. Puedes descargar el calendario o volver a consultar tus reservas.',
    'ACCESS_DENIED': 'No tienes permiso para esta persona u operación.',
    'SESSION_CLOSED': 'Esta sesión está cerrada.',
    'SESSION_STARTED': 'La clase ya ha comenzado. Elige otra sesión.',
    'STALE_ACTION': 'La reserva ha cambiado. Consulta de nuevo Mis reservas.',
    'WAITLIST_CONFIRMATION_REQUIRED': 'La clase se ha llenado. Vuelve a elegirla y confirma si quieres esperar.',
    'DATE_OUTSIDE_WINDOW': 'Solo puedes reservar desde hoy hasta cinco días en adelante.',
    'DAILY_PHONE_LIMIT': 'Límite: 3 clases al día por teléfono. Cancela alguna para reservar otra.',
    'FUTURE_PHONE_LIMIT': 'Límite: 5 clases futuras por teléfono. Cancela alguna o espera a que pase una clase.',
    'ROUTINE_DAY_LIMIT': 'Límite: 3 horarios por día semanal y teléfono.',
    'ROUTINE_PHONE_LIMIT': 'Límite: 5 horarios semanales por teléfono. Quita uno para añadir otro.',
    'PHONE_REQUIRED': 'Necesitamos un teléfono válido asociado a tu ficha. Contacta con recepción.',
    'INVALID_DATE': 'La fecha no es válida.',
    'WRONG_WEEKDAY': 'Esta clase no corresponde a ese día.',
    'LEGACY_WAITLIST_CONFLICT': 'La aplicación ya tiene una entrada en espera con este número para ese horario. Esta prueba no la modificará. Elige otra sesión.',
    'OFFER_EXPIRED': 'El plazo de esta oferta ha terminado. La plaza se ofrece a la siguiente persona. Puedes volver a apuntarte a la espera.',
    'FEATURE_DISABLED': 'Esta función está preparada pero todavía no está activada.',
}


def summary(b):
    state = {'RESERVED': 'Reserva confirmada', 'WAITLIST': 'En lista de espera', 'CANCELLED': 'Cancelada'}[b['estado']]
    text = f"{b['nombre']}\n{b['clase']} · {date_label(b['fecha'])}\nHora: {b['hora']}\n{state}"
    if b.get('posicion'):
        text += f" · Posición {b['posicion']}"
    return display_dates(text)


class Flow(CalendarMenu):
    def __init__(self, backend, store, pilot=False):
        self.backend, self.store = backend, store
        self.pilot = pilot

    def button(self, user, person, text, **action):
        return dict(button_appearance(text, action), callback_data=self.store.button(user, person, action))

    def reply(self, text, buttons=(), layout=None):
        return message(text, buttons, self.pilot, layout)

    def people(self, user):
        people = self.backend.call(user, action='people')['people']
        if self.pilot and len(people)==1:
            p=people[0];self.store.select(user,int(p['id']))
            return self.menu(user,int(p['id']),p['nombre'])
        return self.reply('DEMO · Datos inventados.\n¿Para quién quieres reservar?', [self.button(user, p['id'], p['nombre'], kind='person') for p in people])

    def menu(self, user, person, name):
        return self.reply(('' if self.pilot else 'DEMO · ')+'👤 '+name+'\n\nElige tu próximo entrenamiento o gestiona tus reservas.\n\nHasta 5 días de antelación · 3 clases al día · 5 futuras por teléfono. Reservas y esperas cuentan juntas.', [self.button(user, person, title, kind=kind) for title, kind in [
            ('Reservar clase','dates'),('Mis reservas','reserved'),('Lista de espera','waiting'),('Cambiar persona','people'),('Ayuda','help'),('Mi calendario','calendar')]], layout='menu')

    def handle(self, user, text=None, token=None):
        try:
            people = self.backend.call(user, action='people')['people']
            allowed = {int(p['id']):p['nombre'] for p in people}
            person = self.store.selected(user)
            if text and text.startswith('/start') or text == '/persona':
                return self.people(user)
            if token:
                saved = self.store.get_button(token,user)
                if not saved:
                    return self.reply('Este botón ha caducado. Pulsa /start para continuar.')
                p, action = saved
                if p not in allowed:
                    return self.reply('Esta persona ya no está autorizada. Pulsa /start.')
                if action['kind']=='person':
                    self.store.select(user,p)
                    return self.menu(user,p,allowed[p])
                if p!=person:
                    return self.reply('Has cambiado de persona. Usa el menú actual o pulsa /start.')
            else:
                if text and text!='/ayuda' and person in allowed:
                    return self.reply('Perdona, no te he entendido. Usa los botones o abre Ayuda.',[self.button(user,person,'Reservar clase',kind='dates'),self.button(user,person,'Men?',kind='menu'),self.button(user,person,'Ayuda',kind='help')])
                action={'kind':'help' if text == '/ayuda' else 'menu'}
            if person not in allowed:
                return self.people(user)
            name=allowed[person]
            kind=action['kind']
            if kind in ('calendar','calendar_ics','calendar_image'):
                return self.calendar_view(user,person,name,kind,action.get('week'))
            if kind in ('menu','back'):
                return self.menu(user,person,name)
            if kind=='people':
                return self.people(user)
            if kind=='help':
                note='Estas reservas ocupan plazas reales y aparecen marcadas BORRAR PRUEBA. Solo puedes gestionar tus registros de prueba. Al cancelar puede obtener plaza una persona de la espera real.' if self.pilot else 'Esto es una demo: no verifica tu identidad real.'
                return self.reply(name+'\nElige una fecha y una clase. Después confirma.\nPuedes consultar o cancelar tus reservas y salir de la espera.\nHasta hoy + 5 días. Máximo 3 clases al día y 5 futuras por teléfono, contando reservas y esperas de sus personas.\n'+note,[self.button(user,person,'Volver al menú',kind='menu')])
            if kind=='dates':
                dates=self.backend.call(user,action='dates',persona_id=person)['dates']
                return self.reply(name+'\nElige un día:',[self.button(user,person,d,kind='schedules',fecha=d) for d in dates]+[self.button(user,person,'Volver',kind='menu')], layout='dates')
            if kind=='schedules':
                hs=self.backend.call(user,action='schedules',persona_id=person,fecha=action['fecha'])['schedules']
                choices=[self.button(user,person,f"{h['clase']} · {h['hora']} · {str(h['disponibles'])+' plazas' if h['disponibles'] else 'En espera'}",kind='review',fecha=h['fecha'],horario_id=h['id']) for h in hs if h['limite']>0]
                return self.reply(name+'\n'+action['fecha']+'\nElige una clase:' if choices else name+'\nNo hay sesiones disponibles en esa fecha.',choices+[self.button(user,person,'Cambiar día',kind='dates')])
            if kind=='review':
                hs=self.backend.call(user,action='schedules',persona_id=person,fecha=action['fecha'])['schedules']
                h=next((h for h in hs if h['id']==action['horario_id']),None)
                if not h or h['limite']<=0:
                    return self.reply('Esta sesión ya no está disponible. Pulsa /start.')
                wait=h['disponibles']==0
                description='Entrar en lista de espera' if wait else 'Reservar plaza'
                return self.reply(f"{name}\n{h['clase']} · {h['fecha']}\nHora: {h['hora']}\n{h['disponibles']} plazas disponibles\n¿Confirmas {description.lower()}?",[self.button(user,person,'Sí, '+description.lower(),kind='confirm_reserve',fecha=h['fecha'],horario_id=h['id'],accept_waitlist=wait),self.button(user,person,'No, volver',kind='menu')])
            if kind=='confirm_reserve':
                r=self.backend.call(user,action='reserve',persona_id=person,horario_id=action['horario_id'],fecha=action['fecha'],accept_waitlist=action['accept_waitlist'],request_key='button:'+token)
                return self.reply(summary(r['booking']),[self.button(user,person,'Volver al menú',kind='menu')])
            if kind in ('reserved','waiting'):
                bs=self.backend.call(user,action='list',persona_id=person)['bookings']
                state='RESERVED' if kind=='reserved' else 'WAITLIST'
                bs=[b for b in bs if b['estado']==state]
                labels=[summary(b) for b in bs]
                buttons=[self.button(user,person,('Cancelar' if state=='RESERVED' else 'Salir de espera')+f" · {b['clase']} · {date_label(b['fecha'])} · {b['hora']}",kind='review_cancel',booking_id=b['id'],version=b['version'],expected=state) for b in bs]
                return self.reply('\n\n'.join(labels) if labels else name+'\nNo tienes '+('reservas.' if kind=='reserved' else 'entradas en espera.'),buttons+[self.button(user,person,'Volver al menú',kind='menu')])
            if kind=='review_cancel':
                bs=self.backend.call(user,action='list',persona_id=person)['bookings']
                b=next((b for b in bs if b['id']==action['booking_id'] and b['version']==action['version'] and b['estado']==action['expected']),None)
                if not b:
                    return self.reply('Esta reserva ha cambiado. Pulsa /start para consultarla.')
                verb='cancelar la reserva' if b['estado']=='RESERVED' else 'salir de la lista de espera'
                return self.reply(summary(b)+'\n¿Confirmas '+verb+'?',[self.button(user,person,'Sí, '+verb,kind='confirm_cancel',booking_id=b['id'],version=b['version'],expected=b['estado']),self.button(user,person,'No, volver',kind='menu')])
            if kind=='confirm_cancel':
                r=self.backend.call(user,action='cancel' if action['expected']=='RESERVED' else 'leave_waitlist',persona_id=person,booking_id=action['booking_id'],version=action['version'],request_key='button:'+token)
                return self.reply(summary(r['booking']),[self.button(user,person,'Volver al menú',kind='menu')])
            return self.reply('Opción no válida. Pulsa /start.')
        except Rejected as e:
            return self.reply(ERRORS.get(e.code,'No se puede realizar esta operación. Pulsa /start para volver a consultar.'))
        # TemporaryFailure deliberately escapes: don't consume a mutation callback or advance the offset until retry.
