"""Pruebas del remitente push contra tf_test_reservas (BD aislada) con un envío simulado. Ejecutar: tests/run_push.sh"""
import os, sys, socket, unittest, json
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "push"))
import push_sender as ps

CFG = {"db_socket": "/run/mysqld/mysqld.sock", "db_user": "root", "db_name": "tf_test_reservas"}
assert "test" in CFG["db_name"]
db = ps.connect(CFG)
ps.set_tz(db)
Q = lambda s, a=(): ps.q(db, s, a)[0]
DAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


def reset():
    for t in ("tf_push_outbox", "tf_notify_events", "tf_offers", "tf_push_subscriptions", "tf_devices", "tf_notify_audit", "tf_bookings", "tf_people", "inscripciones", "clases_canceladas", "horarios"):
        Q(f"DELETE FROM {t}")
    Q("UPDATE tf_notify_settings SET v='1' WHERE k='PUSH_SEND_ENABLED'")
    Q("UPDATE tf_notify_settings SET v='' WHERE k='PUSH_ALLOW_PERSONS'")


def fixture(hours_ahead=5):
    """Persona + móvil + suscripción + clase que empieza dentro de `hours_ahead` horas (hora de Madrid)."""
    start = Q("SELECT NOW() + INTERVAL %s HOUR n", (hours_ahead,))[0]["n"].replace(second=0, microsecond=0)
    Q("INSERT INTO tf_people(nombre,telefono) VALUES('Ana Prueba','612345678')")
    pid = Q("SELECT LAST_INSERT_ID() i")[0]["i"]
    Q("INSERT INTO tf_devices(person_id,token_hash) VALUES(%s,%s)", (pid, "a" * 64))
    did = Q("SELECT LAST_INSERT_ID() i")[0]["i"]
    Q("INSERT INTO tf_push_subscriptions(device_id,endpoint_hash,endpoint,p256dh,auth_secret) VALUES(%s,%s,'https://fcm.googleapis.com/fcm/send/x','k','a')", (did, "b" * 64))
    sid = Q("SELECT LAST_INSERT_ID() i")[0]["i"]
    Q("INSERT INTO horarios(clase,dia,hora,limite) VALUES('Yoga',%s,%s,10)", (DAYS[start.weekday()], start.strftime("%H:%M") + "-" + (start + timedelta(hours=1)).strftime("%H:%M")))
    hid = Q("SELECT LAST_INSERT_ID() i")[0]["i"]
    return dict(pid=pid, did=did, sid=sid, hid=hid, start=start, fecha=start.strftime("%Y-%m-%d"))


def event(f, kind, ttl=600, **kw):
    Q("INSERT INTO tf_notify_events(kind,person_id,booking_id,offer_id,horario_id,fecha,dedupe_key,not_before,ttl_at,link_token) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW() + INTERVAL %s SECOND,%s)",
      (kind, f["pid"], kw.get("booking_id"), kw.get("offer_id"), kw.get("horario_id"), kw.get("fecha"), os.urandom(8).hex(), kw.get("not_before", Q("SELECT NOW() - INTERVAL 1 MINUTE n")[0]["n"]), ttl, kw.get("link_token")))
    eid = Q("SELECT LAST_INSERT_ID() i")[0]["i"]
    Q("INSERT INTO tf_push_outbox(event_id,subscription_id) VALUES(%s,%s)", (eid, f["sid"]))
    return eid, Q("SELECT LAST_INSERT_ID() i")[0]["i"]


class Sender:
    def __init__(self, *codes): self.codes = list(codes) or [201]; self.sent = []
    def __call__(self, sub, data, ttl):
        self.sent.append((data, ttl)); c = self.codes.pop(0) if len(self.codes) > 1 else self.codes[0]
        if c == 0: raise OSError("red")
        return c


def ob(i): return Q("SELECT * FROM tf_push_outbox WHERE id=%s", (i,))[0]


class T(unittest.TestCase):
    def setUp(self): reset()

    def test_test_event_sent_and_marked(self):
        f = fixture(); e, o = event(f, "TEST"); s = Sender(201)
        ps.process_once(db, CFG, s)
        self.assertEqual(ob(o)["status"], "ACCEPTED"); self.assertIsNotNone(Q("SELECT test_sent_at t FROM tf_push_subscriptions")[0]["t"])
        self.assertEqual(len(s.sent), 1); self.assertIsNone(Q("SELECT test_confirmed_at t FROM tf_push_subscriptions")[0]["t"])

    def test_switch_off_only_allowed_people(self):
        f = fixture(); e, o = event(f, "TEST"); Q("UPDATE tf_notify_settings SET v='0' WHERE k='PUSH_SEND_ENABLED'"); s = Sender()
        ps.process_once(db, CFG, s); self.assertEqual((len(s.sent), ob(o)["status"]), (0, "PENDING"))
        Q("UPDATE tf_notify_settings SET v=%s WHERE k='PUSH_ALLOW_PERSONS'", (str(f["pid"]),))
        ps.process_once(db, CFG, s); self.assertEqual(ob(o)["status"], "ACCEPTED")

    def test_expired_ttl_is_never_sent(self):
        f = fixture(); e, o = event(f, "TEST", ttl=-5); s = Sender()
        ps.process_once(db, CFG, s); self.assertEqual((len(s.sent), ob(o)["status"]), (0, "EXPIRED"))

    def test_gone_subscription_removed_and_incident_logged(self):
        f = fixture(); e, o = event(f, "TEST"); ps.process_once(db, CFG, Sender(410))
        self.assertEqual(Q("SELECT status FROM tf_push_subscriptions")[0]["status"], "EXPIRED")
        self.assertEqual(Q("SELECT COUNT(*) n FROM tf_notify_audit WHERE action='PUSH_FAILED'")[0]["n"], 1)

    def test_transient_error_retries_then_gives_up(self):
        f = fixture(); e, o = event(f, "TEST", ttl=86400); s = Sender(503)
        for i in range(5):
            Q("UPDATE tf_push_outbox SET next_attempt_at=NOW() WHERE id=%s AND status='PENDING'", (o,)); ps.process_once(db, CFG, s)
            if i < 4: self.assertEqual(ob(o)["status"], "PENDING")
        self.assertEqual((ob(o)["status"], ob(o)["attempts"], len(s.sent)), ("FAILED", 5, 5))
        self.assertEqual(ob(o)["last_error"], "RETRIES_EXHAUSTED")

    def test_network_error_is_retried(self):
        f = fixture(); e, o = event(f, "TEST"); ps.process_once(db, CFG, Sender(0)); self.assertEqual((ob(o)["status"], ob(o)["last_error"]), ("PENDING", "NETWORK"))

    def reminder(self, f):
        Q("INSERT INTO inscripciones(nombre,telefono,horario_id,fecha) VALUES('Ana Prueba','612345678',%s,%s)", (f["hid"], f["fecha"]))
        rid = Q("SELECT LAST_INSERT_ID() i")[0]["i"]
        return rid, event(f, "REMINDER", booking_id=rid, horario_id=f["hid"], fecha=f["fecha"], not_before=f["start"] - timedelta(hours=2))

    def test_reminder_valid_has_class_date_time_and_no_personal_data(self):
        f = fixture(2); rid, (e, o) = self.reminder(f); s = Sender(); ps.process_once(db, CFG, s)
        self.assertEqual(ob(o)["status"], "ACCEPTED"); body = json.dumps(s.sent[0][0], ensure_ascii=False)
        self.assertIn("Yoga", body); self.assertIn(f["start"].strftime("%H:%M"), body); self.assertNotIn("612345678", body); self.assertNotIn("Ana", body)

    def test_reminder_skipped_when_reservation_cancelled(self):
        f = fixture(2); rid, (e, o) = self.reminder(f); Q("DELETE FROM inscripciones WHERE id=%s", (rid,)); s = Sender()
        ps.process_once(db, CFG, s); self.assertEqual((len(s.sent), ob(o)["status"], ob(o)["last_error"]), (0, "SKIPPED", "RESERVATION_GONE"))

    def test_reminder_skipped_when_class_cancelled(self):
        f = fixture(2); rid, (e, o) = self.reminder(f); Q("INSERT INTO clases_canceladas(horario_id,fecha) VALUES(%s,%s)", (f["hid"], f["fecha"])); s = Sender()
        ps.process_once(db, CFG, s); self.assertEqual((len(s.sent), ob(o)["last_error"]), (0, "CLASS_CANCELLED"))

    def test_reminder_skipped_when_schedule_changed(self):
        f = fixture(2); rid, (e, o) = self.reminder(f); new = f["start"] + timedelta(hours=1)
        Q("UPDATE horarios SET hora=%s WHERE id=%s", (new.strftime("%H:%M") + "-" + (new + timedelta(hours=1)).strftime("%H:%M"), f["hid"])); s = Sender()
        ps.process_once(db, CFG, s); self.assertEqual((len(s.sent), ob(o)["last_error"]), (0, "SCHEDULE_CHANGED"))

    def test_schedule_changed_message_has_new_day_and_time_and_heartbeat(self):
        f = fixture(); e, o = event(f, "SCHEDULE_CHANGED", horario_id=f["hid"], fecha=f["fecha"]); s = Sender(); ps.process_once(db, CFG, s)
        body = s.sent[0][0]["body"]; self.assertIn(f["start"].strftime("%H:%M"), body); self.assertIn("Revisa tus reservas", body); self.assertEqual(ob(o)["status"], "ACCEPTED")
        self.assertEqual(Q("SELECT COUNT(*) n FROM tf_notify_settings WHERE k='HB_PUSH'")[0]["n"], 1)
        a = Q("SELECT updated_at FROM tf_notify_settings WHERE k='HB_PUSH'")[0]["updated_at"]; import time; time.sleep(1.1); ps.process_once(db, CFG, Sender())
        self.assertGreater(Q("SELECT updated_at FROM tf_notify_settings WHERE k='HB_PUSH'")[0]["updated_at"], a)

    def test_reception_booking_not_sent_if_reservation_removed(self):
        f = fixture(); Q("INSERT INTO inscripciones(nombre,telefono,horario_id,fecha) VALUES('Ana Prueba','612345678',%s,%s)", (f["hid"], f["fecha"])); rid = Q("SELECT LAST_INSERT_ID() i")[0]["i"]
        e, o = event(f, "RECEPTION_BOOKING", booking_id=rid, horario_id=f["hid"], fecha=f["fecha"]); Q("DELETE FROM inscripciones WHERE id=%s", (rid,)); s = Sender()
        ps.process_once(db, CFG, s); self.assertEqual((len(s.sent), ob(o)["last_error"]), (0, "RESERVATION_GONE"))

    def test_class_cancelled_notice_requires_cancellation(self):
        f = fixture(); e, o = event(f, "CLASS_CANCELLED", horario_id=f["hid"], fecha=f["fecha"]); s = Sender()
        ps.process_once(db, CFG, s); self.assertEqual(ob(o)["last_error"], "NOT_CANCELLED")
        Q("INSERT INTO clases_canceladas(horario_id,fecha) VALUES(%s,%s)", (f["hid"], f["fecha"])); Q("UPDATE tf_push_outbox SET status='PENDING', next_attempt_at=NOW() WHERE id=%s", (o,))
        ps.process_once(db, CFG, s); self.assertEqual(ob(o)["status"], "ACCEPTED")

    def test_revoked_device_gets_nothing(self):
        f = fixture(); e, o = event(f, "TEST"); Q("UPDATE tf_devices SET revoked_at=NOW()"); s = Sender()
        ps.process_once(db, CFG, s); self.assertEqual((len(s.sent), ob(o)["last_error"]), (0, "SUB_INACTIVE"))

    def offer(self, f, status="PENDING", minutes=10):
        Q("INSERT INTO tf_offers(wait_id,person_id,horario_id,fecha,token_hash,status,expires_at) VALUES(1,%s,%s,%s,%s,%s,NOW() + INTERVAL %s MINUTE)", (f["pid"], f["hid"], f["fecha"], os.urandom(32).hex(), status, minutes))
        oid = Q("SELECT LAST_INSERT_ID() i")[0]["i"]
        return oid, event(f, "OFFER", offer_id=oid, horario_id=f["hid"], fecha=f["fecha"], link_token="t" * 40)

    def test_offer_sent_with_deadline_and_token_cleared(self):
        f = fixture(); oid, (e, o) = self.offer(f); s = Sender(); ps.process_once(db, CFG, s)
        d = s.sent[0][0]; self.assertIn("Responde antes de las", d["body"]); self.assertTrue(d["url"].endswith("#" + "t" * 40)); self.assertTrue(d["requireInteraction"])
        self.assertIsNone(Q("SELECT link_token t FROM tf_notify_events WHERE id=%s", (e,))[0]["t"])

    def test_offer_not_sent_if_no_longer_pending_or_expired(self):
        for status, minutes in (("EXPIRED", 10), ("PENDING", -1), ("ACCEPTED", 10)):
            reset(); f = fixture(); oid, (e, o) = self.offer(f, status, minutes); s = Sender(); ps.process_once(db, CFG, s)
            self.assertEqual((len(s.sent), ob(o)["status"]), (0, "SKIPPED"), (status, minutes))

    def test_restart_recovers_stuck_sending(self):
        f = fixture(); e, o = event(f, "TEST"); Q("UPDATE tf_push_outbox SET status='SENDING', next_attempt_at=NOW() - INTERVAL 1 SECOND WHERE id=%s", (o,))
        ps.process_once(db, CFG, Sender()); self.assertEqual(ob(o)["status"], "ACCEPTED")
        e2, o2 = event(f, "TEST"); Q("UPDATE tf_push_outbox SET status='SENDING', next_attempt_at=NOW() + INTERVAL 60 SECOND WHERE id=%s", (o2,))
        s = Sender(); ps.process_once(db, CFG, s); self.assertEqual((len(s.sent), ob(o2)["status"]), (0, "SENDING"))

    def test_endpoint_validation_blocks_internal_targets(self):
        orig = socket.getaddrinfo; socket.getaddrinfo = lambda h, *a, **k: [(2, 1, 6, "", ("142.250.1.1", 443))]
        try:
            self.assertTrue(ps.endpoint_ok("https://fcm.googleapis.com/fcm/send/abc"))
            self.assertTrue(ps.endpoint_ok("https://web.push.apple.com/xyz"))
            for bad in ("http://fcm.googleapis.com/x", "https://127.0.0.1/x", "https://localhost/x", "https://169.254.169.254/latest", "https://fcm.googleapis.com:8080/x", "https://u:p@fcm.googleapis.com/x", "https://evil.example/fcm.googleapis.com", "https://fcm.googleapis.com.evil.example/x"):
                self.assertFalse(ps.endpoint_ok(bad), bad)
            socket.getaddrinfo = lambda h, *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))]
            self.assertFalse(ps.endpoint_ok("https://fcm.googleapis.com/x"), "DNS hacia IP privada")
        finally: socket.getaddrinfo = orig


if __name__ == "__main__":
    unittest.main(verbosity=1)
