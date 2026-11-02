#!/usr/bin/env python3
"""Sube a la web de Cuentas los Excel mensuales de Caja Gimnasio (solo biblioteca estándar).

Configuración: %LOCALAPPDATA%\\TopFitness\\Caja\\cuentas_sync.json  (en Linux: ~/.config/topfitness/cuentas_sync.json)
    {"url": "https://whatsapp.gimnasio.example/cuentas/api/subir", "secret": "<clave de ingest.key>",
     "folder": "C:\\\\Users\\\\User\\\\AppData\\\\Local\\\\TopFitness\\\\Caja\\\\Mensuales"}
Solo sube los Caja-AAAA-MM.xlsx nuevos o modificados (recuerda su hash). Pensado para ejecutarse
cada 15 minutos con el Programador de tareas de Windows:  pythonw subir_caja.py
"""
import hashlib, hmac, json, os, re, secrets, sys, time, urllib.request, urllib.error

NAME = re.compile(r"^Caja-\d{4}-\d{2}\.xlsx$")


def cfg_dir():
    base = os.environ.get("LOCALAPPDATA")
    return os.path.join(base, "TopFitness", "Caja") if base else os.path.expanduser("~/.config/topfitness")


def upload(url, secret, path):
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        body = fh.read()
    ts, nonce = str(int(time.time())), secrets.token_urlsafe(18)
    route = "/" + url.split("//", 1)[1].split("/", 1)[1]
    msg = "\n".join(["POST", route, ts, nonce, name, hashlib.sha256(body).hexdigest()]).encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "X-TF-Filename": name, "X-TF-Time": ts, "X-TF-Nonce": nonce, "X-TF-Sig": sig,
        "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    d = cfg_dir()
    cfg = json.load(open(os.path.join(d, "cuentas_sync.json"), encoding="utf-8"))
    state_file = os.path.join(d, "cuentas_sync_estado.json")
    try:
        state = json.load(open(state_file))
    except (OSError, ValueError):
        state = {}
    failed = 0
    for f in sorted(os.listdir(cfg["folder"])):
        if not NAME.match(f):
            continue
        p = os.path.join(cfg["folder"], f)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if state.get(f) == h:
            continue
        try:
            upload(cfg["url"], cfg["secret"], p)
            state[f] = h
            print("subido", f)
        except (urllib.error.URLError, OSError) as ex:
            failed += 1
            print("fallo", f, ex, file=sys.stderr)
    json.dump(state, open(state_file, "w"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
