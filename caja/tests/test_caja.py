"""Pruebas con datos sintéticos y adaptador falso del puente. Sin red ni SQL real."""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from caja import auth, bridge, hoja, importer, ledger, money, reports, service, xlsx  # noqa: E402
from caja.db import DB, encode, setting, put_setting  # noqa: E402

DAY = '2026-10-18'
ACTOR = dict(user_id=1, username='t', label='Test (t)')


def uid():
    return str(uuid.uuid4())


def row(key, cents, **kw):
    r = dict(key=key, day=DAY, name='Ana € renov', number='7', concept='Cuota', cents=cents, payment='EFECTIVO',
             origin='innux', employee='Eloy', notes='', issues=[], invoice='1', line='1', card='9', client_id='100',
             current_name='Ana €', pending=False)
    r.update(kw)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.db = DB(':memory:')
        with self.db.tx() as c:
            auth.create_user(c, 'u1', 'Usuario', 'admin', 'contraseña-larga-1')
            self.token = bridge.provision_device(c)
            put_setting(c, 'payments_enabled', True)
            c.execute("INSERT INTO client_cache VALUES ('100','7','Ana €','x')")
            c.execute("INSERT INTO client_cache VALUES ('101','8','Pepe %','x')")

    def refresh(self, rows, day=DAY):
        with self.db.tx() as c:
            ledger.apply_refresh(c, day, rows, '2026-10-18T10:00:00+02:00')

    def snap(self, day=DAY):
        with self.db.tx() as c:
            return ledger.live_snapshot(c, day)

    def manual(self, type_='ingreso', cents=1000, **kw):
        args = dict(concept='Concepto', name='', number='', employee='Eloy', notes='', request_id=uid(),
                    duplicate_confirmation=True)
        args.update(kw)
        with self.db.tx() as c:
            return ledger.add_manual(c, ACTOR, DAY, type_, cents=cents, **{k: v for k, v in args.items()})[0]

    def pay_data(self, **kw):
        d = dict(request_id=uid(), day=DAY, category='renovacion', cents=3990, client_id='100', number='7',
                 name='Ana €', employee='Eloy', pay=True, confirm=True)
        d.update(kw)
        return d

    def agent_poll(self):
        with self.db.tx() as c:
            dev = bridge.authenticate(c, 'Bearer ' + self.token, bridge.DEVICE_ID)
            return bridge.poll(c, dev, dict(protocol_version=1, agent_version='1.0.0', capabilities=list(bridge.CAPS)))

    def agent_result(self, job, status='succeeded', result=None, error=None, op=None, **extra):
        body = dict(device_id=bridge.DEVICE_ID, protocol_version=1, job_id=job['id'], operation=op or job['operation'],
                    fingerprint='ab' * 32, status=status, final=status != 'retry', result=result, error=error,
                    completed_at='2026-10-18T10:00:00+02:00')
        body.update(extra)
        with self.db.tx() as c:
            dev = bridge.authenticate(c, 'Bearer ' + self.token, bridge.DEVICE_ID)
            return bridge.submit_result(c, dev, body)

    def pay_result(self, p, **kw):
        r = dict(key='Q:55', card='9', client_id=p['client_id'], number=p['number'], cents=p['quota_cents'],
                 day=p['day'], valid_from=p['valid_from'], valid_until=p['valid_until'], plan_id='1', paid=True)
        r.update(kw)
        return r


class TestMoney(unittest.TestCase):
    def test_rounding_and_format(self):
        self.assertEqual(money.cents('39,90'), 3990)
        self.assertEqual(money.cents('0.005'), 1)
        self.assertEqual(money.cents('1.005'), 101)    # ROUND_HALF_UP decimal, no float
        self.assertEqual(money.cents('99999999'), 9999999900)
        for bad in ('NaN', 'inf', '', None, '100000000', 'abc'):
            with self.assertRaises(ValueError):
                money.cents(bad)

    def test_calculator_is_safe(self):
        self.assertEqual(money.calculate('(2+3)*4,5'), '22.5'.replace('.', ','))
        for bad in ('__import__("os")', '2**3', 'a+1', '1/0'):
            with self.assertRaises(ValueError):
                money.calculate(bad)

    def test_cash_rule(self):
        self.assertTrue(money.is_cash(row('Q:1', 100)))
        self.assertFalse(money.is_cash(row('Q:1', 100, name='Ana % €')))                     # % gana al €
        self.assertFalse(money.is_cash(row('Q:1', 100, current_name='Ana %')))
        self.assertFalse(money.is_cash(row('Q:1', 100, name='Ana', current_name='Ana')))     # sin €
        self.assertFalse(money.is_cash(row('Q:1', 100, notes='ADMINCUOTA:abc SIN CAJA')))
        self.assertFalse(money.is_cash(row('Q:1', 100, payment='TARJETA')))


class TestLedger(Base):
    def test_formulas(self):
        self.refresh([row('Q:1', 3990), row('Q:2', 0), row('Q:3', None), row('Q:4', 1000, name='Bob %'),
                      row('Q:5', 500, pending=True), row('Q:6', 700, notes='ADMINCUOTA:x'), row('Q:7', -300)])
        self.manual('ingreso', 1000)
        self.manual('gasto', 300, name='x')
        self.manual('retirada', 200, name='y')
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(opening=5000, counted=9490))
        t = self.snap()['totals']
        self.assertEqual((t['innux'], t['manual'], t['income']), (3990, 1000, 4990))
        self.assertEqual(t['expected'], 5000 + 4990 - 300 - 200)
        self.assertEqual(t['difference'], 9490 - t['expected'])
        self.assertEqual(t['net'], 4990 - 500)

    def test_manual_percent_and_dedupe(self):
        with self.assertRaises(ValueError):
            self.manual('ingreso', 1000, name='Ana %')
        self.manual('ingreso', 1000, name='Ana')
        with self.db.tx() as c, self.assertRaises(ledger.Conflict):
            ledger.add_manual(c, ACTOR, DAY, 'ingreso', 'Concepto', 1000, 'Ana', '', 'Eloy', '', request_id=uid())

    def test_request_id_requires_same_payload(self):
        rid = uid()
        self.manual('ingreso', 1000, request_id=rid)
        self.assertEqual(self.manual('ingreso', 1000, request_id=rid), self.manual('ingreso', 1000, request_id=rid))
        with self.assertRaises(ledger.Conflict):
            self.manual('ingreso', 2000, request_id=rid)

    def test_link_reconcile_and_return(self):
        self.refresh([row('Q:1', 3990)])
        m = self.manual('ingreso', 3990, name='Ana')
        with self.db.tx() as c:
            ledger.change_manual(c, ACTOR, m, 'vincular', 'Eloy', 'mismo cobro', 'Q:1')
        self.assertEqual(self.snap()['totals']['income'], 3990)       # suma el importado, no el manual
        self.refresh([row('Q:1', 4000)])                              # el origen cambia: vuelve a sumar con aviso
        s = self.snap()
        self.assertEqual(s['totals']['income'], 4000 + 3990)
        self.assertIn('vinculado', s['manual'][0]['warning'])
        m2 = self.manual('ingreso', 4000, name='Otra')
        with self.db.tx() as c, self.assertRaises(ValueError):        # un importado no admite dos manuales
            ledger.change_manual(c, ACTOR, m2, 'vincular', 'Eloy', 'x', 'Q:1')
            ledger.change_manual(c, ACTOR, m, 'desvincular', 'Eloy', 'x')
            ledger.change_manual(c, ACTOR, m, 'vincular', 'Eloy', 'x', 'Q:1')

    def test_exclusion_survives_refresh(self):
        self.refresh([row('Q:1', 3990)])
        with self.db.tx() as c:
            ledger.review_cash(c, ACTOR, DAY, 'Q:1', True, 'Eloy', 'era tarjeta')
        self.refresh([row('Q:1', 3990)])
        self.assertEqual(self.snap()['totals']['innux'], 0)
        self.refresh([row('Q:1', 5000)])
        s = self.snap()
        self.assertEqual(s['totals']['innux'], 0)
        self.assertTrue(any('ha cambiado' in i for i in s['imports'][0]['issues']))
        with self.db.tx() as c:
            ledger.review_cash(c, ACTOR, DAY, 'Q:1', False, 'Eloy', 'ok')
        self.assertEqual(self.snap()['totals']['innux'], 5000)

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            self.refresh([row('Q:1', 1), row('Q:1', 2)])
        self.assertEqual(self.snap()['imports'], [])

    def test_failed_refresh_keeps_last_good(self):
        self.refresh([row('Q:1', 3990)])
        with self.db.tx() as c:
            ledger.refresh_error(c, DAY, 'SQL caído')
        s = self.snap()
        self.assertEqual(s['totals']['innux'], 3990)
        self.assertEqual(s['refresh']['error'], 'SQL caído')


class TestPayments(Base):
    def create(self, **kw):
        d = self.pay_data(**kw)
        with self.db.tx() as c:
            return d, service.create_income(c, ACTOR, d)

    def test_envelope_and_flow(self):
        d, _ = self.create()
        reply = self.agent_poll()
        job = reply['job']
        self.assertEqual(set(job), {'id', 'operation', 'payload'})
        self.assertEqual(job['id'], d['request_id'])
        self.assertEqual(job['payload']['request_id'], job['id'])
        self.assertEqual((job['payload']['cents'], job['payload']['quota_cents'], job['payload']['payment_method']),
                         (3990, 3990, 'EFECTIVO'))
        self.assertEqual(job['payload']['valid_from'], '2026-10-01')
        self.assertEqual(job['payload']['valid_until'], '2026-10-31')
        self.assertEqual(self.snap()['totals']['income'], 0)                    # nada suma hasta verificar
        ack = self.agent_result(job, result=self.pay_result(job['payload']))
        self.assertEqual(ack, dict(acknowledged=True, job_id=job['id']))
        self.assertEqual(self.agent_result(job, result=self.pay_result(job['payload'])), ack)   # ack repetido
        self.assertEqual(self.snap()['totals']['income'], 3990)

    def test_matricula_alta_split(self):
        d, _ = self.create(category='matricula_alta', cents=5480, enrollment_cents=2490)
        p = self.agent_poll()['job']['payload']
        self.assertEqual((p['cents'], p['quota_cents'], p['enrollment_cents']), (5480, 2990, 2490))
        self.agent_result(dict(id=d['request_id'], operation='payments.pay'), result=self.pay_result(p))
        t = self.snap()['totals']
        self.assertEqual(t['income'], 5480)       # el total una sola vez
        # el cobro importado después con la marca CAJA no se suma de nuevo
        self.refresh([row('Q:55', 2990, notes='CAJA:%s Eloy' % d['request_id'])])
        self.assertEqual(self.snap()['totals']['income'], 5480)
        with self.assertRaises(ValueError):
            self.create(category='matricula_alta', cents=1000, enrollment_cents=1000, request_id=uid())

    def test_no_double_count_by_result_key(self):
        d, _ = self.create()
        p = self.agent_poll()['job']['payload']
        self.agent_result(dict(id=d['request_id'], operation='payments.pay'), result=self.pay_result(p, key='Q:77'))
        self.refresh([row('Q:77', 3990)])
        self.assertEqual(self.snap()['totals']['income'], 3990)
        # otro cliente con el mismo importe sí suma
        self.refresh([row('Q:77', 3990), row('Q:78', 3990, client_id='999')])
        self.assertEqual(self.snap()['totals']['income'], 7980)

    def test_retry_blocks_close_and_same_uuid(self):
        d, _ = self.create()
        job = self.agent_poll()['job']
        self.agent_result(job, status='retry', error=dict(code='CONNECTION_OR_LOCAL_ERROR', message='sin conexión'))
        self.assertIsNone(self.agent_poll()['job'])          # backoff: no se entrega aún ni otra escritura
        with self.db.tx() as c:
            c.execute("UPDATE jobs SET next_at='2000-01-01T00:00:00+00:00'")
        again = self.agent_poll()['job']
        self.assertEqual(again, job)                          # MISMO job, UUID y datos
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(counted=0, employee='Eloy', reason='x'))
        with self.db.tx() as c, self.assertRaises(ValueError):
            ledger.close_day(c, ACTOR, DAY, dict(opening=0, employee='Eloy'))

    def test_review_is_not_rejection(self):
        d, _ = self.create()
        job = self.agent_poll()['job']
        self.agent_result(job, status='review_required', error=dict(code='REVIEW_REQUIRED', message='dudoso'))
        with self.db.tx() as c:
            self.assertEqual(c.execute('SELECT void FROM manual').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT status FROM innux_payments').fetchone()[0], 'review_required')
        with self.db.tx() as c, self.assertRaises(ValueError):       # no se anula como si no existiera
            ledger.change_manual(c, ACTOR, c.execute('SELECT id FROM manual').fetchone()[0], 'anular', 'Eloy', 'x')
        mid = self.db.one('SELECT id FROM manual')['id']
        with self.db.tx() as c:
            service.resolve_payment(c, ACTOR, d['request_id'], 'paid', 'Eloy', 'visto en Innux')
        self.assertEqual(self.snap()['totals']['income'], 3990)
        self.assertTrue(mid)

    def test_confirmed_rejection_voids(self):
        d, _ = self.create()
        job = self.agent_poll()['job']
        self.agent_result(job, status='rejected', error=dict(code='PAYMENT_REJECTED', message='deuda'))
        self.assertEqual(self.db.one('SELECT void FROM manual')['void'], 1)
        self.assertEqual(self.snap()['totals']['income'], 0)

    def test_result_mismatch_goes_to_review(self):
        d, _ = self.create()
        job = self.agent_poll()['job']
        self.agent_result(job, result=self.pay_result(job['payload'], cents=1))
        self.assertEqual(self.db.one('SELECT status FROM innux_payments')['status'], 'review_required')

    def test_incompatible_terminal_and_bad_envelope(self):
        d, _ = self.create()
        job = self.agent_poll()['job']
        self.agent_result(job, result=self.pay_result(job['payload']))
        with self.assertRaises(bridge.BridgeError) as cm:
            self.agent_result(job, status='rejected', error=dict(code='PAYMENT_REJECTED', message='x'))
        self.assertEqual(cm.exception.status, 409)
        d2, _ = self.create(request_id=uid(), number='7', confirm_duplicate=True)
        job2 = self.agent_poll()['job']
        with self.assertRaises(bridge.BridgeError) as cm:
            self.agent_result(job2, op='health', result={})
        self.assertEqual(cm.exception.status, 422)
        with self.assertRaises(bridge.BridgeError):
            self.agent_result(dict(id=uid(), operation='health'), result={})

    def test_uuid_reuse_and_validation(self):
        d, _ = self.create()
        with self.db.tx() as c, self.assertRaises(ledger.Conflict):
            service.create_income(c, ACTOR, dict(d, cents=1000))
        with self.db.tx() as c:
            again = service.create_income(c, ACTOR, d)       # mismo payload: idempotente
        self.assertFalse(again['created'])
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM jobs WHERE operation='payments.pay'")['n'], 1)
        for bad in (dict(confirm=False), dict(client_id='abc'), dict(valid_from='2026-10-31', valid_until='2026-10-01'),
                    dict(valid_from='2026-01-01', valid_until='2027-06-01'), dict(client_id='100', name='otro')):
            with self.db.tx() as c, self.assertRaises(ValueError):
                service.create_income(c, ACTOR, self.pay_data(**bad))

    def test_direct_debit_and_unpaid_percent(self):
        d, _ = self.create(client_id='101', number='8', name='Pepe %')
        self.assertEqual(self.agent_poll()['job']['payload']['payment_method'], 'DOMICILIACIÓN BANCARIA')
        with self.db.tx() as c, self.assertRaises(ValueError):
            service.create_income(c, ACTOR, self.pay_data(client_id='101', number='8', name='Pepe %', pay=False))

    def test_payments_disabled_and_unpaired(self):
        with self.db.tx() as c:
            put_setting(c, 'payments_enabled', False)
        with self.db.tx() as c, self.assertRaises(ValueError):
            service.create_income(c, ACTOR, self.pay_data())
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM manual')['n'], 0)

    def test_manual_with_payment_not_editable(self):
        self.create()
        mid = self.db.one('SELECT id FROM manual')['id']
        with self.db.tx() as c, self.assertRaises(ValueError):
            ledger.correct_manual(c, ACTOR, mid, dict(cents=1), 'Eloy', 'x')

    def test_one_write_in_flight(self):
        a, _ = self.create()
        b, _ = self.create(request_id=uid(), number='7', cents=1000)
        first = self.agent_poll()['job']
        self.assertEqual(first['id'], a['request_id'])
        self.assertIsNone(self.agent_poll()['job'])          # lease vigente, no se entrega otra escritura


class TestBridgeAuthAndQueue(Base):
    def test_auth(self):
        with self.db.tx() as c:
            for hdr, dev in ((None, bridge.DEVICE_ID), ('Bearer ' + 'x' * 48, bridge.DEVICE_ID),
                             ('Bearer ' + self.token, 'otro-dispositivo')):
                with self.assertRaises(bridge.BridgeError):
                    bridge.authenticate(c, hdr, dev)
            bridge.revoke_device(c)
            with self.assertRaises(bridge.BridgeError):
                bridge.authenticate(c, 'Bearer ' + self.token, bridge.DEVICE_ID)

    def test_hash_only_stored(self):
        self.assertNotIn(self.token, json.dumps(self.db.q('SELECT * FROM devices')))

    def test_read_jobs_coalesce_and_health(self):
        with self.db.tx() as c:
            a = service.search_clients(c, ACTOR, 'ana')
            b = service.search_clients(c, ACTOR, 'ANA')
            r1 = service.request_refresh(c, ACTOR, DAY)
            r2 = service.request_refresh(c, ACTOR, DAY)
        self.assertEqual(a, b)
        self.assertEqual(r1, r2)
        job = self.agent_poll()['job']
        self.assertEqual(job['operation'], 'clients.search')
        self.agent_result(job, result=dict(clients=[dict(id='5', number='9', name='Ana Ruiz €')]))
        self.assertEqual(self.db.one("SELECT name FROM client_cache WHERE id='5'")['name'], 'Ana Ruiz €')

    def test_health_updates_sql_time_only_on_success(self):
        with self.db.tx() as c:
            bridge.enqueue(c, 'health', {})
        job = self.agent_poll()['job']
        self.assertIsNotNone(self.db.one('SELECT last_seen FROM devices')['last_seen'])
        self.assertIsNone(self.db.one('SELECT last_sql_ok FROM devices')['last_sql_ok'])   # poll != SQL
        self.agent_result(job, status='retry', error=dict(code='CONNECTION_OR_LOCAL_ERROR', message='no sql'))
        self.assertIsNone(self.db.one('SELECT last_sql_ok FROM devices')['last_sql_ok'])
        with self.db.tx() as c:
            c.execute("UPDATE jobs SET next_at='2000-01-01T00:00:00+00:00'")
        job = self.agent_poll()['job']
        self.agent_result(job, result=dict(online=True, server='s', database='d', identity='i', checked_at='x'))
        self.assertIsNotNone(self.db.one('SELECT last_sql_ok FROM devices')['last_sql_ok'])

    def test_cash_day_result_applied_and_wrong_day_rejected(self):
        with self.db.tx() as c:
            service.request_refresh(c, ACTOR, DAY)
        job = self.agent_poll()['job']
        self.agent_result(job, result=dict(day=DAY, updated_at='2026-10-18T10:00:00+02:00', rows=[row('Q:1', 3990)]))
        self.assertEqual(self.snap()['totals']['innux'], 3990)

    def test_admin_remove_snapshot_preserved(self):
        self.refresh([row('Q:1', 3990)])
        data = dict(request_id=uid(), client_id='100', number='7', card_id='9', quota_id='1', signature='sig',
                    employee='Eloy', confirm=True)
        with self.db.tx() as c:
            service.admin_quota(c, ACTOR, 'remove', data)
        job = self.agent_poll()['job']
        self.assertEqual(job['payload']['signature'], 'sig')
        self.agent_result(job, result=dict(action='remove', quota_id='1', removed=True, cash_snapshot=[row('Q:1', 3990)]))
        self.refresh([])                       # la fila desaparece de Innux
        s = self.snap()
        self.assertEqual(s['totals']['innux'], 3990)
        self.assertTrue(s['imports'][0]['admin_removed'])
        self.refresh([row('Q:1', 3990)])       # y si vuelve, no se duplica
        self.assertEqual(self.snap()['totals']['innux'], 3990)
        self.assertEqual(len(self.snap()['imports']), 1)

    def test_admin_activate_no_cash(self):
        data = dict(request_id=uid(), client_id='100', number='7', card_id='9', plan_id='3', quota_cents=0,
                    valid_from='2026-01-01', valid_until='2028-01-01', employee='Eloy', confirm=True)
        with self.db.tx() as c:
            service.admin_quota(c, ACTOR, 'activate', data)
            with self.assertRaises(ledger.Conflict):
                service.admin_quota(c, ACTOR, 'activate', dict(data, quota_cents=5))
            with self.assertRaises(ValueError):
                service.admin_quota(c, ACTOR, 'activate', dict(data, request_id=uid(), confirm=False))
        job = self.agent_poll()['job']
        self.agent_result(job, result=dict(action='activate', quota_id='9', active=True, cash_snapshot=[]))
        self.assertEqual(self.snap()['totals']['income'], 0)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM manual')['n'], 0)


class TestClosure(Base):
    def prep(self, counted=4990):
        self.refresh([row('Q:1', 3990)])
        self.manual('ingreso', 1000)
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(counted=counted, employee='Eloy'))
            put_setting(c, 'stale_minutes', 100000)

    def close(self, **kw):
        with self.db.tx() as c:
            return ledger.close_day(c, ACTOR, DAY, kw.pop('oc', dict(opening=0, employee='Eloy')), **kw)

    def test_confirmation_required_and_zero_valid(self):
        self.prep()
        for bad in (None, dict(opening=-1, employee='Eloy'), dict(opening=0, employee=' '), dict(opening='0', employee='x')):
            with self.assertRaises(ValueError):
                self.close(oc=bad)
        cid, version = self.close()
        self.assertEqual(version, 1)

    def test_reason_needed_for_difference(self):
        self.prep(counted=5000)
        with self.assertRaises(ValueError):
            self.close()
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(reason='faltan 10 cents'))
        self.close()

    def test_closed_immutable_and_versions(self):
        self.prep()
        self.close()
        s1 = ledger.display_snapshot(self.db.conn, DAY)
        self.assertEqual(s1['totals']['income'], 4990)
        with self.assertRaises(ValueError):
            self.manual('ingreso', 5)
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.conn.execute("INSERT INTO manual(id,day,type,concept,cents,name,number,employee,notes,created) "
                                 "VALUES ('x','%s','ingreso','c',1,'','','e','','t')" % DAY)
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.conn.execute('UPDATE closures SET snapshot=?', ('{}',))
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.conn.execute('DELETE FROM audit')
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.conn.execute('UPDATE audit SET action=?', ('x',))
        self.refresh([row('Q:1', 9999)])                     # Innux cambia después del cierre
        s2 = ledger.display_snapshot(self.db.conn, DAY)
        self.assertEqual(s2['totals']['income'], 4990)       # se muestra la instantánea del cierre
        self.assertTrue(s2['changed_since_close'])
        with self.db.tx() as c:
            ledger.reopen_day(c, ACTOR, DAY, 'Eloy', 'error')
        self.manual('ingreso', 7, name='z')
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(counted=9999 + 1007, reason='cambió Innux'))
        cid, version = self.close()
        self.assertEqual(version, 2)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM closures')['n'], 2)

    def test_second_closer_loses(self):
        self.prep()
        epoch = self.db.one('SELECT epoch FROM days')['epoch']
        self.close(epoch=epoch)
        with self.assertRaises((ledger.Conflict, ValueError)):
            self.close(epoch=epoch)

    def test_stale_or_missing_refresh_needs_reason(self):
        self.manual('ingreso', 1000)
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(counted=1000, employee='Eloy'))
        with self.assertRaises(ValueError):
            self.close()

    def test_days_stay_separate_and_dates_not_shifted(self):
        self.manual('ingreso', 500)
        other = self.db.one('SELECT 1 FROM manual WHERE day=?', ('2026-10-19',))
        self.assertIsNone(other)
        self.assertEqual(self.snap('2026-10-19')['totals']['income'], 0)



class TestOpeningCash(Base):
    """El dinero que hay en caja se pide al empezar cada día; cero es una respuesta válida."""

    def test_pending_until_confirmed_and_zero_counts(self):
        with self.db.tx() as c:
            self.assertFalse(ledger.opening_confirmed(c, DAY))
            self.assertTrue(ledger.confirm_opening(c, ACTOR, DAY, 0))
            self.assertTrue(ledger.opening_confirmed(c, DAY))
            self.assertFalse(ledger.opening_confirmed(c, '2026-10-19'))

    def test_existing_fund_counts_as_confirmed(self):
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(opening=5000))
            self.assertTrue(ledger.opening_confirmed(c, DAY))

    def test_saves_amount_changes_expected_and_is_audited(self):
        with self.db.tx() as c:
            ledger.confirm_opening(c, ACTOR, DAY, 12550)
        self.assertEqual(self.snap()['totals']['opening'], 12550)
        self.assertEqual(self.snap()['totals']['expected'], 12550)
        with self.db.tx() as c:
            rows = [dict(r) for r in c.execute("SELECT actor,detail FROM audit WHERE action='fondo_inicial_nuevo_dia'")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]['detail'])['opening'], 12550)

    def test_same_amount_is_idempotent_and_a_different_one_is_refused(self):
        with self.db.tx() as c:
            self.assertTrue(ledger.confirm_opening(c, ACTOR, DAY, 1000))
            self.assertFalse(ledger.confirm_opening(c, ACTOR, DAY, 1000))
            with self.assertRaises(ValueError):
                ledger.confirm_opening(c, ACTOR, DAY, 2000)
        self.assertEqual(self.snap()['totals']['opening'], 1000)

    def test_zero_then_a_different_amount_is_refused(self):
        with self.db.tx() as c:
            ledger.confirm_opening(c, ACTOR, DAY, 0)
            with self.assertRaises(ValueError):
                ledger.confirm_opening(c, ACTOR, DAY, 500)

    def test_invalid_values_and_closed_days_are_refused(self):
        with self.db.tx() as c:
            for bad in (-1, 1.5, '10', None, True, 10 ** 12):
                with self.assertRaises(ValueError):
                    ledger.confirm_opening(c, ACTOR, DAY, bad)
            self.assertFalse(ledger.opening_confirmed(c, DAY))
        self.refresh([row('Q:1', 3990)])
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(counted=3990, employee='Eloy'))
            put_setting(c, 'stale_minutes', 100000)
            ledger.close_day(c, ACTOR, DAY, dict(opening=0, employee='Eloy'))
            with self.assertRaises(ValueError):
                ledger.confirm_opening(c, ACTOR, DAY, 100)

    def test_last_closure_cash_is_only_a_hint(self):
        with self.db.tx() as c:
            self.assertIsNone(ledger.last_closure_cash(c))
        self.refresh([row('Q:1', 3990)])
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(counted=3990, employee='Eloy'))
            put_setting(c, 'stale_minutes', 100000)
            ledger.close_day(c, ACTOR, DAY, dict(opening=0, employee='Eloy'))
            self.assertEqual(ledger.last_closure_cash(c), dict(day=DAY, counted=3990))



class TestExcelAndImport(Base):
    def test_excel_literal_text_and_rows(self):
        self.refresh([row('Q:1', 3990), row('Q:2', 100, name='Bob %'), row('Q:3', 100, pending=True)])
        self.manual('ingreso', 1000, name='=HYPERLINK("http://x")', notes='+cmd|calc', number='5')
        self.manual('gasto', 250, name='-x', concept='Cable')
        snap = self.snap()
        blob = reports.day_workbook(snap)
        import zipfile, io
        z = zipfile.ZipFile(io.BytesIO(blob))
        sheet = z.read('xl/worksheets/sheet1.xml').decode()
        self.assertNotIn('<f>', sheet)
        self.assertIn('quotePrefix', z.read('xl/styles.xml').decode())
        sheets = xlsx.read_sheets(blob)
        caja = sheets['Caja']
        self.assertEqual(caja[1], {c: v for c, v in zip('ABCDEFG', ['Fecha', 'Efectivo', 'Concepto', 'Nombre', 'Nº socio', 'Gestionado por', 'Notas'])})
        values = sorted(Decimal(r['B']) for n, r in caja.items() if n > 1)
        self.assertEqual(values, [Decimal('-2.5'), Decimal('10'), Decimal('39.9')])   # solo lo que computa
        names = [r.get('D') for n, r in caja.items() if n > 1]
        self.assertIn('=HYPERLINK("http://x")', names)

    def test_month_has_totals_and_sheets(self):
        self.manual('ingreso', 1000)
        with self.db.tx() as c:
            ledger.save_day(c, ACTOR, DAY, dict(counted=1000, employee='Eloy', reason='sin consulta'))
        self.close_day()
        with self.db.tx() as c:
            blob = reports.month_workbook(c, '2026-10')
        sheets = xlsx.read_sheets(blob)
        self.assertEqual(set(sheets), {'Caja', 'Cierres', 'Información'})
        self.assertTrue(any(r.get('C') == 'Total neto del día' for r in sheets['Caja'].values()))
        with self.db.tx() as c:
            res = reports.compare_reference(c, blob, '2026-10')
        self.assertEqual(res['days'][0]['difference'], 0)

    def close_day(self):
        with self.db.tx() as c:
            ledger.close_day(c, ACTOR, DAY, dict(opening=0, employee='Eloy'))

    def test_import_idempotent_and_reconciled(self):
        data = dict(format='topfitness-caja-legacy-v1', exported_at='x', schema=[], admin_journal=[
            dict(request=dict(request_id=uid(), action='remove', client_id='1'), status='done', result={},
                 cash_snapshot=[row('Q:9', 100)])],
            tables=dict(days=[dict(day=DAY, opening=100, counted=None, employee='', notes='', reason='', coins='{}', closed=0)],
                        imports=[dict(day=DAY, key='Q:1', payload=json.dumps(row('Q:1', 3990)))],
                        refreshes=[], manual=[dict(id=uid(), day=DAY, type='ingreso', concept='c', cents=500, name='', number='',
                                                   employee='e', notes='', linked_key=None, source_ref=None, void=0,
                                                   created='t', request_id=None, category='custom', updated=None, client_id=None)],
                        closures=[], audit=[dict(id=7, created='t', action='a', detail='{"x":1}')], settings=[], suggestions=[]))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'legacy.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(importer.preview(path)['status'], 'vista_previa')
            fresh = DB(':memory:', upto=1)
            res = importer.run(fresh, path, commit=True)
            self.assertEqual(res['status'], 'importado')
            self.assertEqual(res['counts']['manual'], 1)
            self.assertEqual(importer.run(fresh, path, commit=True)['status'], 'ya_importado')
            self.assertEqual(fresh.one('SELECT COUNT(*) n FROM manual')['n'], 1)
            self.assertEqual(fresh.one('SELECT id FROM audit')['id'], 7)
            fresh.migrate()
            self.assertEqual(fresh.version(), 6)
            with self.assertRaises(sqlite3.DatabaseError):
                fresh.conn.execute('DELETE FROM audit')
            with self.assertRaises(ValueError):
                importer.run(fresh, path, commit=True)      # con protecciones activas no se importa


class TestHoja(Base):
    """Diario en rejilla (réplica del Excel): filas por celda, Innux que entra solo, turnos, cierre del día."""

    def setUp(self):
        super().setUp()
        from caja.db import today
        self.today = today()
        self.caja = ['register', 'view']
        self.boss = ['close', 'export', 'register', 'reopen', 'view']

    def save(self, fields, rid=None, day=None, perms=None):
        rid = rid or uid()
        with self.db.tx() as c:
            return hoja.save_row(c, ACTOR, perms or self.caja, day or self.today, rid, fields)

    def view(self, day=None, perms=None):
        with self.db.tx() as c:
            return hoja.day_view(c, dict(user_id=1, perms=perms or self.caja), day or self.today)

    def shift(self, counted=0, status='ok', note='', employee='Eloy', day=None, perms=None, coins=None):
        with self.db.tx() as c:
            return hoja.close_shift(c, ACTOR, perms or self.caja, day or self.today, employee, status, counted, note, coins)

    def close(self, day=None, opening=None, perms=None):
        with self.db.tx() as c:
            return hoja.close_day(c, ACTOR, perms or self.boss, day or self.today, 'Eloy', '', opening)

    def innux(self, *specs, day=None):
        """specs: (key, cents, number, concept)"""
        day = day or self.today
        rows = [row(k, cents, day=day, number=num, concept=con, name='Ana Gil € %s' % cents, current_name='Ana Gil € %s' % cents,
                    employee='Administrador') for k, cents, num, con in specs]
        self.refresh(rows, day=day)

    def test_rows_totals_and_order(self):
        a = self.save(dict(cents=3990, concept='renovacion', name='Ana Gil', number='100', employee='eloy'))
        self.save(dict(cents=600, concept='pase de dia'))
        self.save(dict(cents=-3000, concept='yoga'))
        v = self.view()
        self.assertEqual([r['pos'] for r in v['rows']], [1, 2, 3])
        self.assertEqual(v['totals'], dict(entries=4590, exits=3000, total=1590, count=3))
        self.assertTrue(v['editable'])
        self.save(dict(cents=4490, notes='con mant'), rid=a['id'])
        v = self.view()
        self.assertEqual(v['totals']['total'], 2090)
        self.assertEqual(v['rows'][0]['notes'], 'con mant')
        with self.db.tx() as c:
            acts = [r['action'] for r in c.execute('SELECT action FROM audit ORDER BY id')]
        self.assertEqual(acts.count('diario_fila'), 3)
        self.assertEqual(acts.count('diario_celda'), 1)

    def test_validation(self):
        for bad in (dict(), dict(cents=1.5), dict(cents='3'), dict(nope=1), dict(concept=5), dict(concept='x' * 201),
                    dict(cents=10 ** 11)):
            with self.assertRaises(ValueError, msg=bad):
                self.save(bad)
        with self.assertRaises(ValueError):
            self.save(dict(cents=100), rid='no-es-uuid')
        r = self.save(dict(cents=100, concept='  reno   vacion '))
        self.assertEqual(r['concept'], 'reno vacion')

    def test_void_removes_from_totals(self):
        r = self.save(dict(cents=500, concept='x'))
        with self.db.tx() as c:
            hoja.void_row(c, ACTOR, self.caja, self.today, r['id'])
        self.assertEqual(self.view()['totals']['total'], 0)
        with self.assertRaises(ValueError):
            self.save(dict(cents=1), rid=r['id'])
        with self.db.tx() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM audit WHERE action='diario_fila_eliminada'").fetchone()[0], 1)
            with self.assertRaises(sqlite3.DatabaseError):
                c.execute('DELETE FROM sheet_rows')

    def test_old_and_future_days(self):
        from datetime import date, timedelta
        t = date.fromisoformat(self.today)
        old = (t - timedelta(days=5)).isoformat()
        with self.assertRaises(ValueError):
            self.save(dict(cents=100), day=old)
        self.save(dict(cents=100), day=old, perms=self.boss)
        self.save(dict(cents=100), day=(t - timedelta(days=1)).isoformat())
        with self.assertRaises(ValueError):
            self.save(dict(cents=100), day=(t + timedelta(days=1)).isoformat(), perms=self.boss)
        self.assertFalse(self.view(day=old)['editable'])
        self.assertTrue(self.view(day=old, perms=self.boss)['editable'])
        self.assertFalse(self.view(perms=['view'])['editable'])

    def test_number_hint(self):
        self.save(dict(cents=3990, name='Mario Galatanu', number='5449'))
        b = self.save(dict(cents=3990, name='Nuria Iglesias', number='5449'))
        self.assertIn('Mario Galatanu', b['hint'])
        c = self.save(dict(cents=3990, name='mario  galatanu (boxeo)', number='5449'), rid=b['id'])
        self.assertIsNone(c['hint'])           # corregido el nombre, el aviso desaparece
        self.assertIsNone(self.save(dict(cents=1, name='Mario Galatanu', number='5449'))['hint'])

    def test_concepts_prices(self):
        with self.db.tx() as c:
            items = {i['text']: i for i in hoja.concepts(c)}
        self.assertEqual(items['renovacion']['cents'], 3990)
        self.assertEqual(items['alta']['cents'], 6480)
        self.assertEqual(items['renovacion + 3 mant']['cents'], 5490)
        self.assertTrue(items['yoga']['out'] and not items['renovacion']['out'])

    # ---- Innux entra solo
    def test_innux_rows_appear_once_and_are_editable(self):
        self.innux(('Q:1', 3990, '4920', 'Cuota 10/2026 · MENSUAL'))
        v = self.view()
        self.assertEqual(len(v['rows']), 1)
        r = v['rows'][0]
        self.assertEqual((r['employee'], r['concept'], r['cents'], r['number'], r['name'], r['source']),
                         ('INNUX', 'renovacion', 3990, '4920', 'Ana Gil', 'innux'))
        self.assertEqual(len(self.view()['rows']), 1)           # leer otra vez no duplica
        self.save(dict(cents=3790, notes='tarifa antigua'), rid=r['id'])
        self.assertEqual(self.view()['rows'][0]['cents'], 3790)
        self.innux(('Q:1', 3990, '4920', 'Cuota 10/2026 · MENSUAL'))
        self.assertEqual(self.view()['rows'][0]['cents'], 3790)  # lo editado no se pisa
        with self.db.tx() as c:
            hoja.void_row(c, ACTOR, self.caja, self.today, r['id'])
        self.assertEqual(len(self.view()['rows']), 0)            # borrada a propósito: no vuelve

    def test_innux_alta_groups_inscription_and_quota(self):
        self.innux(('Q:1', 3990, '6300', 'Cuota 10/2026 · MENSUAL'), ('L:2', 2490, '6300', 'Inscripción'))
        rows = self.view()['rows']
        self.assertEqual([(r['concept'], r['cents']) for r in rows], [('alta', 6480)])

    def test_innux_not_duplicated_when_staff_already_typed_it(self):
        self.save(dict(cents=3990, concept='renovacion', name='Ana Gil', number='4920', employee='lanu'))
        self.innux(('Q:1', 3990, '4920', 'Cuota 10/2026 · MENSUAL'))
        v = self.view()
        self.assertEqual(len(v['rows']), 1)
        self.assertEqual(v['totals']['total'], 3990)
        self.assertIsNone(v['rows'][0]['hint'])
        self.innux(('Q:1', 5000, '4920', 'Cuota 10/2026 · MENSUAL'))
        self.assertIn('Innux registra 50,00', self.view()['rows'][0]['hint'])      # importe distinto: se avisa
        with self.db.tx() as c:
            hoja.void_row(c, ACTOR, self.caja, self.today, v['rows'][0]['id'])
        rows = self.view()['rows']
        self.assertEqual([(r['employee'], r['cents']) for r in rows], [('INNUX', 5000)])   # la manual se borró: entra Innux

    def test_innux_late_manual_twin_is_flagged(self):
        self.innux(('Q:1', 3990, '4920', 'Cuota 10/2026 · MENSUAL'))
        self.view()
        self.save(dict(cents=3990, name='Ana Gil', number='4920', employee='lanu'))
        hints = [r['hint'] for r in self.view()['rows']]
        self.assertTrue(any(h and 'duplicado' in h for h in hints), hints)

    def test_innux_ignores_domiciliation_and_pending(self):
        rows = [row('Q:1', 3990, day=self.today, name='Pepe %', current_name='Pepe %'),
                row('Q:2', 3990, day=self.today, pending=True, number='9'),
                row('Q:3', 3990, day=self.today, payment='TARJETA', number='10')]
        self.refresh(rows, day=self.today)
        self.assertEqual(len(self.view()['rows']), 0)

    def test_innux_name_cleaning(self):
        for raw, clean in (('Ana Gil % 39,9', 'Ana Gil'), ('Su Perez 39,90', 'Su Perez'), ('Ri Reis %', 'Ri Reis'),
                           ('Juan  Luis €', 'Juan Luis'), ('', '')):
            self.assertEqual(hoja.clean_name(raw), clean)

    # ---- turnos y cierre del día
    def test_shift_close_requires_counted_and_note_when_wrong(self):
        self.save(dict(cents=3990, concept='renovacion'))
        for bad in (dict(counted=None), dict(counted=-1), dict(counted='5'), dict(counted=100, status='raro'),
                    dict(counted=100, status='revisar', note=''), dict(counted=100, employee=''),
                    dict(counted=100, coins=dict(x=1)), dict(counted=100, coins=dict(**{'5': -1}))):
            with self.assertRaises(ValueError, msg=bad):
                self.shift(**bad)
        sid = self.shift(counted=3990, coins={'20': 1, '10': 1})
        v = self.view()
        s = v['shifts'][0]
        self.assertEqual((s['id'], s['status'], s['counted'], s['expected'], s['after_pos'], s['employee']), (sid, 'ok', 3990, 3990, 1, 'Eloy'))
        self.assertEqual(s['coins'], {'20': 1, '10': 1})
        self.assertFalse(v['unclosed'])
        self.save(dict(cents=600, concept='pase de dia'))
        self.assertTrue(self.view()['unclosed'])                    # apunte nuevo tras el cierre del turno
        self.shift(counted=4590, status='revisar', note='sobra algo', employee='Ana')
        v = self.view()
        self.assertEqual([s['employee'] for s in v['shifts']], ['Eloy', 'Ana'])
        self.assertFalse(v['unclosed'])

    def test_edit_after_shift_close_marks_unclosed(self):
        r = self.save(dict(cents=3990, concept='renovacion'))
        self.shift(counted=3990)
        self.assertFalse(self.view()['unclosed'])
        self.save(dict(cents=3790), rid=r['id'])
        self.assertTrue(self.view()['unclosed'])

    def test_undo_last_shift_only(self):
        self.save(dict(cents=100))
        a = self.shift(counted=100)
        b = self.shift(counted=100, employee='Ana')
        with self.db.tx() as c:
            with self.assertRaises(ValueError):
                hoja.void_shift(c, ACTOR, self.caja, self.today, a)
            hoja.void_shift(c, ACTOR, self.caja, self.today, b)
        self.assertEqual([s['id'] for s in self.view()['shifts']], [a])

    def test_close_day_flow_locks_and_snapshots(self):
        with self.db.tx() as c:
            ledger.confirm_opening(c, ACTOR, self.today, 5000)
        self.save(dict(cents=3990, concept='renovacion', name='Ana', number='1'))
        with self.assertRaises(ValueError):
            self.close()                                            # sin cierre de turno
        self.shift(counted=8990)
        self.save(dict(cents=600, concept='pase de dia'))
        with self.assertRaises(ValueError):
            self.close()                                            # apunte posterior al cierre de turno
        self.shift(counted=9590, employee='Ana')
        cid, version = self.close()
        self.assertEqual(version, 1)
        v = self.view()
        self.assertTrue(v['closed'] and not v['editable'])
        self.assertEqual(v['closure']['id'], cid)
        for call in (lambda: self.save(dict(cents=1)), lambda: self.shift(counted=1)):
            with self.assertRaises(ValueError):
                call()
        with self.db.tx() as c:
            snap = json.loads(c.execute('SELECT snapshot FROM sheet_closures WHERE id=?', (cid,)).fetchone()[0])
            self.assertEqual((snap['opening'], snap['totals']['total'], len(snap['rows']), len(snap['shifts'])), (5000, 4590, 2, 2))
            with self.assertRaises(sqlite3.DatabaseError):
                c.execute('UPDATE sheet_closures SET actor="x"')
            with self.assertRaises(sqlite3.DatabaseError):
                c.execute("INSERT INTO sheet_rows(id,day,pos,cents,created,updated) VALUES ('z',?,9,1,'a','a')", (self.today,))
            hoja.sync_innux(c, self.today)                           # un día cerrado no cambia
        with self.db.tx() as c:
            with self.assertRaises(ValueError):
                hoja.reopen_day(c, ACTOR, self.boss, self.today, 'Eloy', '')      # motivo obligatorio
            hoja.reopen_day(c, ACTOR, self.boss, self.today, 'Eloy', 'faltaba un apunte')
        self.assertTrue(self.view()['editable'])
        self.save(dict(cents=100))
        self.shift(counted=9690, employee='Ana')
        self.assertEqual(self.close()[1], 2)

    def test_close_asks_opening_for_unconfirmed_day(self):
        self.save(dict(cents=100))
        self.shift(counted=100)
        with self.assertRaises(ValueError):
            self.close()
        self.assertEqual(self.close(opening=0)[1], 1)
        self.assertTrue(self.view()['opening_confirmed'])

    def test_history_has_no_totals_and_filters(self):
        self.save(dict(cents=3990, concept='renovacion', name='Ana Gil', number='7', employee='eloy'))
        self.save(dict(cents=-3000, concept='yoga'))
        with self.db.tx() as c:
            h = hoja.history(c, self.today[:7])
            self.assertEqual(len(h), 1)
            self.assertEqual([r['cents'] for r in h[0]['rows']], [3990, -3000])
            self.assertNotIn('total', h[0])
            self.assertEqual(len(hoja.history(c, self.today[:7], 'ANA gil')[0]['rows']), 1)
            self.assertEqual(hoja.history(c, self.today[:7], 'nadie'), [])
            with self.assertRaises(ValueError):
                hoja.history(c, '2026-13')

    def test_history_excel_wins_until_its_last_day_then_live_rows(self):
        from datetime import date, timedelta
        t = date.fromisoformat(self.today)
        d1, d2 = (t - timedelta(days=2)).isoformat(), (t - timedelta(days=1)).isoformat()
        ex = [dict(period=d[:7], idx=i, day=d, cents=c, concept='renovacion', name=n, number='9', employee='lanu', notes='')
              for i, (d, c, n) in enumerate([(d1, 3990, 'Excel Uno'), (d2, 3790, 'Excel Dos'), (d2, 600, 'Excel Tres')])]
        with self.db.tx() as c:
            res = hoja.import_history(c, ex, d2)
            self.assertEqual(res, dict(filas=3, hasta=d2))
            with self.assertRaises(ValueError):
                hoja.import_history(c, [dict(period='x', idx=0, day=d1, cents=1)], d2)
        self.save(dict(cents=111, concept='yoga', name='Rejilla ayer'), day=d2)      # día cubierto por el Excel: se ignora
        self.save(dict(cents=222, concept='pase de dia', name='Rejilla hoy'))        # después del Excel: vale la rejilla
        with self.db.tx() as c:
            month = {}
            for m in {d1[:7], self.today[:7]}:
                for d in hoja.history(c, m):
                    month[d['day']] = [r['name'] for r in d['rows']]
            self.assertEqual(month, {d1: ['Excel Uno'], d2: ['Excel Dos', 'Excel Tres'], self.today: ['Rejilla hoy']})
            found = hoja.history(c, self.today[:7], 'excel')                        # con búsqueda: todos los meses, lo más reciente primero
            self.assertEqual([x['day'] for x in found], [d2, d1])
            self.assertEqual(hoja.history(c, self.today[:7], 'rejilla ayer'), [])
            self.assertEqual(hoja.history(c, '2025-01'), [])

    def test_month_workbook(self):
        self.save(dict(cents=3990, concept='renovacion', name='Ana', number='1', employee='eloy'))
        self.save(dict(cents=-3000, concept='yoga'))
        self.shift(counted=5000)
        with self.db.tx() as c:
            blob = hoja.month_workbook(c, self.today[:7])
        sheets = xlsx.read_sheets(blob)
        name = next(iter(sheets))
        self.assertRegex(name, r'^[A-Z]+ \d\d$')
        rows = sheets[name]
        self.assertEqual(rows[1]['B'], 'efectivo')
        self.assertEqual(rows[2]['C'], 'renovacion')
        self.assertEqual(rows[3]['B'], Decimal('-30'))
        self.assertEqual((rows[4]['A'], rows[4]['B']), ('total', Decimal('9.9')))
        self.assertIn('cierre ok Eloy 50,00', rows[4]['G'])


class TestHTTP(unittest.TestCase):
    """Servidor real en loopback: sesión, CSRF, origen y contrato del puente."""

    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        from caja import server
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['CAJA_DATA'] = cls.tmp.name
        os.environ['CAJA_COOKIE_SECURE'] = '0'
        cls.cfg = server.Config()
        cls.app = server.App(cls.cfg)
        with cls.app.db.tx() as c:
            auth.create_user(c, 'ana', 'Ana', 'admin', 'contraseña-larga-1')
            auth.create_user(c, 'solo', 'Solo', 'consulta', 'contraseña-larga-2')
            cls.token = bridge.provision_device(c)
        server.Handler.app = cls.app
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.httpd.daemon_threads = True
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:%d/alta/caja' % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.app.db.conn.close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, headers=None, cookie=None, csrf=None, origin=True):
        h = {'Content-Type': 'application/json'}
        if origin:
            h['Origin'] = self.cfg.origin
        if cookie:
            h['Cookie'] = cookie
        if csrf:
            h['X-CSRF-Token'] = csrf
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     method=method, headers=h)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.headers, json.loads(r.read() or b'null')
        except urllib.error.HTTPError as e:
            return e.code, e.headers, json.loads(e.read() or b'null')

    def login(self, user='ana', password='contraseña-larga-1'):
        status, headers, body = self.call('POST', '/api/login', dict(username=user, password=password))
        self.assertEqual(status, 200, body)
        return headers['Set-Cookie'].split(';')[0], body['csrf'], headers['Set-Cookie']

    def test_session_csrf_origin_roles(self):
        status, _, _ = self.call('GET', '/api/me')
        self.assertEqual(status, 401)
        self.assertEqual(self.call('POST', '/api/login', dict(username='ana', password='mala'))[0], 401)
        cookie, csrf, raw = self.login()
        for flag in ('HttpOnly', 'SameSite=Strict'):
            self.assertIn(flag, raw)
        self.assertEqual(self.call('GET', '/api/me', cookie=cookie)[0], 200)
        body = dict(request_id=str(uuid.uuid4()), day=DAY, option='yoga', cents=3000, concept='Yoga', employee='Eloy')
        self.assertEqual(self.call('POST', '/api/outflow', body, cookie=cookie)[0], 403)                 # sin CSRF
        self.assertEqual(self.call('POST', '/api/outflow', body, cookie=cookie, csrf=csrf, origin=False)[0], 403)
        self.assertEqual(self.call('POST', '/api/outflow', body, cookie=cookie, csrf=csrf)[0], 200)
        status, _, day = self.call('GET', '/api/day/' + DAY, cookie=cookie)
        self.assertEqual(day['day']['totals']['expenses'], 3000)
        c2, s2, _ = self.login('solo', 'contraseña-larga-2')
        self.assertEqual(self.call('POST', '/api/outflow', dict(body, request_id=str(uuid.uuid4())), cookie=c2, csrf=s2)[0], 403)

    def test_hoja_over_http(self):
        from caja.db import today
        from datetime import date, timedelta
        t = (date.fromisoformat(today()) - timedelta(days=1)).isoformat()   # ayer: no toca el dinero inicial de hoy
        cookie, csrf, _ = self.login()
        rid = str(uuid.uuid4())
        url = '/api/hoja/%s/row' % t
        row = dict(id=rid, fields=dict(cents=3990, concept='renovacion'))
        self.assertEqual(self.call('POST', url, row, cookie=cookie)[0], 403)                           # sin CSRF
        self.assertEqual(self.call('POST', url, row, cookie=cookie, csrf=csrf)[0], 200)
        self.assertEqual(self.call('POST', url, dict(id=rid, fields=dict(cents='x')), cookie=cookie, csrf=csrf)[0], 400)
        s, _, body = self.call('GET', '/api/hoja/' + t, cookie=cookie)
        self.assertEqual((s, body['hoja']['totals']['total']), (200, 3990))
        c2, s2, _ = self.login('solo', 'contraseña-larga-2')
        self.assertEqual(self.call('GET', '/api/hoja/' + t, cookie=c2)[0], 200)                          # consulta puede ver
        self.assertEqual(self.call('POST', url, dict(id=str(uuid.uuid4()), fields=dict(cents=1)), cookie=c2, csrf=s2)[0], 403)
        sh = '/api/hoja/%s/shift' % t
        self.assertEqual(self.call('POST', sh, dict(employee='Eloy', status='ok'), cookie=cookie, csrf=csrf)[0], 400)   # falta lo contado
        self.assertEqual(self.call('POST', sh, dict(employee='Eloy', status='ok', counted=3990), cookie=c2, csrf=s2)[0], 403)
        s, _, body = self.call('POST', sh, dict(employee='Eloy', status='ok', counted=3990), cookie=cookie, csrf=csrf)
        self.assertEqual(s, 200, body)
        self.assertEqual(self.call('POST', '/api/hoja/%s/close' % t, dict(employee='Eloy', opening=0), cookie=c2, csrf=s2)[0], 403)
        s, _, body = self.call('POST', '/api/hoja/%s/close' % t, dict(employee='Eloy', opening=0), cookie=cookie, csrf=csrf)
        self.assertEqual(s, 200, body)
        s, _, body = self.call('GET', '/api/hoja/' + t, cookie=cookie)
        self.assertTrue(body['hoja']['closed'] and not body['hoja']['editable'])
        self.assertEqual(self.call('POST', url, dict(id=rid, fields=dict(cents=5)), cookie=cookie, csrf=csrf)[0], 400)   # día cerrado
        s, _, body = self.call('GET', '/api/diary/' + t[:7], cookie=cookie)                                              # lo lee el Centro de control
        self.assertEqual([(d['day'], d['closed'], d['rows'][0]['cents']) for d in body['days'] if d['day'] == t], [(t, True, 3990)])
        s, _, body = self.call('GET', '/api/hoja/historial/' + t[:7] + '?q=reno', cookie=c2)
        self.assertEqual((s, body['days'][0]['rows'][0]['concept']), (200, 'renovacion'))
        self.assertEqual(self.call('GET', '/api/hoja/historial/2026-13', cookie=cookie)[0], 400)
        self.assertEqual(self.call('POST', '/api/hoja/%s/reopen' % t, dict(employee='Eloy', reason='prueba'), cookie=c2, csrf=s2)[0], 403)
        self.assertEqual(self.call('POST', '/api/hoja/%s/reopen' % t, dict(employee='Eloy', reason='prueba'), cookie=cookie, csrf=csrf)[0], 200)
        self.assertEqual(self.call('POST', '/api/hoja/%s/row/%s/void' % (t, rid), {}, cookie=cookie, csrf=csrf)[0], 200)
        self.assertTrue(self.call('GET', '/api/me', cookie=cookie)[2]['build'])

    def test_opening_asked_only_from_configured_hour(self):
        from caja.db import today
        cookie, csrf, _ = self.login()
        with self.app.db.tx() as c:
            put_setting(c, 'opening_hour', 24)                 # nunca antes de «las 24 h»
        self.assertFalse(self.call('GET', '/api/me', cookie=cookie)[2]['opening_pending'])
        with self.app.db.tx() as c:
            put_setting(c, 'opening_hour', 0)
        self.assertTrue(self.call('GET', '/api/me', cookie=cookie)[2]['opening_pending'])
        for bad in (-1, 24, '12', None, 1.5):
            self.assertEqual(self.call('POST', '/api/settings', dict(opening_hour=bad), cookie=cookie, csrf=csrf)[0], 400, bad)
        self.assertEqual(self.call('POST', '/api/settings', dict(opening_hour=12), cookie=cookie, csrf=csrf)[0], 200)
        with self.app.db.tx() as c:
            self.assertEqual(setting(c, 'opening_hour'), 12)
            put_setting(c, 'opening_hour', 0)                  # el resto de pruebas dan por hecha la hora cumplida

    def test_opening_cash_flow_over_http(self):
        from caja.db import today
        t = today()
        with self.app.db.tx() as c:
            put_setting(c, 'opening_hour', 0)
        cookie, csrf, _ = self.login()
        s, _, me = self.call('GET', '/api/me', cookie=cookie)
        self.assertEqual((s, me['today'], me['opening_pending']), (200, t, True))
        url = '/api/day/%s/opening' % t
        self.assertEqual(self.call('POST', url, dict(opening=1000), cookie=cookie)[0], 403)                    # sin CSRF
        self.assertEqual(self.call('POST', url, dict(opening=1000), cookie=cookie, csrf=csrf, origin=False)[0], 403)
        c2, s2, _ = self.login('solo', 'contraseña-larga-2')
        self.assertEqual(self.call('POST', url, dict(opening=1000), cookie=c2, csrf=s2)[0], 403)              # solo consulta
        for bad in (-1, 'x', None, 1.5):
            self.assertEqual(self.call('POST', url, dict(opening=bad), cookie=cookie, csrf=csrf)[0], 400, bad)
        self.assertEqual(self.call('POST', '/api/day/%s/opening' % DAY, dict(opening=1000), cookie=cookie, csrf=csrf)[0], 400)  # solo hoy
        self.assertTrue(self.call('GET', '/api/me', cookie=cookie)[2]['opening_pending'])
        self.assertEqual(self.call('POST', url, dict(opening=0), cookie=cookie, csrf=csrf)[0], 200)             # cero vale
        s, _, me = self.call('GET', '/api/me', cookie=cookie)
        self.assertFalse(me['opening_pending'])
        self.assertFalse(self.call('GET', '/api/me', cookie=c2)[2]['opening_pending'])                          # lo ve todo el mundo
        self.assertEqual(self.call('POST', url, dict(opening=0), cookie=cookie, csrf=csrf)[0], 200)             # idempotente
        self.assertEqual(self.call('POST', url, dict(opening=700), cookie=cookie, csrf=csrf)[0], 400)           # otro importe: no
        self.assertEqual(self.call('GET', '/api/day/' + t, cookie=cookie)[2]['day']['totals']['opening'], 0)

    def test_initial_password_flow(self):
        with self.app.db.tx() as c:
            auth.create_user(c, 'nuevo', 'Nuevo', 'caja', 'inicial-larga-123', must_change=True)
        cookie, csrf, _ = self.login('nuevo', 'inicial-larga-123')
        s, _, me = self.call('GET', '/api/me', cookie=cookie)
        self.assertEqual((s, me['user']['must_change']), (200, True))
        self.assertEqual(self.call('GET', '/api/day/' + DAY, cookie=cookie)[0], 403)
        s, _, _ = self.call('POST', '/api/password', dict(old='inicial-larga-123', new='definitiva-larga-456'), cookie=cookie, csrf=csrf)
        self.assertEqual(s, 200)
        cookie, csrf, _ = self.login('nuevo', 'definitiva-larga-456')
        self.assertEqual(self.call('GET', '/api/day/' + DAY, cookie=cookie)[0], 200)

    def test_wrong_current_password_keeps_session_and_explains(self):
        # F-10: la contraseña actual incorrecta no es una sesión caducada (no puede ser 401, que cierra la sesión en el cliente).
        with self.app.db.tx() as c:
            auth.create_user(c, 'cambia', 'Cambia', 'caja', 'inicial-larga-123', must_change=True)
        cookie, csrf, _ = self.login('cambia', 'inicial-larga-123')
        s, _, body = self.call('POST', '/api/password', dict(old='no-es-esta', new='definitiva-larga-456'), cookie=cookie, csrf=csrf)
        self.assertEqual(s, 403)
        self.assertIn('contraseña actual', body['error'])
        self.assertEqual(self.call('GET', '/api/me', cookie=cookie)[0], 200)             # la sesión sigue viva
        self.assertEqual(self.call('POST', '/api/password', dict(old='inicial-larga-123', new='definitiva-larga-456'), cookie=cookie, csrf=csrf)[0], 200)

    def test_head_requests(self):
        # F-12: los monitores de disponibilidad usan HEAD; el servidor responde sin cuerpo y sin abrir la API.
        import http.client
        host, port = self.httpd.server_address
        def head(path):
            c = http.client.HTTPConnection(host, port, timeout=5)
            c.request('HEAD', path)
            r = c.getresponse(); body = r.read(); c.close()
            return r.status, r.getheader('Content-Length'), body
        s, length, body = head('/alta/caja/healthz')
        self.assertEqual((s, body), (200, b'')); self.assertGreater(int(length), 0)
        self.assertEqual(head('/alta/caja/')[0], 200)
        self.assertEqual(head('/alta/caja/')[2], b'')
        self.assertEqual(head('/alta/caja/api/me')[0], 405)
        self.assertEqual(head('/alta/caja/bridge/v1/poll')[0], 405)

    def sso_ticket(self, **over):
        from caja import sso
        key = b'k' * 40
        with open(self.cfg.sso_key_file, 'wb') as f:
            f.write(key)
        t = int(__import__('time').time())
        payload = dict(mod='caja', sub='maria', name='María López', role='responsable', iat=t, exp=t + 60, jti=uuid.uuid4().hex)
        payload.update(over)
        return sso.sign(over.pop('_key', key), payload)

    def test_sso_from_control_center(self):
        # F-06: la persona entra con SU identidad y SU rol, no con un usuario de servicio con todos los permisos.
        os.makedirs(os.path.dirname(self.cfg.sso_key_file), exist_ok=True)
        ticket = self.sso_ticket()
        s, h, body = self.call('POST', '/api/sso', dict(ticket=ticket))
        self.assertEqual(s, 200, body)
        cookie = h['Set-Cookie'].split(';')[0]
        s, _, me = self.call('GET', '/api/me', cookie=cookie)
        self.assertEqual(me['user']['username'], 'cc.maria')
        self.assertEqual(me['user']['role'], 'responsable')
        self.assertNotIn('reopen', me['user']['perms'])           # permisos del rol, no de administrador
        self.assertIn('close', me['user']['perms'])
        # un solo uso
        self.assertEqual(self.call('POST', '/api/sso', dict(ticket=ticket))[0], 401)
        # la auditoría identifica a la persona real
        with self.app.db.tx() as c:
            rows = [r['actor'] for r in c.execute("SELECT actor FROM audit WHERE action='login_sso'")]
        self.assertTrue(any('María López' in a and 'cc.maria' in a for a in rows), rows)
        # el rol se refresca en cada entrada y la cuenta SSO no admite contraseña
        t2 = self.sso_ticket(role='consulta')
        cookie2 = self.call('POST', '/api/sso', dict(ticket=t2))[1]['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('GET', '/api/me', cookie=cookie2)[2]['user']['role'], 'consulta')
        self.assertEqual(self.call('POST', '/api/login', dict(username='cc.maria', password='lo-que-sea-1234'))[0], 401)

    def test_sso_rejections(self):
        from caja import sso
        os.makedirs(os.path.dirname(self.cfg.sso_key_file), exist_ok=True)
        t = int(__import__('time').time())
        for name, over in [('caducado', dict(iat=t - 300, exp=t - 200)), ('otro módulo', dict(mod='altas')),
                           ('rol inventado', dict(role='superadmin')), ('rol de personal normal', dict(role='caja')),
                           ('ticket de larga duración', dict(exp=t + 3600)), ('sujeto raro', dict(sub='../x'))]:
            self.assertEqual(self.call('POST', '/api/sso', dict(ticket=self.sso_ticket(**over)))[0], 401, name)
        good = self.sso_ticket()
        tampered = good[:-3] + ('aaa' if not good.endswith('aaa') else 'bbb')
        self.assertEqual(self.call('POST', '/api/sso', dict(ticket=tampered))[0], 401)
        forged = sso.sign(b'x' * 40, dict(mod='caja', sub='eve', name='Eve', role='admin', iat=t, exp=t + 60, jti='z1'))
        self.assertEqual(self.call('POST', '/api/sso', dict(ticket=forged))[0], 401)
        self.assertEqual(self.call('POST', '/api/sso', dict(ticket='basura'))[0], 401)
        # una cuenta de personal normal con ese nombre nunca se sobrescribe
        with self.app.db.tx() as c:
            auth.create_user(c, 'cc.pepe', 'Pepe', 'caja', 'contraseña-larga-9')
        self.assertEqual(self.call('POST', '/api/sso', dict(ticket=self.sso_ticket(sub='pepe')))[0], 401)

    def test_sso_not_configured_is_refused(self):
        try:
            os.unlink(self.cfg.sso_key_file)
        except OSError:
            pass
        t = int(__import__('time').time())
        from caja import sso
        tk = sso.sign(b'k' * 40, dict(mod='caja', sub='maria', name='M', role='responsable', iat=t, exp=t + 60, jti='n1'))
        self.assertEqual(self.call('POST', '/api/sso', dict(ticket=tk))[0], 401)

    def test_clients_session_does_not_open_a_cash_day(self):
        from unittest.mock import patch
        cookie, csrf, _ = self.login()
        with self.app.db.tx() as c:
            before = [tuple(r) for r in c.execute('SELECT * FROM days ORDER BY day')]
        with patch('caja.server.today', return_value='2099-01-01'):
            status, _, body = self.call('GET', '/api/me?clients=1', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(body['user']['username'], 'ana')
        self.assertFalse(body['opening_pending'])
        with self.app.db.tx() as c:
            self.assertEqual(before, [tuple(r) for r in c.execute('SELECT * FROM days ORDER BY day')])

    def test_bridge_contract(self):
        auth_h = {'Authorization': 'Bearer ' + self.token}
        poll = dict(device_id=bridge.DEVICE_ID, protocol_version=1, agent_version='1.0.0', capabilities=list(bridge.CAPS))
        s, h, b = self.call('POST', '/bridge/v1/poll', poll, headers=auth_h, origin=False)
        self.assertEqual((s, b), (200, dict(ok=True, job=None)))
        self.assertEqual(h.get_content_type(), 'application/json')
        self.assertEqual(self.call('POST', '/bridge/v1/poll', poll, headers={'Authorization': 'Bearer ' + 'a' * 48}, origin=False)[0], 401)
        self.assertEqual(self.call('POST', '/bridge/v1/poll', poll, origin=False)[0], 401)
        cookie, csrf, _ = self.login()      # la cookie de personal no sustituye al token
        self.assertEqual(self.call('POST', '/bridge/v1/poll', poll, cookie=cookie, origin=False)[0], 401)
        s, _, b = self.call('POST', '/api/clients/search', dict(query='ana'), cookie=cookie, csrf=csrf)
        job_id = b['job_id']
        s, _, b = self.call('POST', '/bridge/v1/poll', poll, headers=auth_h, origin=False)
        self.assertEqual(set(b['job']), {'id', 'operation', 'payload'})
        res = dict(device_id=bridge.DEVICE_ID, protocol_version=1, job_id=job_id, operation='clients.search',
                   fingerprint='f', status='succeeded', final=True, result=dict(clients=[]), error=None,
                   completed_at='2026-10-18T10:00:00+02:00')
        s, _, b = self.call('POST', '/bridge/v1/result', res, headers=auth_h, origin=False)
        self.assertEqual((s, b), (200, dict(acknowledged=True, job_id=job_id)))
        s, _, b = self.call('GET', '/api/jobs/' + job_id, cookie=cookie)
        self.assertEqual(b['job']['status'], 'succeeded')


if __name__ == '__main__':
    unittest.main()
