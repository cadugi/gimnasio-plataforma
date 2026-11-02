"""Administración por línea de comandos: python3 -m caja.cli <comando>."""
import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from . import auth, bridge, importer
from .db import DB


def write_secret(path, text):
    """Escribe un secreto con permisos 600 y sin sobrescribir."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text + '\n')


def main(argv=None):
    p = argparse.ArgumentParser(prog='caja')
    p.add_argument('--data', default=os.environ.get('CAJA_DATA', '/var/lib/topfitness-caja'))
    sub = p.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('migrate'); m.add_argument('--upto', type=int)
    u = sub.add_parser('create-user')
    u.add_argument('username'); u.add_argument('--name', required=True)
    u.add_argument('--role', choices=sorted(auth.PERMS), required=True)
    u.add_argument('--password-file', help='Fichero con la contraseña; si falta se pide por consola oculta')
    u.add_argument('--initial-password-out', help='Genera contraseña aleatoria que obliga a cambiarla y la guarda aquí (600)')
    d = sub.add_parser('provision-device'); d.add_argument('--token-out', required=True)
    d.add_argument('--device-id', default=bridge.DEVICE_ID)
    r = sub.add_parser('revoke-device'); r.add_argument('--device-id', default=bridge.DEVICE_ID)
    i = sub.add_parser('import'); i.add_argument('file'); i.add_argument('--commit', action='store_true')
    sub.add_parser('backup')
    sub.add_parser('check')
    ih = sub.add_parser('import-history', help='Carga el histórico del Excel (JSON con until y rows) en el Histórico del Diario')
    ih.add_argument('file')
    ci = sub.add_parser('copy-identity', help='Copia usuarios y dispositivos (solo hashes) desde otra base, p. ej. la piloto')
    ci.add_argument('source')
    a = p.parse_args(argv)
    db = DB(Path(a.data) / 'caja.sqlite3', upto=(a.upto if a.cmd == 'migrate' else None)) \
        if a.cmd not in ('import',) else DB(Path(a.data) / 'caja.sqlite3', upto=1)
    if a.cmd == 'migrate':
        print('Esquema en versión', db.version())
    elif a.cmd == 'create-user':
        if a.initial_password_out:
            password, must = secrets.token_urlsafe(18), True
        elif a.password_file:
            password, must = Path(a.password_file).read_text(encoding='utf-8-sig').strip(), False
        else:
            password, must = getpass.getpass('Contraseña: '), False
        with db.tx() as c:
            auth.create_user(c, a.username, a.name, a.role, password, must_change=must)
        if a.initial_password_out:
            write_secret(a.initial_password_out, 'usuario: %s\ncontraseña inicial (cámbiala al entrar): %s' % (a.username, password))
            print('Usuario creado. Contraseña inicial en', a.initial_password_out)
        else:
            print('Usuario creado.')
    elif a.cmd == 'provision-device':
        with db.tx() as c:
            token = bridge.provision_device(c, a.device_id)
        write_secret(a.token_out, token)
        print('Token generado en', a.token_out, '(no se muestra en pantalla)')
    elif a.cmd == 'revoke-device':
        with db.tx() as c:
            bridge.revoke_device(c, a.device_id)
        print('Dispositivo revocado.')
    elif a.cmd == 'import':
        if a.commit:
            res = importer.run(db, a.file, commit=True)
        else:
            res = importer.preview(a.file)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if a.commit:
            print('Ahora ejecuta: migrate (activa protecciones) y arranca el servicio.')
    elif a.cmd == 'backup':
        print(db.backup('manual'))
    elif a.cmd == 'copy-identity':
        import sqlite3
        src = sqlite3.connect('file:%s?mode=ro' % Path(a.source).as_posix(), uri=True)
        src.row_factory = sqlite3.Row
        with db.tx() as c:
            for u in src.execute('SELECT * FROM users'):
                c.execute('INSERT OR IGNORE INTO users(username,display_name,pw_hash,role,active,must_change,created) VALUES (?,?,?,?,?,?,?)',
                          (u['username'], u['display_name'], u['pw_hash'], u['role'], u['active'], u['must_change'], u['created']))
            for d in src.execute('SELECT * FROM devices'):
                c.execute('INSERT OR IGNORE INTO devices(device_id,token_hash,revoked,label,created) VALUES (?,?,?,?,?)',
                          (d['device_id'], d['token_hash'], d['revoked'], d['label'], d['created']))
        print('Usuarios y dispositivos copiados (sin tokens ni contraseñas en claro).')
    elif a.cmd == 'import-history':
        from . import hoja
        payload = json.loads(Path(a.file).read_text(encoding='utf-8'))
        print(db.backup('antes-historial'))
        with db.tx() as c:
            print(json.dumps(hoja.import_history(c, payload['rows'], payload['until']), ensure_ascii=False))
    elif a.cmd == 'check':
        print('integridad:', db.one('PRAGMA integrity_check'), 'versión:', db.version())
    return 0


if __name__ == '__main__':
    sys.exit(main())
