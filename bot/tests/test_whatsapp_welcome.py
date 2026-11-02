import hashlib
import hmac
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot.portable.store import Store
from bot.transport import Rejected, TemporaryFailure
from bot.whatsapp import WhatsAppGateway, WhatsAppPolicy, WhatsAppTransport, whatsapp_payload
from bot.whatsapp_webhook import Queue, process_job, handler
from bot.whatsapp_welcome import ReservationWelcome, RESERVATIONS_URL


class WelcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = time.time()
        self.path = Path(self.tmp.name) / 'state.sqlite'
        self.store = Store(self.path, clock=lambda: self.now)
        self.addCleanup(self.store.c.close)
        self.flow = ReservationWelcome(self.store)
        self.recipient = '34600000001'
        self.directory = {self.recipient: {'principal': '123', 'consent': {'service': True}}}
        self.receipts = []
        self.gateway = WhatsAppGateway(self.flow, self.store, self.directory, 'fake-secret', '999',
                                       clock=lambda: self.now, status_handler=self.receipts.append)
        self.policy = WhatsAppPolicy(clock=lambda: self.now)
        self.serial = 0

    def envelope(self, text='Hola', **message):
        self.serial += 1
        msg = dict(id='fake-message-' + str(self.serial), timestamp=str(int(self.now)),
                   type='text', text={'body': text})
        msg['from'] = self.recipient
        msg.update(message)
        return {'object': 'whatsapp_business_account', 'entry': [{'id': 'test', 'changes': [
            {'field': 'messages', 'value': {'metadata': {'phone_number_id': '999'}, 'messages': [msg]}}]}]}

    def accept(self, doc):
        raw = json.dumps(doc).encode()
        signature = 'sha256=' + hmac.new(b'fake-secret', raw, hashlib.sha256).hexdigest()
        return self.gateway.accept(raw, signature)

    def inbound(self, text='Hola', **msg):
        return self.accept(self.envelope(text, **msg))[0]

    def assert_cta(self, result):
        decision = self.gateway.decision(self.recipient, result['reply'], self.policy)
        self.assertTrue(decision.allowed)
        payload = decision.payload
        self.assertEqual(payload['type'], 'interactive')
        self.assertEqual(payload['interactive']['type'], 'cta_url')
        self.assertEqual(payload['interactive']['action'], {'name': 'cta_url', 'parameters': {
            'display_text': 'Reservar clases', 'url': RESERVATIONS_URL}})
        self.assertEqual(set(payload['interactive']), {'type', 'body', 'action'})
        self.assertNotIn('__tf_web_access', payload)

    def test_first_message_any_text_has_one_static_cta(self):
        self.assert_cta(self.inbound('Me gustaría consultar las clases'))

    def test_greetings_and_commands(self):
        for text in ('Hola!', 'Hola, buenos días', 'Buenas tardes', '¡Buenos días!', 'Buenas noches',
                     '/start', 'menú', 'reservar clases', 'horarios'):
            self.now += 301
            self.assert_cta(self.inbound(text))

    def test_followup_and_greeting_burst_are_silent(self):
        self.assert_cta(self.inbound())
        for text in ('hola', 'buenas', 'gracias', 'vale', 'Quiero información'):
            self.now += 1
            self.assertIsNone(self.inbound(text)['reply'])

    def test_new_session_and_cooldown_survive_restart(self):
        self.inbound()
        replacement = ReservationWelcome(self.store)
        self.assertIsNone(replacement.handle_inbound('123', int(self.now), text='hola'))
        self.now += 86401
        self.assert_cta(self.inbound('Nueva consulta'))

    def test_duplicate_message_in_different_envelope_is_not_replied(self):
        doc = self.envelope()
        self.assert_cta(self.accept(doc)[0])
        doc['entry'][0]['id'] = 'different-envelope'
        self.assertTrue(self.accept(doc)[0]['duplicate'])

    def test_old_and_out_of_order_messages_are_silent(self):
        self.assertIsNone(self.inbound(timestamp=str(int(self.now - 86401)))['reply'])
        self.assert_cta(self.inbound())
        self.now += 301
        self.assertIsNone(self.inbound(timestamp=str(int(self.now - 600)))['reply'])

    def test_initial_media_and_old_callback_redirect_without_booking(self):
        self.assert_cta(self.inbound(type='audio', audio={'id': 'fake-media'}))
        self.now += 301
        self.assert_cta(self.inbound(type='interactive', interactive={
            'type': 'button_reply', 'button_reply': {'id': 'obsolete-booking-token'}}))
        self.now += 301
        self.assertIsNone(self.inbound(type='interactive', interactive={
            'type': 'nfm_reply', 'nfm_reply': {'response_json': '{"flow_token":"old-flow"}'}})['reply'])

    def test_statuses_echoes_wrong_number_and_unknown_sender_do_not_reply(self):
        doc = self.envelope()
        value = doc['entry'][0]['changes'][0]['value']
        value['messages'] = []
        value['statuses'] = [{'id': 'outbound', 'status': 'delivered'}]
        self.assertEqual(self.accept(doc), [])
        self.assertEqual(len(self.receipts), 1)
        doc = self.envelope()
        doc['entry'][0]['changes'][0]['field'] = 'message_echoes'
        self.assertEqual(self.accept(doc), [])
        doc = self.envelope()
        doc['entry'][0]['changes'][0]['value']['metadata']['phone_number_id'] = 'other'
        self.assertEqual(self.accept(doc), [])
        self.assertEqual(self.accept(self.envelope(**{'from': '34600000002'})), [])

    def test_signature_and_optout(self):
        with self.assertRaises(Rejected):
            self.gateway.accept(json.dumps(self.envelope()).encode(), 'sha256=bad')
        self.assertIsNone(self.inbound('STOP')['reply'])
        self.assertEqual(self.store.c.execute('SELECT unsubscribed FROM whatsapp_sessions').fetchone()[0], 1)
        self.assert_cta(self.inbound('Hola'))

    def test_outside_window_is_blocked_even_with_generic_template(self):
        reply = {'text': 'Hola', 'whatsapp_reservations_cta': True}
        policy = WhatsAppPolicy(approved_templates={'SESSION_REOPEN': {
            'approved': True, 'name': 'fake', 'language': 'es', 'quick_replies': 0}}, clock=lambda: self.now)
        decision = policy.prepare(self.recipient, reply, self.now - 86400, {'service': True})
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, 'APPROVED_URL_TEMPLATE_REQUIRED')
        self.assertFalse(policy.prepare(self.recipient, reply, self.now, {}).allowed)

    def test_queue_duplicate_and_ambiguous_send_are_never_replayed(self):
        queue = Queue(Path(self.tmp.name) / 'queue.sqlite')
        raw = json.dumps(self.envelope()).encode()
        queue.put(raw)
        queue.put(raw)
        row = queue.claim()
        self.assertIsNone(queue.claim())
        transport = unittest.mock.Mock()
        transport.send.side_effect = TemporaryFailure('fake')
        self.assertFalse(process_job(queue, self.gateway, transport, self.policy, 'fake-secret', row))
        self.assertEqual(transport.send.call_count, 1)
        self.assertIsNone(queue.claim())
        with queue.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM jobs').fetchone()[0], 'review')

    def test_transport_posts_exact_payload_without_backend(self):
        result = self.inbound()
        decision = self.gateway.decision(self.recipient, result['reply'], self.policy)
        transport = WhatsAppTransport('fake-token', '999', 'v23.0', enabled=True)
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"messages":[{"id":"fake-outbound"}]}'
        with patch('urllib.request.urlopen', return_value=response) as send:
            transport.send(decision)
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, 'https://graph.facebook.com/v23.0/999/messages')
        self.assertEqual(json.loads(request.data), decision.payload)

    def test_webhook_verification_signature_and_durable_reception(self):
        from http.server import ThreadingHTTPServer
        from http.client import HTTPConnection
        queue = Queue(Path(self.tmp.name) / 'http.sqlite')
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(queue, 'fake-secret', 'fake-verify'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection(*server.server_address)
        try:
            connection.request('GET', '/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=fake-verify&hub.challenge=challenge')
            response = connection.getresponse()
            self.assertEqual((response.status, response.read()), (200, b'challenge'))
            raw = json.dumps(self.envelope()).encode()
            for signature, expected in [('bad', 401), ('sha256=' + hmac.new(b'fake-secret', raw, hashlib.sha256).hexdigest(), 200)]:
                connection.request('POST', '/webhooks/whatsapp', raw, {'X-Hub-Signature-256': signature})
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            self.assertIsNotNone(queue.claim())
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
