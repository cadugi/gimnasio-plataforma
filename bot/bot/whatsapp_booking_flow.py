"""Adaptador del Flow dinámico de Meta. Las reglas y las escrituras pertenecen al Backend."""
import json
import secrets
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from .transport import Rejected, TemporaryFailure
from .flow import ERRORS
from .branding import date_label

TTL = 900
MAX_CHOICES = 20  # RadioButtonsGroup admite 20 opciones.
WEEKDAYS = ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo')
UNAVAILABLE = 'No hemos podido conectar con el gimnasio. Inténtalo de nuevo en unos segundos.'

SOFT_ERRORS = {'STALE_ACTION': 'La selección ha cambiado. Vuelve a elegir.',
               'INVALID_SELECTION': 'Esa opción no es válida. Elige una de la lista.',
               'CONFIRMATION_REQUIRED': 'Pulsa el botón para confirmar.'}

_locks = {}
_locks_guard = threading.Lock()


def token_lock(token):
    """Serializa las llamadas de un mismo token sin mantener transacciones SQLite abiertas."""
    with _locks_guard:
        if len(_locks) > 512:
            for key in [k for k, v in _locks.items() if not v.locked()][:256]:
                del _locks[key]
        return _locks.setdefault(token, threading.Lock())


def clip(text, size):
    text = ' '.join(str(text).split())
    return text if len(text) <= size else text[:size - 1].rstrip() + '…'


def today():
    return datetime.now(ZoneInfo('Europe/Madrid')).date()


def day_label(value):
    """«Lunes 20-10» y, si procede, «Hoy» o «Mañana» como descripción."""
    try:
        day = datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return clip(value, 30), ''
    delta = (day - today()).days
    note = 'Hoy' if delta == 0 else 'Mañana' if delta == 1 else ''
    return f'{WEEKDAYS[day.weekday()]} {day.day:02d}-{day.month:02d}', note


class BookingFlow:
    def __init__(self, backend, store):
        self.backend, self.store = backend, store
        store.c.execute('''CREATE TABLE IF NOT EXISTS wa_booking_flows(
            token TEXT PRIMARY KEY,user TEXT NOT NULL,expires REAL NOT NULL,
            state TEXT NOT NULL,response TEXT NOT NULL)''')
        store.c.commit()
        self._cache = {}

    # ---- sesión del Flow -------------------------------------------------
    def start(self, user):
        if not self.backend.call(user, action='people')['people']:
            raise Rejected('ACCESS_DENIED')
        token = secrets.token_urlsafe(32)
        self.store.c.execute('DELETE FROM wa_booking_flows WHERE expires<?', (self.store.clock(),))
        self.store.c.execute('INSERT INTO wa_booking_flows VALUES (?,?,?,?,?)',
                             (token, str(user), self.store.clock() + TTL, '{}', '{}'))
        self.store.c.commit()
        return token

    def people(self, user):
        return {str(p['id']): p['nombre'] for p in self.backend.call(user, action='people')['people']}

    def sessions(self, user, person):
        """Sesiones con cupo configurado. Una consulta por persona y petición."""
        if person in self._cache:
            return self._cache[person]
        rows = []
        for day in self.backend.call(user, action='dates', persona_id=int(person))['dates']:
            rows.extend(self.backend.call(user, action='schedules', persona_id=int(person), fecha=day)['schedules'])
        self._cache[person] = [r for r in rows if r['limite'] > 0]
        return self._cache[person]

    # ---- vistas ------------------------------------------------------------
    @staticmethod
    def view(screen, error='', **data):
        base = {'error': error, 'has_error': bool(error), 'error_message': error}
        base.update(data)
        return {'screen': screen, 'data': base}

    def start_view(self, user, people, state, error=''):
        person_default = state.get('person') if state.get('person') in people else next(iter(people))
        activities = state['activities']
        choices = [{'id': str(i), 'title': clip(name, 30)} for i, name in enumerate(activities)]
        if not choices:
            choices = [{'id': 'none', 'title': 'Sin clases disponibles'}]
            error = error or 'Ahora mismo no quedan clases que reservar. Prueba más tarde.'
        multiple = len(people) > 1
        return self.view(
            'START', error, step='1 de 4',
            detail='Elige a quién apuntamos y la actividad.' if multiple else 'Elige la actividad que quieres hacer.',
            people=[{'id': k, 'title': clip(v, 30)} for k, v in people.items()],
            person_default=person_default, show_person=multiple,
            activities=choices, has_choices=bool(activities))

    def days_view(self, state, error=''):
        choices = []
        for value in state['dates'][:MAX_CHOICES]:
            title, note = day_label(value)
            choices.append(dict(id=str(len(choices)), title=title, **({'description': note} if note else {})))
        return self.view('DAY', error, step='2 de 4', detail=clip(state['activity'], 60),
                         days=choices or [{'id': 'none', 'title': 'Sin días disponibles'}], has_choices=bool(choices))

    def slots_view(self, user, state, error=''):
        rows = self.slot_rows(user, state)
        choices = []
        for row in rows[:MAX_CHOICES]:
            wait = row['disponibles'] <= 0
            choices.append({'id': str(row['id']), 'title': clip(row['hora'], 30),
                            'description': 'Completa · entrarás en lista de espera' if wait
                            else (f"{row['disponibles']} plaza libre" if row['disponibles'] == 1 else f"{row['disponibles']} plazas libres")})
        label = ' · '.join(day_label(state['date']))
        label = label.rstrip(' ·')
        if not choices:
            error = error or 'Ya no quedan horarios para este día. Vuelve atrás y elige otro.'
        return self.view('SLOT', error, step='3 de 4', detail=f"{clip(state['activity'], 40)} · {label}",
                         slots=choices or [{'id': 'none', 'title': 'Sin horarios'}], has_choices=bool(choices))

    def slot_rows(self, user, state):
        return sorted((r for r in self.sessions(user, state['person'])
                       if r['clase'] == state['activity'] and r['fecha'] == state['date']),
                      key=lambda r: str(r['hora']))

    def confirm_view(self, people, state, error='', can_confirm=True):
        wait = state['wait']
        title, _ = day_label(state['date'])
        return self.view(
            'CONFIRM', error, step='4 de 4', headline=clip(state['class'], 60),
            when=f"{title} · {state['hour']}", who=people[state['person']],
            note=('La clase está completa. Te apuntamos a la lista de espera y te avisamos si queda una plaza libre.'
                  if wait else 'Tu plaza se confirma en cuanto pulses el botón.'),
            cta='Entrar en lista de espera' if wait else 'Confirmar reserva', can_confirm=can_confirm)

    def done_view(self, token, people, booking):
        waiting = booking['estado'] == 'WAITLIST'
        lines = [booking['clase'], f"{day_label(booking['fecha'])[0]} · {booking['hora']}", booking['nombre']]
        if waiting and booking.get('posicion'):
            lines.append(f"Posición {booking['posicion']} en la lista")
        return self.view('DONE', headline='Estás en la lista de espera' if waiting else 'Reserva confirmada',
                         detail='\n'.join(lines), flow_token=token)

    @staticmethod
    def with_error(previous, message):
        return dict(previous, data=dict(previous['data'], error=message, has_error=True, error_message=message))

    # ---- intercambio -------------------------------------------------------
    def exchange(self, request):
        if request.get('action') == 'ping':
            return {'data': {'status': 'active'}}
        if request.get('version') != '3.0':
            raise Rejected('FLOW_VERSION_INVALID')
        token = request.get('flow_token')
        if not isinstance(token, str):
            raise Rejected('FLOW_EXPIRED')
        with token_lock(token):
            self._cache = {}
            row = self.store.c.execute('SELECT user,expires,state,response FROM wa_booking_flows WHERE token=?',
                                       (token,)).fetchone()
            if not row or row[1] < self.store.clock():
                raise Rejected('FLOW_EXPIRED')
            user, state, previous = row[0], json.loads(row[2]), json.loads(row[3])
            try:
                people = self.people(user)
                if not people:
                    raise Rejected('ACCESS_DENIED')
                response = self.step(request, token, user, people, state, previous)
            except TemporaryFailure:
                if not previous:
                    raise Rejected('SERVICE_UNAVAILABLE') from None
                # Se conserva el estado: reintentar con la misma clave es idempotente.
                return self.with_error(previous, UNAVAILABLE)
            except Rejected as error:
                if error.code not in SOFT_ERRORS or not previous:
                    raise
                return self.with_error(previous, SOFT_ERRORS[error.code])
            self.store.c.execute('UPDATE wa_booking_flows SET state=?,response=? WHERE token=?',
                                 (json.dumps(state), json.dumps(response), token))
            self.store.c.commit()
            return response

    def step(self, request, token, user, people, state, previous):
        action = request.get('action')
        if action == 'INIT':
            if previous:
                return previous
            default = next(iter(people))
            state.clear()
            state.update(person=default,
                         activities=sorted({r['clase'] for r in self.sessions(user, default)}))
            return self.start_view(user, people, state)
        if action == 'BACK':
            return previous or self.step({'action': 'INIT'}, token, user, people, state, previous)
        if action != 'data_exchange':
            raise Rejected('FLOW_ACTION_INVALID')
        if state.get('booking'):
            return previous  # La reserva ya está hecha: un segundo toque no repite nada.
        data = request.get('data', {})
        if not isinstance(data, dict):
            raise Rejected('INVALID_SELECTION')
        screen = request.get('screen')
        # Se puede volver atrás y reenviar cualquier pantalla: cada una rehace todo lo posterior.
        if screen == 'START':
            return self.on_start(user, people, state, data)
        if screen == 'DAY' and state.get('activity'):
            return self.on_day(user, state, data)
        if screen == 'SLOT' and state.get('date'):
            return self.on_slot(user, people, state, data)
        if screen == 'CONFIRM' and state.get('slot'):
            return self.on_confirm(token, user, people, state, data)
        raise Rejected('STALE_ACTION')

    @staticmethod
    def index(value, size):
        if isinstance(value, str) and value.isdigit() and int(value) < size:
            return int(value)
        raise Rejected('INVALID_SELECTION')

    def on_start(self, user, people, state, data):
        person = data.get('person') or (next(iter(people)) if len(people) == 1 else None)
        if person is not None and (not isinstance(person, str) or person not in people):
            raise Rejected('ACCESS_DENIED')
        if person is None:
            return self.start_view(user, people, state, 'Elige primero a quién apuntamos.')
        for key in ('activity', 'date', 'slot', 'wait', 'class', 'hour', 'dates'):
            state.pop(key, None)
        state['person'] = person
        state['activities'] = sorted({r['clase'] for r in self.sessions(user, person)})
        choice = data.get('activity')
        if choice == 'none' or not state['activities']:
            return self.start_view(user, people, state)
        state['activity'] = state['activities'][self.index(choice, len(state['activities']))]
        state['dates'] = sorted({r['fecha'] for r in self.sessions(user, person) if r['clase'] == state['activity']})
        if not state['dates']:
            state.pop('activity')
            return self.start_view(user, people, state, 'Esa actividad ya no tiene horarios disponibles.')
        return self.days_view(state)

    def on_day(self, user, state, data):
        dates = state['dates'][:MAX_CHOICES]
        state['date'] = dates[self.index(data.get('choice'), len(dates))]
        for key in ('slot', 'wait', 'class', 'hour'):
            state.pop(key, None)
        return self.slots_view(user, state)

    def on_slot(self, user, people, state, data):
        choice = data.get('choice')
        row = next((r for r in self.slot_rows(user, state) if str(r['id']) == choice), None)
        if not row:
            state.pop('slot', None)
            return self.slots_view(user, state, 'Ese horario ya no está disponible. Elige otro.')
        state.update(slot=int(row['id']), wait=row['disponibles'] <= 0,
                     **{'class': row['clase'], 'hour': row['hora']})
        return self.confirm_view(people, state)

    def on_confirm(self, token, user, people, state, data):
        if data.get('confirm') is not True:
            raise Rejected('CONFIRMATION_REQUIRED')
        try:
            result = self.backend.call(
                user, action='reserve', persona_id=int(state['person']), horario_id=state['slot'],
                fecha=state['date'], accept_waitlist=state['wait'],
                request_key=f"flow:{token}:{state['person']}:{state['slot']}:{state['date']}:{int(state['wait'])}")
            booking = result['booking']
            if booking['estado'] not in ('RESERVED', 'WAITLIST'):
                raise Rejected('STALE_ACTION')
        except Rejected as error:
            message = ERRORS.get(error.code, 'No hemos podido reservar esta clase. Mira Mis reservas en el chat.')
            return self.confirm_view(people, state, message + ' Vuelve atrás para elegir otro horario.', can_confirm=False)
        state['booking'] = booking
        return self.done_view(token, people, booking)

    def completion(self, user, token):
        row = self.store.c.execute('SELECT state FROM wa_booking_flows WHERE token=? AND user=? AND expires>=?',
                                   (token, str(user), self.store.clock())).fetchone()
        if not row:
            raise Rejected('FLOW_EXPIRED')
        state = json.loads(row[0])
        if not state.get('booking') or state['person'] not in self.people(user):
            raise Rejected('ACCESS_DENIED')
        return state['booking']
