import base64, hashlib, hmac, json, os, re, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from bot.portable.store import Store
from bot.transport import Rejected, TemporaryFailure
from bot.whatsapp_booking_flow import BookingFlow, day_label, today
from bot.whatsapp_flow_endpoint import FlowEndpoint
from datetime import timedelta

D = [(today() + timedelta(days=i)).isoformat() for i in range(3)]

class FakeBackend:
    official_web = True
    def __init__(self, people=None):
        self.people_ = people or [{'id': 7, 'nombre': 'Ana Pérez'}]
        self.reserved = {}; self.fail = None; self.calls = []
        self.free = {1: 3, 2: 1, 3: 0}
    def sched(self, day):
        names = {1: 'Pilates mat', 2: 'Cross Training con un nombre larguísimo de verdad', 3: 'Yoga'}
        return [{'id': i, 'clase': names[i], 'fecha': day, 'hora': f'{9+i}:00', 'limite': 10,
                 'disponibles': self.free[i]} for i in (1, 2, 3)] + [{'id': 9, 'clase': 'Cerrada', 'fecha': day, 'hora': '8:00', 'limite': 0, 'disponibles': 0}]
    def call(self, user, **d):
        self.calls.append(d['action'])
        if self.fail: raise self.fail
        a = d['action']
        if a == 'people': return {'ok': True, 'people': self.people_}
        if a == 'dates': return {'ok': True, 'dates': D}
        if a == 'schedules': return {'ok': True, 'schedules': self.sched(d['fecha'])}
        if a == 'reserve':
            key = d['request_key']
            if key in self.reserved: return self.reserved[key]
            if self.free[d['horario_id']] <= 0 and not d['accept_waitlist']: raise Rejected('WAITLIST_CONFIRMATION_REQUIRED')
            wait = self.free[d['horario_id']] <= 0
            if not wait: self.free[d['horario_id']] -= 1
            r = {'ok': True, 'booking': {'id': len(self.reserved) + 1, 'nombre': 'Ana Pérez', 'clase': 'x', 'fecha': d['fecha'],
                 'hora': '10:00', 'estado': 'WAITLIST' if wait else 'RESERVED', 'posicion': 2 if wait else None}}
            self.reserved[key] = r; return r
        raise AssertionError(a)

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.store = Store(os.path.join(self.tmp, 's.sqlite'))
        self.backend = FakeBackend(); self.flow = BookingFlow(self.backend, self.store)
        self.token = self.flow.start('u1')
    def ex(self, action, screen=None, data=None, token=None):
        r = {'version': '3.0', 'action': action, 'flow_token': token or self.token}
        if screen: r.update(screen=screen, data=data or {})
        return self.flow.exchange(r)

class Journey(Base):
    def test_happy_path(self):
        v = self.ex('INIT'); self.assertEqual(v['screen'], 'START')
        self.assertFalse(v['data']['show_person'])
        acts = {a['title']: a['id'] for a in v['data']['activities']}
        self.assertEqual(len(acts), 3)  # 'Cerrada' (limite 0) fuera
        self.assertTrue(all(len(t) <= 30 for t in acts))
        v = self.ex('data_exchange', 'START', {'person': '', 'activity': acts['Pilates mat']})
        self.assertEqual(v['screen'], 'DAY'); self.assertEqual(len(v['data']['days']), 3)
        self.assertEqual(v['data']['days'][0]['description'], 'Hoy')
        v = self.ex('data_exchange', 'DAY', {'choice': '1'}); self.assertEqual(v['screen'], 'SLOT')
        slot = v['data']['slots'][0]; self.assertIn('3 plazas libres', slot['description'])
        v = self.ex('data_exchange', 'SLOT', {'choice': slot['id']}); self.assertEqual(v['screen'], 'CONFIRM')
        self.assertTrue(v['data']['can_confirm'])
        v = self.ex('data_exchange', 'CONFIRM', {'confirm': True}); self.assertEqual(v['screen'], 'DONE')
        self.assertEqual(v['data']['headline'], 'Reserva confirmada'); self.assertEqual(v['data']['flow_token'], self.token)
        again = self.ex('data_exchange', 'CONFIRM', {'confirm': True})
        self.assertEqual(again, v); self.assertEqual(len(self.backend.reserved), 1)
        self.assertEqual(self.flow.completion('u1', self.token)['estado'], 'RESERVED')
        with self.assertRaises(Rejected): self.flow.completion('otro', self.token)

    def test_waitlist(self):
        v = self.ex('INIT'); acts = {a['title']: a['id'] for a in v['data']['activities']}
        self.ex('data_exchange', 'START', {'activity': acts['Yoga']}); self.ex('data_exchange', 'DAY', {'choice': '0'})
        v = self.ex('data_exchange', 'SLOT', {'choice': '3'})
        self.assertIn('lista de espera', v['data']['note'])
        v = self.ex('data_exchange', 'CONFIRM', {'confirm': True})
        self.assertEqual(v['data']['headline'], 'Estás en la lista de espera'); self.assertIn('Posición 2', v['data']['detail'])

    def test_back_navigation_resubmits_earlier_screens(self):
        v = self.ex('INIT'); acts = {a['title']: a['id'] for a in v['data']['activities']}
        self.ex('data_exchange', 'START', {'activity': acts['Pilates mat']}); self.ex('data_exchange', 'DAY', {'choice': '0'})
        self.ex('data_exchange', 'SLOT', {'choice': '1'})
        v = self.ex('data_exchange', 'SLOT', {'choice': '1'}); self.assertEqual(v['screen'], 'CONFIRM')  # atrás y otra vez
        v = self.ex('data_exchange', 'DAY', {'choice': '2'}); self.assertEqual(v['screen'], 'SLOT')
        with self.assertRaises(Rejected): self.flow.completion('u1', self.token)  # aún sin reservar
        v = self.ex('data_exchange', 'START', {'activity': acts['Yoga']}); self.assertEqual(v['screen'], 'DAY')
        self.assertEqual(self.backend.reserved, {})
        self.ex('data_exchange', 'DAY', {'choice': '0'})
        v = self.ex('data_exchange', 'CONFIRM', {'confirm': True})  # sin horario elegido
        self.assertTrue(v['data']['has_error'])

    def test_full_class_after_choice_and_limits(self):
        v = self.ex('INIT'); acts = {a['title']: a['id'] for a in v['data']['activities']}
        self.ex('data_exchange', 'START', {'activity': acts['Pilates mat']}); self.ex('data_exchange', 'DAY', {'choice': '0'})
        self.backend.free[1] = 0  # se llena mientras decide
        v = self.ex('data_exchange', 'SLOT', {'choice': '1'}); self.assertIn('lista de espera', v['data']['note'])
        self.backend.free[1] = 2
        self.ex('data_exchange', 'SLOT', {'choice': '1'})
        orig = self.backend.call
        def deny(user, **d):
            if d['action'] == 'reserve': raise Rejected('WEEKLY_PERSON_LIMIT')
            return orig(user, **d)
        self.backend.call = deny
        v = self.ex('data_exchange', 'CONFIRM', {'confirm': True})
        self.assertEqual(v['screen'], 'CONFIRM'); self.assertFalse(v['data']['can_confirm']); self.assertIn('10 clases', v['data']['error'])

    def test_temporary_failure_keeps_state_and_retry_is_idempotent(self):
        v = self.ex('INIT'); acts = {a['title']: a['id'] for a in v['data']['activities']}
        self.ex('data_exchange', 'START', {'activity': acts['Pilates mat']}); self.ex('data_exchange', 'DAY', {'choice': '0'})
        self.ex('data_exchange', 'SLOT', {'choice': '1'})
        self.backend.fail = TemporaryFailure('x')
        v = self.ex('data_exchange', 'CONFIRM', {'confirm': True})
        self.assertEqual(v['screen'], 'CONFIRM'); self.assertTrue(v['data']['has_error']); self.assertTrue(v['data']['can_confirm'])
        self.backend.fail = None
        self.assertEqual(self.ex('data_exchange', 'CONFIRM', {'confirm': True})['screen'], 'DONE')

    def test_security(self):
        self.ex('INIT')
        for bad in ('99', 'x', '-1', None, 5):
            v = self.ex('data_exchange', 'START', {'activity': bad})
            self.assertTrue(v['data']['has_error'] or v['screen'] != 'DONE')
        with self.assertRaises(Rejected): self.ex('data_exchange', 'START', {'person': '999', 'activity': '0'})
        with self.assertRaises(Rejected): self.ex('INIT', token='nope')
        with self.assertRaises(Rejected): self.flow.exchange({'version': '2.0', 'action': 'INIT', 'flow_token': self.token})
        self.store.c.execute('UPDATE wa_booking_flows SET expires=0'); self.store.c.commit()
        with self.assertRaises(Rejected): self.ex('INIT')
        self.assertEqual(self.flow.exchange({'version': '3.0', 'action': 'ping'}), {'data': {'status': 'active'}})

    def test_multiple_people_require_choice(self):
        self.backend.people_ = [{'id': 7, 'nombre': 'Ana'}, {'id': 8, 'nombre': 'Luis'}]
        v = self.ex('INIT'); self.assertTrue(v['data']['show_person'])
        v = self.ex('data_exchange', 'START', {'person': '', 'activity': '0'})
        self.assertEqual(v['screen'], 'START'); self.assertTrue(v['data']['has_error'])
        v = self.ex('data_exchange', 'START', {'person': '8', 'activity': '0'}); self.assertEqual(v['screen'], 'DAY')

    def test_labels(self):
        self.assertEqual(day_label(today().isoformat())[1], 'Hoy')
        self.assertTrue(len(day_label('2026-10-21')[0]) <= 30)

    def test_concurrent_confirm_books_once(self):
        v = self.ex('INIT'); acts = {a['title']: a['id'] for a in v['data']['activities']}
        self.ex('data_exchange', 'START', {'activity': acts['Pilates mat']}); self.ex('data_exchange', 'DAY', {'choice': '0'})
        self.ex('data_exchange', 'SLOT', {'choice': '1'})
        path = os.path.join(self.tmp, 's.sqlite'); results = []
        def go():
            f = BookingFlow(self.backend, Store(path))
            results.append(f.exchange({'version': '3.0', 'action': 'data_exchange', 'screen': 'CONFIRM', 'flow_token': self.token, 'data': {'confirm': True}}))
        ts = [threading.Thread(target=go) for _ in range(6)]; [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(self.backend.reserved), 1); self.assertTrue(all(r['screen'] == 'DONE' for r in results))

class FlowJson(unittest.TestCase):
    """El contrato del JSON y de las respuestas del servidor tiene que coincidir."""
    def setUp(self):
        self.doc = json.loads((Path(__file__).resolve().parents[1] / 'assets/whatsapp-booking-flow.json').read_text(encoding='utf-8'))
        self.screens = {s['id']: s for s in self.doc['screens']}
    def walk(self, node):
        if isinstance(node, dict):
            yield node
            for v in node.values(): yield from self.walk(v)
        elif isinstance(node, list):
            for v in node: yield from self.walk(v)
    def test_structure(self):
        self.assertLess(len(json.dumps(self.doc)), 400_000)
        routes = self.doc['routing_model']; self.assertEqual(set(routes), set(self.screens))
        targets = {t for v in routes.values() for t in v}
        self.assertEqual(set(routes) - targets, {'START'})  # una sola entrada
        for s in self.screens.values():
            self.assertLessEqual(len(s['title']), 30)
            self.assertEqual(sum(1 for n in self.walk(s['layout']) if n.get('type') == 'Footer'), 1)
            self.assertLessEqual(sum(1 for n in self.walk(s['layout']) if n.get('type') == 'Image'), 3)
        self.assertTrue(self.screens['DONE']['terminal'])
        for s in self.screens.values():
            for n in self.walk(s['layout']):
                if n.get('type') == 'Image': self.assertLess(len(n['src']) * 3 // 4, 300_000)
                if n.get('type') in ('Dropdown', 'RadioButtonsGroup'): self.assertLessEqual(len(n['label']), 20)
    def test_bindings_are_declared(self):
        for s in self.screens.values():
            for text in [json.dumps(n) for n in self.walk(s['layout'])]:
                for ref in re.findall(r'\$\{data\.(\w+)\}', text): self.assertIn(ref, s['data'], (s['id'], ref))
    def test_server_views_match_declared_data(self):
        t = tempfile.mkdtemp(); store = Store(os.path.join(t, 's.sqlite')); b = FakeBackend(); f = BookingFlow(b, store)
        tok = f.start('u1'); seen = {}
        def ex(a, sc=None, d=None):
            r = {'version': '3.0', 'action': a, 'flow_token': tok}
            if sc: r.update(screen=sc, data=d)
            v = f.exchange(r); seen[v['screen']] = v; return v
        ex('INIT'); ex('data_exchange', 'START', {'activity': '0'}); ex('data_exchange', 'DAY', {'choice': '0'})
        ex('data_exchange', 'SLOT', {'choice': seen['SLOT']['data']['slots'][0]['id']}); ex('data_exchange', 'CONFIRM', {'confirm': True})
        self.assertEqual(set(seen), set(self.screens))
        for name, v in seen.items():
            declared = set(self.screens[name]['data'])
            self.assertEqual(set(v['data']) - declared, set(), name)   # nada sin declarar
            for key in declared - set(v['data']): self.fail(f'{name}: falta {key}')
            for key, spec in self.screens[name]['data'].items():
                if spec['type'] == 'array':
                    for item in v['data'][key]:
                        self.assertLessEqual(len(item['title']), 30); self.assertLessEqual(len(item.get('description', '')), 300)
                    self.assertLessEqual(len(v['data'][key]), 20 if name != 'START' else 200); self.assertGreaterEqual(len(v['data'][key]), 1)

class Endpoint(unittest.TestCase):
    def setUp(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        self.t = tempfile.mkdtemp(); self.secret = 'secreto'; self.backend = FakeBackend()
        from contextlib import contextmanager
        path = os.path.join(self.t, 's.sqlite'); self.token = BookingFlow(self.backend, Store(path)).start('u1')
        @contextmanager
        def factory():
            s = Store(path)
            try: yield BookingFlow(self.backend, s)
            finally: s.c.close()
        self.ep = FlowEndpoint(self.secret, pem, factory)
    def send(self, request, sign=True):
        aes = os.urandom(16); iv = os.urandom(16)
        env = {'encrypted_aes_key': base64.b64encode(self.key.public_key().encrypt(aes, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))).decode(),
               'initial_vector': base64.b64encode(iv).decode(),
               'encrypted_flow_data': base64.b64encode(AESGCM(aes).encrypt(iv, json.dumps(request).encode(), None)).decode()}
        raw = json.dumps(env).encode()
        sig = 'sha256=' + hmac.new(self.secret.encode(), raw, hashlib.sha256).hexdigest() if sign else 'sha256=00'
        code, body = self.ep.process(raw, sig)
        if code == 200: body = json.loads(AESGCM(aes).decrypt(bytes(v ^ 255 for v in iv), base64.b64decode(body), None))
        return code, body
    def test_codes(self):
        self.assertEqual(self.send({'version': '3.0', 'action': 'ping'}), (200, {'data': {'status': 'active'}}))
        code, body = self.send({'version': '3.0', 'action': 'INIT', 'flow_token': self.token}); self.assertEqual((code, body['screen']), (200, 'START'))
        self.assertEqual(self.send({'version': '3.0', 'action': 'INIT'}, sign=False)[0], 432)
        code, body = self.send({'version': '3.0', 'action': 'INIT', 'flow_token': 'caducado'})
        self.assertEqual(code, 427); self.assertIn('error_msg', json.loads(body))
        self.assertEqual(self.ep.process(b'{"x":1}', 'sha256=' + hmac.new(b'secreto', b'{"x":1}', hashlib.sha256).hexdigest())[0], 421)
        self.backend.fail = TemporaryFailure('x')  # INIT ya guardado: se repite la respuesta sin tocar el backend
        self.assertEqual(self.send({'version': '3.0', 'action': 'INIT', 'flow_token': self.token})[0], 200)

if __name__ == '__main__': unittest.main(verbosity=1)
