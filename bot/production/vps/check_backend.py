#!/usr/bin/python3
import json
import subprocess
import urllib.request
try:
    raw=subprocess.run(['systemd-creds','decrypt','--name=topfitness-env','/etc/credstore.encrypted/topfitness-env','-'],capture_output=True,check=True).stdout
    values=json.loads(raw)
    directory=json.loads(values['WA_DIRECTORY_JSON'])
    for identity in directory.values():
        request=urllib.request.Request(values['WA_BACKEND_URL'],data=json.dumps({'action':'people','user_id':identity['principal']}).encode(),headers={'Authorization':'Bearer '+values['WA_BACKEND_SECRET'],'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=10) as response:
            assert response.headers['X-Demo-Reservas']=='isolated-v2'
            assert json.load(response)['people']
    print('Backend e identidades correctos en el VPS.')
except Exception:raise SystemExit(1) from None
