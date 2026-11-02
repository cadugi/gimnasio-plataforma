#!/usr/bin/env python3
"""Remitente Web Push aislado. Lee tf_push_outbox, revalida el estado de negocio antes de CADA intento y envía con VAPID.
No decide reglas de negocio nuevas: solo envía lo que PHP dejó registrado y descarta lo que ya no es vigente.
Configuración y claves viven fuera del repositorio (por defecto /etc/topfitness-push/sender.json)."""
import ipaddress, json, logging, re, socket, sys, time
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pymysql, requests
from pywebpush import WebPushException, webpush

MADRID = ZoneInfo("Europe/Madrid")
ALLOWED_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com")
BACKOFF = (30, 120, 600, 1800)       # segundos entre intentos; máximo 5 intentos y nunca más allá del TTL
LEASE = 120                          # un envío «en curso» que no termina en 2 min se reintenta (reinicios)
DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
log = logging.getLogger("push_sender")


def connect(cfg):
    return pymysql.connect(unix_socket=cfg.get("db_socket"), host=cfg.get("db_host"), user=cfg["db_user"], password=cfg.get("db_password", ""),
                           database=cfg["db_name"], charset="utf8mb4", autocommit=True, cursorclass=pymysql.cursors.DictCursor)


def q(db, sql, args=()):
    with db.cursor() as c:
        c.execute(sql, args)
        return c.fetchall(), c.rowcount


def endpoint_ok(url):
    """Mismo criterio que PHP, más resolución DNS: nunca se envía a direcciones privadas o internas."""
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or u.port not in (None, 443) or u.username or not host:
        return False
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        return False
    try:
        return all(ipaddress.ip_address(i[4][0]).is_global for i in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP))
    except (OSError, ValueError):
        return False


class NoRedirectSession(requests.Session):
    def request(self, *a, **kw):
        kw["allow_redirects"] = False
        return super().request(*a, **kw)


def set_tz(db):
    """Las horas de clase son de Madrid y el servidor está en UTC: la sesión usa el desfase vigente (verano/invierno)."""
    off = datetime.now(MADRID).strftime("%z")
    q(db, "SET time_zone = %s", (off[:3] + ":" + off[3:],))


def when(fecha, hora):
    d = datetime.strptime(str(fecha), "%Y-%m-%d")
    return f"{DAYS[d.weekday()]} {d.day}/{d.month} a las {hora[:5]}"


def revalidate(db, ev, sub):
    """(vigente, motivo, datos). Cada tipo comprueba que reserva, clase y horario siguen siendo los que originaron el aviso."""
    kind = ev["kind"]
    if sub["status"] != "ACTIVE" or sub["revoked_at"] is not None:
        return False, "SUB_INACTIVE", None
    if kind == "TEST":
        return True, "", {}
    h = q(db, "SELECT clase, hora, dia FROM horarios WHERE id=%s", (ev["horario_id"],))[0]
    if not h:
        return False, "NO_SCHEDULE", None
    cls, hora, dia = h[0]["clase"], h[0]["hora"], h[0]["dia"]
    cancelled = bool(q(db, "SELECT 1 FROM clases_canceladas WHERE horario_id=%s AND fecha=%s", (ev["horario_id"], ev["fecha"]))[0])
    data = {"clase": cls, "hora": hora, "dia": dia}
    started = q(db, "SELECT (TIMESTAMP(%s, LEFT(%s,5)) <= NOW()) s", (ev["fecha"], hora))[0][0]["s"]
    if kind == "CLASS_CANCELLED":
        return (cancelled, "", data) if cancelled else (False, "NOT_CANCELLED", None)
    if cancelled:
        return False, "CLASS_CANCELLED", None
    if started:
        return False, "CLASS_STARTED", None
    if kind == "REMINDER":
        if not q(db, "SELECT 1 FROM inscripciones WHERE id=%s AND horario_id=%s AND fecha=%s", (ev["booking_id"], ev["horario_id"], ev["fecha"]))[0]:
            return False, "RESERVATION_GONE", None
        # not_before = inicio - 2 h. Si el horario cambió, este recordatorio ya no corresponde (lo cubre el aviso de cambio).
        same = q(db, "SELECT (TIMESTAMP(%s, LEFT(%s,5)) - INTERVAL 2 HOUR = %s) s", (ev["fecha"], hora, ev["not_before"]))[0][0]["s"]
        return (True, "", data) if same else (False, "SCHEDULE_CHANGED", None)
    if kind == "RECEPTION_BOOKING":
        ok = q(db, "SELECT 1 FROM inscripciones WHERE id=%s AND horario_id=%s AND fecha=%s", (ev["booking_id"], ev["horario_id"], ev["fecha"]))[0]
        return (True, "", data) if ok else (False, "RESERVATION_GONE", None)
    if kind in ("OFFER", "OFFER_ACCEPTED"):
        o = q(db, "SELECT status, expires_at, (expires_at > NOW()) live FROM tf_offers WHERE id=%s", (ev["offer_id"],))[0]
        if not o:
            return False, "NO_OFFER", None
        data["expires_at"] = o[0]["expires_at"]
        if kind == "OFFER":
            return (True, "", data) if o[0]["status"] == "PENDING" and o[0]["live"] else (False, "OFFER_NOT_PENDING", None)
        return (True, "", data) if o[0]["status"] == "ACCEPTED" else (False, "OFFER_NOT_ACCEPTED", None)
    if kind == "SCHEDULE_CHANGED":
        return True, "", data
    return False, "UNKNOWN_KIND", None


def payload(ev, d):
    k = ev["kind"]
    if k == "TEST":
        return {"title": "Top Fitness", "body": "Aviso de prueba. Si lo ves, vuelve a la web y pulsa «Sí, lo he recibido».", "url": "/reservas/"}
    w = when(ev["fecha"], d["hora"])
    if k == "REMINDER":
        return {"title": "Recordatorio de clase", "body": f"{d['clase']}, {w}.", "url": "/reservas/"}
    if k == "RECEPTION_BOOKING":
        return {"title": "Reserva hecha en recepción", "body": f"{d['clase']}, {w}.", "url": "/reservas/"}
    if k == "OFFER":
        limit = d["expires_at"].strftime("%H:%M")
        return {"title": "¡Hay una plaza libre!", "body": f"{d['clase']}, {w}. Responde antes de las {limit}.", "url": "/reservas/oferta.html#" + (ev["link_token"] or ""), "requireInteraction": True}
    if k == "OFFER_ACCEPTED":
        return {"title": "Plaza confirmada", "body": f"{d['clase']}, {w}.", "url": "/reservas/"}
    if k == "CLASS_CANCELLED":
        return {"title": "Clase cancelada", "body": f"{d['clase']}, {w}, no se celebrará.", "url": "/reservas/"}
    return {"title": "Cambio de horario", "body": f"{d['clase']}: ahora los {d['dia']} a las {d['hora'][:5]}. Revisa tus reservas.", "url": "/reservas/"}


def real_send(cfg):
    session = NoRedirectSession()

    def send(sub, data, ttl):
        r = webpush({"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth_secret"]}}, json.dumps(data, ensure_ascii=False),
                    vapid_private_key=cfg["vapid_private_key_file"], vapid_claims={"sub": cfg["vapid_subject"]}, ttl=ttl, timeout=10, requests_session=session)
        return r.status_code
    return send


def finish(db, ob, ev, status, error=None, http=None, retry=None):
    if retry:
        q(db, "UPDATE tf_push_outbox SET status='PENDING', attempts=attempts+1, next_attempt_at=NOW() + INTERVAL %s SECOND, last_error=%s, http_status=%s WHERE id=%s", (retry, error, http, ob["id"]))
    else:
        q(db, "UPDATE tf_push_outbox SET status=%s, attempts=attempts+1, accepted_at=IF(%s='ACCEPTED',NOW(),accepted_at), last_error=%s, http_status=%s WHERE id=%s", (status, status, error, http, ob["id"]))
    left = q(db, "SELECT COUNT(*) n FROM tf_push_outbox WHERE event_id=%s AND status IN ('PENDING','SENDING')", (ev["id"],))[0][0]["n"]
    if left == 0:
        ok = q(db, "SELECT COUNT(*) n FROM tf_push_outbox WHERE event_id=%s AND status='ACCEPTED'", (ev["id"],))[0][0]["n"]
        # El enlace opaco de una oferta ya no hace falta una vez resuelto el envío.
        q(db, "UPDATE tf_notify_events SET status=%s, link_token=NULL WHERE id=%s AND status='PENDING'", ("DONE" if ok else "FAILED", ev["id"]))


def permanent_failure(db, ob, ev, sub, reason):
    """Incidencia visible en recepción. Una oferta cuyo aviso no se pudo entregar NO confirma la reserva automáticamente."""
    q(db, "INSERT INTO tf_notify_audit(actor,action,person_id,device_id,detail_json) VALUES('sender','PUSH_FAILED',%s,%s,%s)",
      (ev["person_id"], sub["device_id"], json.dumps({"kind": ev["kind"], "event": ev["id"], "offer": ev["offer_id"], "reason": reason})))


def process_once(db, cfg, send, limit=20):
    set_tz(db)
    q(db, "INSERT INTO tf_notify_settings(k,v) VALUES('HB_PUSH','1') ON DUPLICATE KEY UPDATE v=NOT v")   # latido: recepción ve que el remitente sigue vivo
    sw = dict((r["k"], r["v"]) for r in q(db, "SELECT k,v FROM tf_notify_settings")[0])
    enabled = sw.get("PUSH_SEND_ENABLED") == "1"
    allow = [int(x) for x in re.findall(r"\d+", sw.get("PUSH_ALLOW_PERSONS", ""))]
    # Vencimientos: nada se entrega después de su TTL.
    q(db, "UPDATE tf_push_outbox o JOIN tf_notify_events e ON e.id=o.event_id SET o.status='EXPIRED' WHERE o.status IN ('PENDING','SENDING') AND e.ttl_at < NOW() AND (o.status='PENDING' OR o.next_attempt_at <= NOW())")
    q(db, "UPDATE tf_notify_events e SET status='EXPIRED', link_token=NULL WHERE e.status='PENDING' AND e.ttl_at < NOW() AND NOT EXISTS (SELECT 1 FROM tf_push_outbox o WHERE o.event_id=e.id AND o.status IN ('PENDING','SENDING','ACCEPTED'))")
    if not enabled and not allow:
        return 0
    gate = "" if enabled else " AND e.person_id IN (" + ",".join(str(i) for i in allow) + ")"
    rows, _ = q(db, "SELECT o.id FROM tf_push_outbox o JOIN tf_notify_events e ON e.id=o.event_id WHERE ((o.status='PENDING' AND o.next_attempt_at <= NOW()) OR (o.status='SENDING' AND o.next_attempt_at <= NOW())) "
                    "AND e.not_before <= NOW() AND e.ttl_at >= NOW()" + gate + " ORDER BY o.id LIMIT %s", (limit,))
    done = 0
    for r in rows:
        _, n = q(db, "UPDATE tf_push_outbox SET status='SENDING', next_attempt_at=NOW() + INTERVAL %s SECOND WHERE id=%s AND status IN ('PENDING','SENDING') AND next_attempt_at <= NOW()", (LEASE, r["id"]))
        if n != 1:
            continue
        ob = q(db, "SELECT * FROM tf_push_outbox WHERE id=%s", (r["id"],))[0][0]
        ev = q(db, "SELECT * FROM tf_notify_events WHERE id=%s", (ob["event_id"],))[0][0]
        sub = q(db, "SELECT s.*, d.revoked_at, d.person_id dev_person FROM tf_push_subscriptions s JOIN tf_devices d ON d.id=s.device_id WHERE s.id=%s", (ob["subscription_id"],))[0][0]
        sub["device_id"] = sub["device_id"]
        ok, why, data = revalidate(db, ev, sub)
        if ok and sub["dev_person"] != ev["person_id"]:
            ok, why = False, "PERSON_MISMATCH"
        if not ok:
            finish(db, ob, ev, "SKIPPED", why)
            continue
        if not endpoint_ok(sub["endpoint"]):
            q(db, "UPDATE tf_push_subscriptions SET status='FAILED', last_error='BAD_ENDPOINT' WHERE id=%s", (sub["id"],))
            finish(db, ob, ev, "FAILED", "BAD_ENDPOINT")
            permanent_failure(db, ob, ev, sub, "BAD_ENDPOINT")
            continue
        ttl = max(1, int(q(db, "SELECT TIMESTAMPDIFF(SECOND, NOW(), %s) s", (ev["ttl_at"],))[0][0]["s"]))
        try:
            status = send(sub, payload(ev, data), ttl)
        except WebPushException as e:
            status = e.response.status_code if getattr(e, "response", None) is not None else 0
        except Exception:
            status = 0
        done += 1
        if 200 <= status < 300:
            if ev["kind"] == "TEST":
                q(db, "UPDATE tf_push_subscriptions SET test_sent_at=NOW(), failure_count=0, last_error=NULL WHERE id=%s", (sub["id"],))
            finish(db, ob, ev, "ACCEPTED", None, status)
        elif status in (404, 410):
            q(db, "UPDATE tf_push_subscriptions SET status='EXPIRED', last_error=%s WHERE id=%s", (f"HTTP_{status}", sub["id"]))
            finish(db, ob, ev, "FAILED", f"HTTP_{status}", status)
            permanent_failure(db, ob, ev, sub, f"HTTP_{status}")
        elif status in (400, 401, 403, 413):
            q(db, "UPDATE tf_push_subscriptions SET failure_count=failure_count+1, last_error=%s, status=IF(failure_count+1>=3,'FAILED',status) WHERE id=%s", (f"HTTP_{status}", sub["id"]))
            finish(db, ob, ev, "FAILED", f"HTTP_{status}", status)
            permanent_failure(db, ob, ev, sub, f"HTTP_{status}")
        elif ob["attempts"] + 1 >= 5:
            finish(db, ob, ev, "FAILED", "RETRIES_EXHAUSTED", status or None)
            permanent_failure(db, ob, ev, sub, "RETRIES_EXHAUSTED")
        else:
            finish(db, ob, ev, "PENDING", f"HTTP_{status}" if status else "NETWORK", status or None, retry=BACKOFF[min(ob["attempts"], len(BACKOFF) - 1)])
        log.info("outbox=%s kind=%s status=%s", ob["id"], ev["kind"], status)
    return done


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/etc/topfitness-push/sender.json"))
    send = real_send(cfg)
    while True:
        try:
            db = connect(cfg)
            try:
                while True:
                    process_once(db, cfg, send)
                    time.sleep(2)
            finally:
                db.close()
        except pymysql.Error as e:
            log.error("base de datos no disponible: %s", type(e).__name__)
            time.sleep(10)


if __name__ == "__main__":
    main()
