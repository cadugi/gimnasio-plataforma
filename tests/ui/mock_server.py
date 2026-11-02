#!/usr/bin/env python3
"""Servidor SOLO de pruebas de interfaz: sirve web/public y simula movil.php/avisos.php en memoria. No toca ninguna base de datos."""
import http.server, json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web", "public")
S = {"linked": False, "sub": False, "sent": False, "ok": False, "send": True, "offer": "PENDING", "of_posts": 0, "yoga": True, "cancels": 0}
TOKEN = "a" * 64


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, *a):
        pass

    def out(self, j, code=200):
        b = json.dumps(j).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def av(self):
        return {"state": ("ACTIVATED" if S["sub"] and S["ok"] else "REVIEW" if S["sub"] else "NONE"), "subscribed": S["sub"],
                "test_sent": S["sent"], "test_confirmed": S["ok"], "problem": None}

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/reservas/movil.php":
            return self.out({"success": True, "linked": True, "nombre": "Ana Pérez", "telefono": "612345678", "csrf": "x"} if S["linked"] else {"success": True, "linked": False})
        if p == "/reservas/avisos.php":
            return self.out({"success": True, "avisos": self.av(), "vapid_public": "BAbc", "envio_activo": S["send"],
                             "mis_avisos": [{"kind": "REMINDER", "fecha": "2026-11-02", "clase": "Yoga", "hora": "18:00", "estado": "ENVIADO"}]})
        if p == "/reservas/obtener_horarios_clase.php":
            b = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture_horarios.json"), "rb").read()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if p == "/reservas/comprobar_disponibilidad.php":
            return self.out({"cancelada": False, "success": True, "disponibles": 5, "limite": 5, "limite_max": 10, "inscritos": 5, "retenidas": 0, "en_cola": 0})
        if p == "/reservas/mis_clases.php":
            if not S["linked"]:
                return self.out({"success": False, "error": "ACCESS_DENIED"}, 403)
            return self.out({"success": True, "nombre": "Ana Pérez", "avisos": "ACTIVATED" if S["sub"] and S["ok"] else "NONE",
                             "reservas": [{"clase": "Yoga", "fecha": "2026-11-03", "hora": "18:00", "cancelada": False, "puede": S["yoga"], "ref": "1.aaaaaaaaaaaaaaaaaaaaaaaa"}, {"clase": "Pilates", "fecha": "2026-11-04", "hora": "10:00", "cancelada": True, "puede": False, "ref": "2.bbbbbbbbbbbbbbbbbbbbbbbb"}],
                             "espera": [{"clase": "Boxeo", "fecha": "2026-11-05", "hora": "19:00", "cancelada": False, "posicion": 2, "total": 3, "oferta_hasta": None, "puede": True, "ref": "3.cccccccccccccccccccccccc"},
                                        {"clase": "Ciclo", "fecha": "2026-11-06", "hora": "08:00", "cancelada": False, "posicion": 1, "total": 1, "oferta_hasta": "17:42", "puede": True, "ref": "4.dddddddddddddddddddddddd"}]})
        if p == "/reservas/admin_movil.php":
            return self.out({"success": True, "salud": {"envio": True, "ofertas": True, "remitente_seg": 3, "worker_ofertas_seg": 200},
                             "devices": [{"id": 1, "nombre": "Ana Pérez", "telefono": "***678", "platform": "ios", "last_seen_at": "2026-10-30 17:00:00", "avisos": 1}],
                             "ofertas": [{"id": 7, "nombre": "Luis Gómez", "telefono": "***222", "clase": "Yoga", "fecha": "2026-11-03", "hora": "18:00", "limite": "17:42", "segundos": 600, "avisos": 0}],
                             "incidencias": [{"id": 9, "action": "OFFER_UNDELIVERABLE", "created_at": "2026-10-30 17:19:21", "nombre": "Luis Gómez", "detail_json": "{}"}]})
        if p == "/reservas/oferta.php":
            if self.headers.get("X-Offer-Token") != TOKEN:
                return self.out({"success": False, "error": "OFFER_NOT_FOUND"}, 404)
            return self.out({"success": True, "clase": "Yoga", "fecha": "2026-11-03", "hora": "18:00", "limite": "17:42", "estado": S["offer"]})
        if p == "/reservas/":
            self.path = "/mobile.html"; return super().do_GET()
        if p.startswith("/reservas/"):
            self.path = p.replace("/reservas/", "/", 1)
        return super().do_GET()

    def do_POST(self):
        p = self.path.split("?")[0]
        r = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        a = r.get("action")
        if p.endswith("movil.php"):
            if a == "identificar":
                if len(r.get("telefono", "")) < 9:
                    return self.out({"success": False, "error": "INVALID_DATA"}, 400)
                S.update(linked=True)
                return self.out({"success": True, "linked": True, "csrf": "x"})
            if a == "olvidar":
                S.update(linked=False, sub=False, sent=False, ok=False)
                return self.out({"success": True, "linked": False})
        if p.endswith("mis_clases.php"):
            S["cancels"] += 1
            if a == "cancelar":
                S["yoga"] = False
            return self.out({"success": True, "estado": "CANCELADA"})
        if p.endswith("admin_movil.php"):
            S["staff"] = a
            return self.out({"success": True, "estado": "ACCEPTED"})
        if p.endswith("oferta.php"):
            S["of_posts"] += 1
            if r.get("token") != TOKEN:
                return self.out({"success": False, "error": "OFFER_NOT_FOUND"}, 404)
            if S["offer"] == "ACCEPTED":
                return self.out({"success": True, "estado": "ACCEPTED", "ya": True})
            if S["offer"] == "EXPIRED":
                return self.out({"success": False, "estado": "EXPIRED", "code": "OFFER_EXPIRED"}, 409)
            S["offer"] = "ACCEPTED" if a == "aceptar" else "DECLINED"
            return self.out({"success": True, "estado": S["offer"], "ya": False})
        if p.endswith("avisos.php"):
            if a == "suscribir":
                S.update(sub=True, sent=False, ok=False)
            if a == "probar":
                S.update(sent=True, ok=False)
            if a == "confirmar_prueba":
                S.update(ok=True)
            if a == "desactivar":
                S.update(sub=False)
            return self.out({"success": True, "avisos": self.av()})
        self.out({"success": False}, 400)

    def do_PATCH(self):  # estado para las pruebas
        self.out({"of_posts": S["of_posts"], "offer": S["offer"], "cancels": S["cancels"]})

    def do_DELETE(self):  # reinicio entre pruebas
        S.update(linked=False, sub=False, sent=False, ok=False, send=True, offer="PENDING", of_posts=0, yoga=True, cancels=0)
        if "expired" in self.path:
            S["offer"] = "EXPIRED"
        self.out({"success": True})


http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()
