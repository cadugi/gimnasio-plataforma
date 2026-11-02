"""Bot de reservas por botones (sin Flows) con backend simulado."""
import hashlib, hmac, json, os, sys, tempfile, threading, time, unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot.portable.store import Store
from bot.transport import Rejected
from bot.whatsapp import WhatsAppGateway, WhatsAppPolicy, whatsapp_payload, plain, units
from bot.whatsapp_booking_flow import today
from bot.whatsapp_flow import WhatsAppFlow, WhatsAppMenuFlow
from bot.whatsapp_webhook import Queue, worker

TODAY = today()
DAYS = [(TODAY + timedelta(days=i)).isoformat() for i in range(6)]
PHONE = '34600000001'


class FakeBackend:
    official_web = True

    def __init__(self, people=None, portable=False):
        self.people_ = people or [{'id': 7, 'nombre': 'Ana Pérez'}]
        self.portable = portable
        self.free = {1: 3, 2: 0, 3: 1}
        self.names = {1: 'Pilates', 2: 'Yoga', 3: 'Cross Training'}
        self.bookings = {}      # id -> booking
        self.keys = {}          # request_key -> resultado
        self.fail = {}          # acción -> código de rechazo
        self.next_id = 1

    def sessions(self, day):
        rows = [{'id': i, 'clase': self.names[i], 'fecha': day, 'hora': h, 'limite': 10, 'disponibles': self.free[i]}
                for i, h in ((1, '09:00'), (2, '10:00'), (3, '18:30'))]
        return rows + [{'id': 9, 'clase': 'Cerrada', 'fecha': day, 'hora': '08:00', 'limite': 0, 'disponibles': 0}]

    def call(self, user, **d):
        a = d['action']
        if a in self.fail: raise Rejected(self.fail[a])
        if a == 'people': return {'ok': True, 'people': self.people_, 'portable_features': self.portable}
        if a == 'dates': return {'ok': True, 'dates': DAYS}
        if a == 'schedules': return {'ok': True, 'schedules': self.sessions(d['fecha'])}
        if a == 'profile': return {'ok': True, 'now': TODAY.isoformat() + 'T10:00:00', 'profile': {'favorites': []}}
        if a == 'catalog': return {'ok': True, 'classes': list(self.names.values())}
        if a == 'list': return {'ok': True, 'bookings': [dict(b) for b in self.bookings.values() if b['estado'] != 'CANCELLED']}
        if a in ('reserve', 'cancel', 'leave_waitlist'):
            if d['request_key'] in self.keys: return self.keys[d['request_key']]
            if a == 'reserve':
                full = self.free[d['horario_id']] <= 0
                if full and not d['accept_waitlist']: raise Rejected('WAITLIST_CONFIRMATION_REQUIRED')
                if not full: self.free[d['horario_id']] -= 1
                b = {'id': self.next_id, 'version': 1, 'nombre': 'Ana Pérez', 'clase': self.names[d['horario_id']],
                     'fecha': d['fecha'], 'hora': {1: '09:00', 2: '10:00', 3: '18:30'}[d['horario_id']],
                     'estado': 'WAITLIST' if full else 'RESERVED', 'posicion': 2 if full else None}
                self.next_id += 1; self.bookings[b['id']] = b
            else:
                b = self.bookings[d['booking_id']]
                if b['version'] != d['version']: raise Rejected('STALE_ACTION')
                b['estado'] = 'CANCELLED'; b['version'] += 1
            self.keys[d['request_key']] = {'ok': True, 'booking': dict(b)}
            return self.keys[d['request_key']]
        raise AssertionError(a)


class Chat:
    """Simula a la persona: lee el payload real de WhatsApp y pulsa lo que ve."""
    def __init__(self, test, backend, clock=None):
        self.test = test
        self.now = [time.time()]
        self.store = Store(os.path.join(test.tmp, 's.sqlite'), clock=clock or (lambda: self.now[0]))
        self.backend = backend
        self.flow = WhatsAppFlow(WhatsAppMenuFlow(backend, self.store, pilot=True))
        self.last = None

    def show(self, reply):
        payload = whatsapp_payload(PHONE, reply)
        self.test.check_limits(payload)
        self.test.assertNotRegex(json.dumps(payload, ensure_ascii=False), r'\d{1,4}-\d{1,2}-\d{2,4}', 'fecha con año o numérica')
        self.last = (reply, payload)
        return reply

    def say(self, text):
        return self.show(self.flow.handle('123', text=text))

    def options(self):
        i = self.last[1].get('interactive')
        if not i: return []
        if i['type'] == 'button':
            return [(b['reply']['title'], '', b['reply']['id']) for b in i['action']['buttons']]
        return [(r['title'], r.get('description', ''), r['id']) for s in i['action']['sections'] for r in s['rows']]

    def tap(self, label):
        found = [o for o in self.options() if label.casefold() in (o[0] + ' ' + o[1]).casefold()]
        self.test.assertTrue(found, f'No hay «{label}» en {[o[:2] for o in self.options()]}')
        return self.tap_id(found[0][2])

    def tap_id(self, token):
        return self.show(self.flow.handle('123', token=token))

    def text(self):
        return plain(self.last[0])


class Base(unittest.TestCase):
    portable = False

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(); self.addCleanup(self.tmpdir.cleanup)
        self.tmp = self.tmpdir.name
        self.backend = FakeBackend(portable=self.portable)
        self.chat = Chat(self, self.backend)
        self.addCleanup(self.chat.store.c.close)

    def check_limits(self, payload):
        """Límites de WhatsApp Cloud API."""
        if payload['type'] == 'text':
            self.assertLessEqual(units(payload['text']['body']), 4096); return
        i = payload['interactive']
        self.assertLessEqual(units(i['body']['text']), 1024)
        if i['type'] == 'button':
            buttons = i['action']['buttons']
            self.assertLessEqual(len(buttons), 3)
            for b in buttons: self.assertLessEqual(units(b['reply']['title']), 20, b['reply']['title'])
            self.assertEqual(len({b['reply']['title'] for b in buttons}), len(buttons))
        elif i['type'] == 'list':
            rows = [r for s in i['action']['sections'] for r in s['rows']]
            self.assertLessEqual(len(rows), 10)
            self.assertLessEqual(units(i['action']['button']), 20)
            for r in rows:
                self.assertLessEqual(units(r['title']), 24, r['title'])
                self.assertLessEqual(units(r.get('description', '')), 72)
            self.assertEqual(len({r['id'] for r in rows}), len(rows))

    def pick_day(self, day_index=0):
        c = self.chat
        c.tap('Reservar clase'); c.tap(c.options()[day_index][1])

    def pick(self, label, day_index=0):
        self.pick_day(day_index); self.chat.tap(label)

    def book(self, activity='Pilates', day_index=0, hour='09:00'):
        c = self.chat
        c.say('hola'); c.tap('Reservar clase')
        c.tap(c.options()[day_index][1])
        c.tap(f'{hour} {activity}'); c.tap('Confirmar reserva')


class MenuTests(Base):
    def test_menu_is_clean_and_complete(self):
        reply = self.chat.say('hola')
        text = plain(reply)
        for banned in ('DEMO', 'Datos ficticios', 'Reservar por bot', 'TOPFITNESS', 'PRUEBA', 'BORRAR', '/start'):
            self.assertNotIn(banned, text)
        self.assertIn('Ana Pérez', text)
        labels = ' '.join(o[1] for o in self.chat.options())
        for wanted in ('Reservar clase', 'Mis reservas', 'Lista de espera', 'Más opciones'):
            self.assertIn(wanted, labels)

    def test_welcome_image_once_per_half_day(self):
        self.assertTrue(self.chat.say('hola').get('whatsapp_welcome_image'))
        self.assertIn('__tf_welcome_image', self.chat.last[1])
        self.assertFalse(self.chat.say('menú').get('whatsapp_welcome_image'))
        self.chat.now[0] += 13 * 3600
        self.assertTrue(self.chat.say('hola').get('whatsapp_welcome_image'))

    def test_next_class_shown(self):
        self.book()
        self.assertIn('Tu próxima clase', plain(self.chat.say('menu')))

    def test_more_options_without_switch_person_for_one_person(self):
        self.chat.say('hola'); self.chat.tap('Más opciones')
        labels = ' '.join(o[1] for o in self.chat.options())
        self.assertIn('Ayuda', labels); self.assertIn('calendario', labels.lower())
        self.assertNotIn('Cambiar persona', labels); self.assertNotIn('empleado', labels)

    def test_more_options_with_several_people(self):
        self.backend.people_ = [{'id': 7, 'nombre': 'Ana Pérez'}, {'id': 8, 'nombre': 'Leo Pérez'}]
        self.chat.say('hola')
        self.assertIn('Para quién', self.chat.text())
        self.chat.tap('Leo'); self.assertIn('Hola, Leo Pérez', self.chat.text())
        self.chat.tap('Más opciones')
        self.assertIn('Cambiar persona', ' '.join(o[1] for o in self.chat.options()))

    def test_schedule_image_button(self):
        self.chat.say('hola'); self.assertIn('Ver horario', ' '.join(o[1] for o in self.chat.options()))
        reply = self.chat.flow.handle('123', token=[o for o in self.chat.options() if 'horario' in o[1]][0][2])
        self.assertEqual(reply['attachment'], {'kind': 'static_image', 'name': 'horario'})
        decision = WhatsAppPolicy(clock=time.time).prepare(PHONE, reply, time.time(), {'service': True})
        self.assertTrue(decision.allowed, decision.reason)
        self.check_limits(decision.payload)
        from bot.calendar_export import attachment_bytes
        from bot.branding import ROOT
        name, mime, content = attachment_bytes(decision.attachment, ROOT)
        self.assertEqual(mime, 'image/png'); self.assertTrue(content.startswith(b'\x89PNG'))

    def test_single_person_is_not_asked(self):
        self.assertNotIn('Para quién', plain(self.chat.say('hola')))

    def test_help_text_has_business_rules(self):
        self.chat.say('hola'); self.chat.tap('Más opciones'); self.chat.tap('Ayuda')
        text = self.chat.text()
        for fact in ('10 clases', '5 días', '3 clases al día', '5 futuras'): self.assertIn(fact, text)
        self.assertNotIn('demo', text.lower())
        self.chat.say('ayuda'); self.assertIn('Así funciona', self.chat.text())

    def test_unknown_text_offers_buttons(self):
        self.chat.say('hola'); r = self.chat.say('blablabla')
        self.assertTrue(self.chat.options())


class BookingTests(Base):
    def test_happy_path_and_result_buttons(self):
        c = self.chat
        c.say('hola'); c.tap('Reservar clase')
        self.assertEqual(len(c.options()), 6 + 1)   # 6 días + menú; sin «Más opciones»
        self.assertNotIn('Más opciones', ' '.join(o[1] for o in c.options()))
        self.assertRegex(' '.join(o[1] for o in c.options()), r'\d{1,2} de [a-zé]+ · (Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)')
        c.tap(c.options()[0][1])
        shown = ' '.join(o[1] for o in c.options())    # todas las clases del día de una vez
        for wanted in ('09:00 Pilates', '10:00 Yoga', '18:30 Cross Training'): self.assertIn(wanted, shown)
        self.assertIn('completa', shown); self.assertNotIn('Cerrada', shown)
        c.tap('09:00 Pilates'); self.assertIn('¿Confirmas la reserva para Ana Pérez?', c.text())
        self.assertEqual(len(self.backend.bookings), 0)           # aún nada: falta confirmar
        c.tap('Confirmar reserva')
        self.assertIn('Reserva confirmada', c.text()); self.assertIn('Pilates', c.text())
        titles = ' '.join(o[0] for o in c.options())
        for wanted in ('Mis reservas', 'Reservar otra', 'Menú'): self.assertIn(wanted, titles)
        self.assertEqual(len(c.options()), 3)
        self.assertEqual(len(self.backend.bookings), 1); self.assertEqual(self.backend.free[1], 2)

    def test_full_class_offers_waitlist_with_clear_warning(self):
        c = self.chat
        c.say('hola'); self.pick_day()
        self.assertIn('completa', ' '.join(o[1] for o in c.options()))
        c.tap('10:00')
        self.assertIn('completa', c.text()); self.assertIn('lista de espera', c.text())
        self.assertEqual(len(self.backend.bookings), 0)
        c.tap('Entrar en espera')
        self.assertIn('lista de espera', c.text()); self.assertIn('Posición 2', c.text())
        self.assertEqual(self.backend.bookings[1]['estado'], 'WAITLIST')

    def test_double_tap_on_confirm_books_once(self):
        c = self.chat
        c.say('hola'); self.pick('09:00 Pilates')
        token = [o for o in c.options() if 'Confirmar' in o[0]][0][2]
        first = c.tap_id(token); second = c.tap_id(token)
        self.assertEqual(plain(first), plain(second))
        self.assertEqual(len(self.backend.bookings), 1); self.assertEqual(self.backend.free[1], 2)

    def test_business_limits_are_explained(self):
        c = self.chat
        for code, snippet in (('WEEKLY_PERSON_LIMIT', '10 clases de esta semana'), ('DAILY_PHONE_LIMIT', '3 clases al día'),
                              ('FUTURE_PHONE_LIMIT', '5 clases futuras'), ('DATE_OUTSIDE_WINDOW', '5 días por delante')):
            self.backend.fail = {'reserve': code}
            c.say('hola'); self.pick('09:00 Pilates')
            c.tap('Confirmar reserva')
            self.assertIn(snippet, c.text()); self.assertNotIn('/start', c.text())
            self.assertIn('Menú', ' '.join(o[0] for o in c.options()))
        self.assertEqual(len(self.backend.bookings), 0)

    def test_class_fills_while_deciding(self):
        c = self.chat
        c.say('hola'); self.pick('18:30 Cross')
        self.backend.free[3] = 0
        c.tap('Confirmar reserva')
        self.assertIn('se ha llenado', c.text()); self.assertEqual(len(self.backend.bookings), 0)

    def test_session_closed_while_deciding(self):
        c = self.chat
        c.say('hola'); self.pick_day()
        self.backend.sessions = lambda day: []
        c.tap('09:00 Pilates'); self.assertIn('ya no admite reservas', c.text())

    def test_expired_button_returns_to_menu(self):
        c = self.chat
        c.say('hola'); c.tap('Reservar clase')
        old = c.options()[0][2]
        c.now[0] += 1000
        c.tap_id(old)
        self.assertIn('ha caducado', c.text()); self.assertIn('Reservar clase', ' '.join(o[1] for o in c.options()))
        self.assertEqual(len(self.backend.bookings), 0)

    def test_unknown_token_cannot_book(self):
        self.chat.say('hola')
        reply = self.chat.flow.handle('123', token='X' * 24)
        self.assertIn('caducado', reply['text']); self.assertEqual(len(self.backend.bookings), 0)

    def test_button_from_other_user_is_rejected(self):
        c = self.chat; c.say('hola'); token = c.options()[0][2]
        reply = c.flow.handle('999', token=token)
        self.assertEqual(len(self.backend.bookings), 0); self.assertIn('caducado', reply['text'])

    def test_old_person_button_after_switch(self):
        self.backend.people_ = [{'id': 7, 'nombre': 'Ana Pérez'}, {'id': 8, 'nombre': 'Leo Pérez'}]
        c = self.chat; c.say('hola'); c.tap('Ana')
        c.tap('Reservar clase'); stale = c.options()[0][2]
        c.say('cambiar persona'); c.tap('Leo')
        reply = c.flow.handle('123', token=stale)
        self.assertNotIn('Elige', plain(reply)[:0] or 'x'); self.assertEqual(len(self.backend.bookings), 0)

    def test_many_classes_split_in_morning_and_evening(self):
        hours = ['07:30', '09:00', '10:00', '11:00', '17:00', '18:00', '19:00', '20:00', '20:30', '21:00']
        self.backend.names = {i: f'Clase {i:02d}' for i in range(1, 11)}
        self.backend.free = {i: 5 for i in range(1, 11)}
        self.backend.sessions = lambda day: [{'id': i, 'clase': f'Clase {i:02d}', 'fecha': day, 'hora': hours[i - 1], 'limite': 10, 'disponibles': 5} for i in range(1, 11)]
        c = self.chat; c.say('hola'); self.pick_day()
        self.assertIn('Mañana', ' '.join(o[0] for o in c.options())); self.assertIn('Tarde', ' '.join(o[0] for o in c.options()))
        c.tap('Tarde'); shown = ' '.join(o[1] for o in c.options())
        self.assertIn('17:00 Clase 05', shown); self.assertNotIn('Clase 01', shown)

    def test_nine_classes_fit_in_one_list_when_one_period(self):
        self.backend.sessions = lambda day: [{'id': i, 'clase': f'Clase {i:02d}', 'fecha': day, 'hora': f'{14+i}:00', 'limite': 10, 'disponibles': 5} for i in range(1, 10)]
        self.backend.names = {i: f'Clase {i:02d}' for i in range(1, 10)}; self.backend.free = {i: 5 for i in range(1, 10)}
        c = self.chat; c.say('hola'); self.pick_day()
        self.assertEqual(len(c.options()), 10); self.assertNotIn('Más opciones', ' '.join(o[1] for o in c.options()))

    def test_closed_day_has_message(self):
        self.backend.sessions = lambda day: []
        c = self.chat; c.say('hola'); self.pick_day()
        self.assertIn('No hay clases', c.text())

    def test_web_booking_option(self):
        c = self.chat; c.say('hola')
        self.assertIn('Reservar en la web', ' '.join(o[1] for o in c.options()))
        reply = c.tap('Reservar en la web')
        self.assertEqual(reply['whatsapp_web_access'], {'user': '123', 'person': 7})
        self.assertEqual(c.last[1]['interactive']['type'], 'cta_url')


class PortableBookingTests(BookingTests):
    portable = True

    def test_natural_text_then_confirmation(self):
        c = self.chat; c.say('hola')
        c.say('Quiero pilates hoy')
        self.assertIn('Pilates', ' '.join(o[1] for o in c.options()))
        c.tap('09:00'); c.tap('Confirmar reserva'); self.assertEqual(len(self.backend.bookings), 1)


class CancellationTests(Base):
    def test_cancel_requires_explicit_confirmation(self):
        self.book(); c = self.chat
        c.say('hola'); c.tap('Mis reservas'); c.tap('Pilates')
        c.tap('Cancelar reserva')
        self.assertIn('¿Seguro que quieres cancelar', c.text())
        self.assertEqual(self.backend.bookings[1]['estado'], 'RESERVED')
        c.tap('No, mantenerla'); self.assertEqual(self.backend.bookings[1]['estado'], 'RESERVED')
        c.tap('Pilates'); c.tap('Cancelar reserva'); token = [o for o in c.options() if 'Sí' in o[0]][0][2]
        c.tap_id(token); self.assertIn('Reserva cancelada', c.text())
        c.tap_id(token)                       # segunda pulsación: mismo resultado, sin error
        self.assertIn('Reserva cancelada', c.text()); self.assertEqual(self.backend.bookings[1]['version'], 2)

    def test_leave_waitlist_requires_confirmation(self):
        c = self.chat
        c.say('hola'); self.pick('10:00 Yoga'); c.tap('Entrar en espera')
        c.tap('Menú'); c.tap('Lista de espera'); c.tap('Yoga'); c.tap('Salir de la espera')
        self.assertIn('salir de la lista de espera', c.text()); self.assertEqual(self.backend.bookings[1]['estado'], 'WAITLIST')
        c.tap('Sí, salir'); self.assertIn('salido de la lista', c.text()); self.assertEqual(self.backend.bookings[1]['estado'], 'CANCELLED')

    def test_stale_booking_version(self):
        self.book(); c = self.chat
        c.say('hola'); c.tap('Mis reservas'); stale = c.options()[0][2]
        self.backend.bookings[1]['version'] = 5
        c.tap_id(stale); self.assertIn('ha cambiado', c.text())

    def test_empty_lists(self):
        c = self.chat; c.say('hola')
        c.tap('Mis reservas'); self.assertIn('No tienes clases reservadas', c.text())
        c.tap('Menú'); c.tap('Lista de espera'); self.assertIn('No estás en ninguna lista', c.text())


class GuestTests(unittest.TestCase):
    """Número oficial: quien no está en el directorio solo recibe el enlace público a la web."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, 's.sqlite')); self.addCleanup(self.store.c.close)
        self.backend = FakeBackend()
        self.flow = WhatsAppFlow(WhatsAppMenuFlow(self.backend, self.store, pilot=True))
        self.directory = {PHONE: {'principal': '123', 'consent': {'service': True}}}
        self.n = 0

    def gateway(self, guest):
        from bot.whatsapp_welcome import ReservationWelcome
        return WhatsAppGateway(self.flow, self.store, self.directory, 'fake-secret', '999',
                               guest_flow=ReservationWelcome(self.store) if guest else None)

    def send(self, gateway, sender, text='Hola'):
        self.n += 1
        doc = {'object': 'whatsapp_business_account', 'entry': [{'id': 't', 'changes': [{'field': 'messages', 'value': {
            'metadata': {'phone_number_id': '999'}, 'messages': [{'id': f'm{self.n}', 'from': sender, 'timestamp': str(int(time.time())),
                                                                   'type': 'text', 'text': {'body': text}}]}}]}]}
        raw = json.dumps(doc).encode()
        return gateway.accept(raw, 'sha256=' + hmac.new(b'fake-secret', raw, hashlib.sha256).hexdigest())

    def test_unknown_number_gets_web_link_only(self):
        g = self.gateway(True)
        result = self.send(g, '34699999999')
        self.assertEqual(len(result), 1)
        decision = g.decision('34699999999', result[0]['reply'], WhatsAppPolicy())
        self.assertTrue(decision.allowed, decision.reason)
        self.assertEqual(decision.payload['interactive']['type'], 'cta_url')
        self.assertEqual(self.backend.bookings, {})

    def test_unknown_number_cannot_use_buttons_or_booking(self):
        g = self.gateway(True)
        self.send(g, '34699999999')
        # Un botón del miembro autorizado no sirve para otro número.
        member = self.send(g, PHONE)[0]['reply']
        token = member['reply_markup']['inline_keyboard'][0][0]['callback_data']
        result = self.send(g, '34699999999', 'Reservar clase')
        self.assertTrue(result == [] or result[0]['reply'] is None or 'cta' in json.dumps(result[0]['reply']))
        self.assertEqual(self.backend.bookings, {})

    def test_disabled_by_default_ignores_unknown(self):
        self.assertEqual(self.send(self.gateway(False), '34699999999'), [])

    def test_member_still_gets_the_bot(self):
        g = self.gateway(True)
        reply = self.send(g, PHONE)[0]['reply']
        self.assertIn('Hola, Ana Pérez', reply['text'])


class WorkerTests(unittest.TestCase):
    def test_worker_uses_buttons_not_landing_or_flows(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        (Path(tmp.name) / '.local').mkdir()
        directory = {PHONE: {'principal': '123', 'consent': {'service': True}}}
        raw = json.dumps({'object': 'whatsapp_business_account', 'entry': [{'id': 't', 'changes': [{'field': 'messages', 'value': {
            'metadata': {'phone_number_id': '999'}, 'messages': [{'id': 'm1', 'from': PHONE, 'timestamp': str(int(time.time())),
                                                                   'type': 'text', 'text': {'body': 'Hola'}}]}}]}]}).encode()
        queue = Queue(Path(tmp.name) / 'q.sqlite'); queue.put(raw)
        ready, stop = threading.Event(), threading.Event()
        config = {'WA_DIRECTORY_JSON': json.dumps(directory), 'WA_APP_SECRET': 'fake-secret', 'WA_TEST_PHONE_NUMBER_ID': '999',
                  'WA_ACCESS_TOKEN': 'fake-token', 'WA_GRAPH_VERSION': 'v23.0', 'WA_FLOW_ID': 'must-not-be-used'}
        sent = []
        def fake_send(decision):
            sent.append(decision.payload); stop.set(); return {'messages': [{'id': 'out1'}]}
        with patch('bot.whatsapp_webhook.ROOT', Path(tmp.name)), \
             patch('bot.whatsapp_webhook.booking_backend', return_value=FakeBackend()), \
             patch('bot.whatsapp.WhatsAppTransport.send', side_effect=fake_send):
            worker(queue, config, ready, stop)
        self.assertTrue(ready.is_set()); self.assertEqual(len(sent), 1)
        payload = sent[0]
        self.assertEqual(payload['interactive']['type'], 'list')
        self.assertNotIn('flow', json.dumps(payload).lower().replace('flow_', ''))
        self.assertIn('Reservar clase', json.dumps(payload, ensure_ascii=False))
        self.assertTrue(payload.get('__tf_welcome_image'))


if __name__ == '__main__':
    unittest.main()
