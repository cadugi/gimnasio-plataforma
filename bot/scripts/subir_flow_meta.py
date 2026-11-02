import json, subprocess, sys, urllib.request, urllib.error, uuid
import os
# Token por variable de entorno (META_TOKEN) o, si no, el del almacén cifrado del VPS. Nunca se imprime.
env = json.loads(subprocess.run(['sudo','systemd-creds','decrypt','/etc/credstore.encrypted/topfitness-env','-'],capture_output=True,check=True).stdout)
tok, fid, ver = os.environ.get('META_TOKEN') or env['WA_ACCESS_TOKEN'], env['WA_FLOW_ID'], env['WA_GRAPH_VERSION']
def call(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=dict(headers or {}, Authorization='Bearer '+tok), method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try: body = json.load(e)
        except Exception: body = {}
        err = body.get('error', {}); return e.code, {'error': {k: err.get(k) for k in ('type','code','error_subcode','message')}}
base = f'https://graph.facebook.com/{ver}/{fid}'
st, info = call(base + '?fields=name,status,validation_errors,endpoint_uri')
print('estado:', st, json.dumps(info, ensure_ascii=False)[:1500])
if sys.argv[1:] == ['upload'] and st == 200 and info.get('status') == 'DRAFT':
    b = uuid.uuid4().hex; content = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','assets','whatsapp-booking-flow.json'),'rb').read()
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="name"\r\n\r\nflow.json\r\n', f'--{b}\r\nContent-Disposition: form-data; name="asset_type"\r\n\r\nFLOW_JSON\r\n']
    body = ''.join(parts).encode() + f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="flow.json"\r\nContent-Type: application/json\r\n\r\n'.encode() + content + f'\r\n--{b}--\r\n'.encode()
    st, res = call(base + '/assets', body, {'Content-Type': 'multipart/form-data; boundary=' + b}, 'POST')
    print('subida:', st, json.dumps(res, ensure_ascii=False)[:4000])
