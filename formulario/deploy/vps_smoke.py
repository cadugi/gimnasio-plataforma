"""Prueba HTTPS con identidad temporal ficticia y sin registrar credenciales."""
import base64,hashlib,http.cookiejar,json,os,pathlib,secrets,struct,subprocess,sys,urllib.error,urllib.request
P=pathlib.Path;ROOT=P(__file__).resolve().parents[1]
BASE='https://whatsapp.gimnasio.example'

def access(payload):
    command=['runuser','-u','topfitness-altas','--','env','TF_CONFIG_FILE=/etc/topfitness-altas/config.json','TF_KEY_FILE=/run/credentials/topfitness-altas.service/keys','php','-d','extension=/opt/topfitness-formulario/runtime/php-sqlite/usr/lib/php/20230831/pdo_sqlite.so',str(ROOT/'deploy/vps_smoke_access.php')]
    result=subprocess.run(command,input=json.dumps(payload).encode(),capture_output=True)
    if result.returncode:raise RuntimeError('No se pudo preparar o limpiar el acceso temporal.')
    return json.loads(result.stdout)

class Client:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar();self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar));self.csrf=''
        status,data=self.request('/alta/api.php?action=bootstrap');assert status==200
        self.csrf=data['data']['csrf']
    def request(self,path,payload=None,headers=None):
        head={'Content-Type':'application/json','X-CSRF-Token':self.csrf}
        head.update(headers or {})
        body=None if payload is None else json.dumps(payload).encode()
        req=urllib.request.Request(BASE+path,data=body,headers=head)
        try:
            with self.opener.open(req,timeout=15) as response:code=response.status;raw=response.read();self.headers=response.headers
        except urllib.error.HTTPError as response:code=response.code;raw=response.read();self.headers=response.headers
        try:data=json.loads(raw)
        except ValueError:data=raw
        if isinstance(data,dict) and data.get('ok') and isinstance(data.get('data'),dict):self.csrf=data['data'].get('csrf',self.csrf)
        return code,data
    def post(self,action,**payload):
        status,data=self.request('/alta/api.php',{'action':action,**payload});assert status==200,action
        return data['data']

def main():
    identity=secrets.token_hex(16);username='qa_deploy_'+secrets.token_hex(5);password=secrets.token_urlsafe(30)+'Aa9'
    result=subprocess.run(['/usr/bin/openssl','passwd','-apr1','-stdin'],input=password.encode()+b'\n',capture_output=True,check=True)
    access({'operation':'create','id':identity,'username':username,'hash':result.stdout.decode().strip()})
    checks=[];client=None;draft=False
    try:
        guest=Client();assert guest.request('/alta/api.php',{'action':'contracts'})[0]==401
        assert guest.request('/alta/api.php',{'action':'draft_new'})[0]==403
        checks.append('Acceso anónimo sin contratos ni envíos')
        client=Client();client.post('login',username=username,password=password)
        assert all(c.secure and c.path=='/alta/' for c in client.jar)
        assert access({'operation':'status','id':identity})['rehash_argon2id']
        checks.append('Autenticación Apache importada y conversión a Argon2id; cookie HTTPS /alta/')
        _,bootstrap=client.request('/alta/api.php?action=bootstrap');catalog=bootstrap['data']['catalog']
        tariff=next(x for x in catalog['tariffs'] if x['brand']=='fitness')
        legal=next(x for x in catalog['legal'] if x['brand']=='fitness')
        client.post('kiosk_start');client.post('draft_new');draft=True
        assert client.request('/alta/api.php',{'action':'contracts'})[0]==401
        assert client.request('/alta/api.php',{'action':'draft_cancel'},headers={'X-CSRF-Token':'invalid'})[0]==403
        assert client.request('/alta/api.php',{'action':'draft_cancel'},headers={'Origin':'https://otro.invalid'})[0]==403
        checks.append('Modo tablet sin administración, CSRF y origen comprobados')
        data={'personal':{'name':'PRUEBA','surname':'DESPLIEGUE FICTICIO','birth_date':'1994-03-12','document_type':'DNI','document':'00000000T','address':'Calle ficticia 0','town':'Ciudad ficticia','postal_code':'00000','phone':'+34000000000','phone_secondary':'','email':'prueba.despliegue@example.invalid'},'brand':'fitness','tariff_id':tariff['id'],'payment_method':'cash','consents':{'legal_id':legal['id'],'contract':True,'privacy':True,'sepa':False,'marketing':False}}
        client.post('draft_save',data=data)
        jpeg=(ROOT/'public/assets/logo.jpg').read_bytes();comment=b'F'*45000
        jpeg=jpeg[:2]+(b'\xff\xfe'+struct.pack('!H',len(comment)+2)+comment)*2+jpeg[2:]
        assert len(jpeg)>65536
        client.post('photo_save',image='data:image/jpeg;base64,'+base64.b64encode(jpeg).decode(),confirmed=True)
        status,photo=client.request('/alta/api.php?action=draft_photo');assert status==200 and photo.startswith(b'\xff\xd8')
        assert guest.request('/alta/api.php?action=draft_photo')[0]==403
        checks.append('Formulario y foto ficticia de más de 64 KB; aislamiento de sesión')
        assert client.request('/alta/api.php',{'action':'draft_prepare'})[0]==409
        checks.append('Firma real bloqueada mientras los textos legales estén pendientes')
        client.post('draft_cancel');draft=False
        state=access({'operation':'status','id':identity});assert state['drafts']==0 and state['contracts']==0
        checks.append('Prueba cancelada sin dejar altas ni contratos')
        for path in ['/alta/.private/config.json','/alta/app/Core.php','/alta/scripts/setup.php','/alta/deploy/vps_smoke.py','/alta/assets/missing.php']:
            assert guest.request(path)[0]==404
        checks.append('Código PHP, configuración y archivos privados inaccesibles')
        assert guest.request('/reservas/')[0]==401
        assert guest.request('/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=invalid&hub.challenge=smoke')[0] in (401,403)
        assert guest.request('/webhooks/whatsapp',{'object':'invalid_smoke','entry':[]})[0] in (400,401,403)
        checks.append('Reservas protegidas; webhook rechaza verificación y firma inválidas')
        return {'passed':len(checks),'checks':checks,'real_personal_data_used':False,'messages_sent':0,'contracts_created':0}
    finally:
        if draft and client:
            try:client.post('draft_cancel')
            except Exception:pass
        access({'operation':'delete','id':identity})

if __name__=='__main__':
    try:print(json.dumps(main(),ensure_ascii=False))
    except Exception as error:print(json.dumps({'error':type(error).__name__,'details':'No se muestran credenciales ni respuestas con datos.'}));raise SystemExit(1)
