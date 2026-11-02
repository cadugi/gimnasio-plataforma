#!/usr/bin/env python3
"""Plan (solo lectura) para copiar web/ del repositorio a /opt/topfitness-web SIN pisar cambios hechos en producción por otra sesión.
Compara tres versiones de cada archivo: repositorio (nuevo), producción (ahora) y la copia de seguridad previa (base).
  NUEVO        no existe en producción                         -> se copia
  ACTUALIZAR   producción == base (nadie lo tocó)               -> se copia
  IGUAL        producción == repositorio                        -> nada
  CONSERVAR    producción cambió y el repositorio no            -> se deja la de producción (cambio de otra sesión)
  CONFLICTO    ambos cambiaron respecto a la base               -> SE DETIENE: hay que fusionar a mano
Uso: push_plan_sync.py BACKUP.tgz [--apply]   (--apply solo copia NUEVO y ACTUALIZAR y aborta si hay CONFLICTO)"""
import hashlib, io, json, os, shutil, sys, tarfile
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
PROD = "/opt/topfitness-web"
MANIFEST = "/var/lib/topfitness-push-deploy/manifest.json"   # sha de lo que ESTE script dejó en producción (para distinguirlo de cambios ajenos)
INCLUDE = ("public/", "sso/", "cli/", "migrations/", "guard.php")
SKIP = ("public/img/guia/",)  # se copian igual; lista por si hiciera falta excluir algo


def sha(b): return hashlib.sha256(b).hexdigest()


def main():
    tgz = sys.argv[1]; apply = "--apply" in sys.argv
    base = {}
    with tarfile.open(tgz) as t:
        for m in t.getmembers():
            if m.isfile() and m.name.startswith("topfitness-web/"):
                base[m.name[len("topfitness-web/"):]] = sha(t.extractfile(m).read())
    last = json.load(open(MANIFEST)) if os.path.isfile(MANIFEST) else {}
    rows, conflicts = [], 0
    for root, _, files in os.walk(REPO):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), REPO).replace(os.sep, "/")
            if not rel.startswith(INCLUDE) or rel.endswith(".pyc") or "__pycache__" in rel: continue
            repo = sha(open(os.path.join(REPO, rel), "rb").read())
            p = os.path.join(PROD, rel); prod = sha(open(p, "rb").read()) if os.path.isfile(p) else None
            b = base.get(rel)
            if prod is None: st = "NUEVO"
            elif prod == repo: st = "IGUAL"
            elif prod == b or prod == last.get(rel): st = "ACTUALIZAR"
            elif repo == b: st = "CONSERVAR"
            else: st = "CONFLICTO"; conflicts += 1
            rows.append((st, rel))
    order = {"CONFLICTO": 0, "CONSERVAR": 1, "NUEVO": 2, "ACTUALIZAR": 3, "IGUAL": 4}
    for st, rel in sorted(rows, key=lambda r: (order[r[0]], r[1])):
        if st != "IGUAL": print(f"{st:11} {rel}")
    print("resumen:", {k: sum(1 for r in rows if r[0] == k) for k in order})
    if conflicts: print("HAY CONFLICTOS: no se aplica nada."); sys.exit(2)
    if apply:
        for st, rel in rows:
            if st in ("NUEVO", "ACTUALIZAR"):
                dst = os.path.join(PROD, rel); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(os.path.join(REPO, rel), dst)
                last[rel] = sha(open(dst, "rb").read())
        os.makedirs(os.path.dirname(MANIFEST), exist_ok=True); json.dump(last, open(MANIFEST, "w"))
        print("aplicado (NUEVO + ACTUALIZAR).")


main()
