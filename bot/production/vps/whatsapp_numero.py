#!/usr/bin/python3
"""Cambio de número de WhatsApp (prueba -> oficial) y vuelta atrás. Se ejecuta con sudo.

    sudo python3 whatsapp_numero.py estado
    printf %s "$TOKEN" | sudo python3 whatsapp_numero.py token          # guarda un token nuevo (permanente)
    sudo python3 whatsapp_numero.py pedir-codigo  --phone-id ID          # SMS al número oficial
    sudo python3 whatsapp_numero.py verificar     --phone-id ID --codigo 123456
    sudo python3 whatsapp_numero.py registrar     --phone-id ID --pin 123456 --confirmo
    sudo python3 whatsapp_numero.py activar       --phone-id 1307370059133825 [--sin-invitados]   # suscribe la app a la cuenta oficial
    sudo python3 whatsapp_numero.py volver                               # deja el número de prueba

Nunca imprime tokens ni secretos. Cada cambio del almacén deja copia en topfitness-env.bak-*.
"""
import argparse, json, os, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

STORE = Path('/etc/credstore.encrypted/topfitness-env')
LAST = Path('/etc/credstore.encrypted/.ultimo-cambio-numero')
WABA_PRUEBA = '1618799219708710'
WABA_OFICIAL = '1641461160835161'   # cuenta del número +34 615 80 94 95
PHONE_ID_OFICIAL = '1307370059133825'


def load():
    out = subprocess.run(['systemd-creds', 'decrypt', '--name=topfitness-env', str(STORE), '-'], capture_output=True)
    if out.returncode: sys.exit('No se pudo leer el almacén cifrado.')
    return json.loads(out.stdout)


def save(values, tag):
    enc = subprocess.run(['systemd-creds', 'encrypt', '--name=topfitness-env', '-', '-'], input=json.dumps(values).encode(), capture_output=True)
    if enc.returncode: sys.exit('No se pudo cifrar el almacén.')
    backup = STORE.with_name('topfitness-env.bak-' + tag + '-' + time.strftime('%Y%m%dT%H%M%S'))
    backup.write_bytes(STORE.read_bytes()); backup.chmod(0o600)
    new = STORE.with_suffix('.new'); new.write_bytes(enc.stdout); new.chmod(0o600); os.replace(new, STORE)
    return backup


def graph(values, path, data=None, method=None):
    request = urllib.request.Request('https://graph.facebook.com/' + values['WA_GRAPH_VERSION'] + '/' + path,
                                     data=json.dumps(data).encode() if data is not None else None, method=method,
                                     headers={'Authorization': 'Bearer ' + values['WA_ACCESS_TOKEN'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=25) as response: return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try: return error.code, json.loads(error.read())
        except ValueError: return error.code, {}
    except OSError: return 0, {}


def restart():
    subprocess.run(['systemctl', 'restart', 'topfitness-whatsapp'], check=True)
    time.sleep(6)
    active = subprocess.run(['systemctl', 'is-active', 'topfitness-whatsapp'], capture_output=True, text=True).stdout.strip()
    log = subprocess.run(['journalctl', '-u', 'topfitness-whatsapp', '-n', '5', '--no-pager'], capture_output=True, text=True).stdout
    ready = 'Webhook de prueba disponible' in log
    print('Servicio:', active, '| arranque correcto:', 'sí' if ready else 'NO (revisa journalctl)')
    return active == 'active' and ready


def describe(values):
    code, info = graph(values, 'debug_token?input_token=' + values['WA_ACCESS_TOKEN'])
    data = info.get('data', {}) if code == 200 else {}
    expires = data.get('expires_at')
    print('Token:', 'válido' if data.get('is_valid') else 'NO válido / caducado',
          '| caduca:', 'nunca' if data.get('is_valid') and not expires else (time.strftime('%d-%m-%Y %H:%M', time.localtime(expires)) if expires else '-'))
    code, info = graph(values, values['WA_TEST_PHONE_NUMBER_ID'] + '?fields=display_phone_number,verified_name,status,code_verification_status,platform_type,quality_rating')
    print('Número configurado:', info if code == 200 else 'no consultable (token o id no válidos)')
    directory = json.loads(values['WA_DIRECTORY_JSON'])
    print('Directorio autorizado:', len(directory), 'número(s) | respuesta a no vinculados:', 'sí' if values.get('WA_UNKNOWN_REPLY') == '1' else 'no',
          '| empleado:', 'sí' if values.get('WA_HANDOFF') == '1' else 'no')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('orden', choices=['estado', 'token', 'pedir-codigo', 'verificar', 'registrar', 'activar', 'volver'])
    parser.add_argument('--phone-id'); parser.add_argument('--codigo'); parser.add_argument('--pin')
    parser.add_argument('--confirmo', action='store_true'); parser.add_argument('--sin-invitados', action='store_true')
    args = parser.parse_args()
    values = load()
    if args.orden == 'estado': return describe(values)
    if args.orden == 'token':
        token = sys.stdin.read().strip()
        if len(token) < 40: sys.exit('Token vacío o demasiado corto.')
        probe = dict(values, WA_ACCESS_TOKEN=token)
        if graph(probe, 'me')[0] != 200: sys.exit('Meta rechaza ese token. No se ha guardado.')
        values['WA_ACCESS_TOKEN'] = token
        print('Copia:', save(values, 'token').name); restart(); return describe(values)
    if args.orden == 'volver':
        if not LAST.exists(): sys.exit('No hay un cambio de número registrado.')
        backup = Path(LAST.read_text().strip())
        if not backup.is_file(): sys.exit('Falta la copia ' + backup.name)
        keep = values['WA_ACCESS_TOKEN']
        STORE.write_bytes(backup.read_bytes()); STORE.chmod(0o600)
        values = load(); values['WA_ACCESS_TOKEN'] = keep   # el token vigente se conserva
        save(values, 'volver'); LAST.unlink(); print('Restaurado el número de prueba.'); restart(); return describe(values)
    if not args.phone_id or not args.phone_id.isdigit(): sys.exit('Falta --phone-id (identificador numérico del número en Meta).')
    base = args.phone_id
    if args.orden == 'pedir-codigo':
        print(graph(values, base + '/request_code', {'code_method': 'SMS', 'language': 'es'}, 'POST')); return
    if args.orden == 'verificar':
        if not args.codigo: sys.exit('Falta --codigo.')
        print(graph(values, base + '/verify_code', {'code': args.codigo}, 'POST')); return
    if args.orden == 'registrar':
        if not args.confirmo or not args.pin or not (args.pin.isdigit() and len(args.pin) == 6):
            sys.exit('Registrar conecta el número a la API de WhatsApp y puede dejarlo fuera de la app Business. Usa --pin de 6 dígitos y --confirmo.')
        print(graph(values, base + '/register', {'messaging_product': 'whatsapp', 'pin': args.pin}, 'POST')); return
    if args.orden == 'activar':
        code, info = graph(values, base + '?fields=display_phone_number,status,platform_type')
        if code != 200: sys.exit('Meta no devuelve el número ' + base + '. ¿Token válido y número registrado?')
        print('Número:', info)
        if base == PHONE_ID_OFICIAL:
            print('Suscripción de la app a la cuenta oficial:', graph(values, WABA_OFICIAL + '/subscribed_apps', {}, 'POST'))
        if values['WA_TEST_PHONE_NUMBER_ID'] == base: sys.exit('Ya está activo.')
        backup = save(dict(values, WA_TEST_PHONE_NUMBER_ID=base, WA_UNKNOWN_REPLY='0' if args.sin_invitados else '1'), 'numero-real')
        # La copia previa al cambio es la que usa «volver».
        previous = sorted(STORE.parent.glob('topfitness-env.bak-numero-real-*'))[-1]
        LAST.write_text(str(previous)); LAST.chmod(0o600)
        if not restart():
            print('Fallo al arrancar: se vuelve al número anterior.'); STORE.write_bytes(previous.read_bytes()); restart(); sys.exit(1)
        print('Listo. Escribe «Hola» al número oficial desde un móvil del directorio.'); return describe(load())


if __name__ == '__main__': main()
