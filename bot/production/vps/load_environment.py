#!/usr/bin/python3
"""Lee variables por SSH/stdin y las conserva solo en memoria de systemd."""
import json
import subprocess
import sys
import dbus
from pathlib import Path
import os

try:
    values=json.load(sys.stdin)
    names=('WA_APP_SECRET','WA_VERIFY_TOKEN','WA_TEST_PHONE_NUMBER_ID','WA_ACCESS_TOKEN',
           'WA_GRAPH_VERSION','WA_DIRECTORY_JSON','WA_BACKEND_URL','WA_BACKEND_SECRET','WA_TEST_MODE')
    if set(values)!=set(names) or not all(isinstance(v,str) and v and '\x00' not in v and '\n' not in v for v in values.values()):
        raise ValueError()
    encrypted=Path('/etc/credstore.encrypted/topfitness-env')
    if encrypted.exists():
        existing=subprocess.run(['systemd-creds','decrypt','--name=topfitness-env',str(encrypted),'-'],capture_output=True,check=True)
        stored=json.loads(existing.stdout)
        changed=any(stored.get(k)!=v for k,v in values.items())
        if changed:
            stored.update(values)
            result=subprocess.run(['systemd-creds','encrypt','--name=topfitness-env','-','-'],input=json.dumps(stored).encode(),capture_output=True,check=True)
            temp=encrypted.with_suffix('.new');temp.write_bytes(result.stdout);temp.chmod(0o600);os.replace(temp,encrypted)
        result=subprocess.run(['systemctl','restart' if changed else 'start','topfitness-whatsapp.service'],capture_output=True)
        raise SystemExit(result.returncode)
    manager=dbus.Interface(dbus.SystemBus().get_object('org.freedesktop.systemd1','/org/freedesktop/systemd1'),
                           'org.freedesktop.systemd1.Manager')
    properties=dbus.Interface(dbus.SystemBus().get_object('org.freedesktop.systemd1','/org/freedesktop/systemd1'),'org.freedesktop.DBus.Properties')
    previous={str(v).split('=',1)[0]:str(v).split('=',1)[1] for v in properties.Get('org.freedesktop.systemd1.Manager','Environment')}
    changed=any(previous.get(k)!=v for k,v in values.items())
    manager.SetEnvironment([k+'='+v for k,v in values.items()])
    action='restart' if changed else 'start'
    result=subprocess.run(['systemctl',action,'topfitness-whatsapp.service'],capture_output=True)
    raise SystemExit(result.returncode)
except Exception:
    raise SystemExit(1) from None
