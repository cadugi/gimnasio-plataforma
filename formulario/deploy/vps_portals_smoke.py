"""Pruebas de la separación de portales en HTTPS; sin datos de personas reales."""
import http.cookiejar,json,pathlib,secrets,subprocess,sys,urllib.request
from vps_smoke import access,Client,BASE
ROOT=pathlib.Path(__file__).resolve().parents[1]

class PortalClient(Client):
    def __init__(self,portal='client',jar=None):
        self.portal=portal;self.csrf='';self.jar=jar if jar is not None else http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar));self.bootstrap()
    def request(self,path,payload=None,headers=None):
        if self.portal=='admin' and path.startswith('/alta/api.php'):path=path.replace('/alta/api.php','/alta/admin/api.php',1)
        return super().request(path,payload,headers)
    def bootstrap(self):
        code,result=self.request('/alta/api.php?action=bootstrap');assert code==200
        self.csrf=result['data']['csrf'];return result['data']

def main():
    identity=secrets.token_hex(16);username='qa_deploy_'+secrets.token_hex(5);password=secrets.token_urlsafe(30)+'Aa9'
    hashed=subprocess.run(['/usr/bin/openssl','passwd','-apr1','-stdin'],input=password.encode()+b'\n',capture_output=True,check=True).stdout.decode().strip()
    access({'operation':'create','id':identity,'username':username,'hash':hashed})
    client=None;staff=None;draft=False;checks=[]
    try:
        guest=PortalClient();assert guest.bootstrap()['portal']=='client' and guest.bootstrap()['mode']=='guest'
        assert guest.request('/alta/api.php',{'action':'login','username':username,'password':password})[0]==403
        for action in ['contracts','contract_detail','configuration','enrollment_inbox','dashboard','save_user']:
            assert guest.request('/alta/api.php',{'action':action})[0]==403
        _,html=guest.request('/alta/');assert b'assets/admin.js' not in html
        checks.append('Acceso de clientes sin panel, contraseña administrativa ni módulo de administración')
        staff=PortalClient('admin');staff.post('login',username=username,password=password)
        assert staff.bootstrap()['mode']=='admin'
        assert staff.request('/alta/api.php',{'action':'draft_new'})[0]==403
        invitation=staff.post('tablet_invitation');code=invitation['code']
        assert staff.bootstrap()['mode']=='guest'
        assert staff.request('/alta/api.php',{'action':'contracts'})[0]==401
        checks.append('Generar código cierra esa sesión administrativa también en el servidor')
        client=PortalClient('client',staff.jar);client.post('tablet_activate',code=code)
        assert client.bootstrap()['mode']=='kiosk' and client.bootstrap()['user'] is None
        stranger=PortalClient();assert stranger.request('/alta/api.php',{'action':'tablet_activate','code':code})[0]==403
        for action in ['contracts','contract_detail','configuration','enrollment_inbox','audit','save_user','tablet_invitation','login']:
            assert client.request('/alta/api.php',{'action':action})[0]==403
        assert PortalClient('admin',client.jar).bootstrap()['mode']=='guest'
        checks.append('Código de un solo uso y sesión de clientes sin permisos del personal')
        b=client.bootstrap();tariff=next(x for x in b['catalog']['tariffs'] if x['brand']=='fitness');legal=next(x for x in b['catalog']['legal'] if x['brand']=='fitness')
        client.post('draft_new');draft=True
        data={'personal':{'name':'PRUEBA','surname':'PORTALES FICTICIA','birth_date':'1994-03-12','document_type':'DNI','document':'00000000T','address':'Calle ficticia 0','town':'Ciudad ficticia','postal_code':'00000','phone':'+34000000000','phone_secondary':'','email':'prueba.portales@example.invalid'},'brand':'fitness','tariff_id':tariff['id'],'payment_method':'cash','consents':{'legal_id':legal['id'],'contract':True,'privacy':True,'sepa':False,'marketing':False}}
        client.post('draft_save',data=data)
        prepared_status,prepared=client.request('/alta/api.php',{'action':'draft_prepare'})
        assert prepared_status==(200 if legal['approved'] else 409)
        client.post('draft_cancel');draft=False
        assert client.bootstrap()['draft'] is None
        client.post('tablet_lock');assert client.bootstrap()['mode']=='guest'
        checks.append('Inscripción ficticia preparada con texto autorizado, sin firmar ni crear socio' if legal['approved'] else 'Inscripción propia aislada; textos pendientes bloquean firma')
        assert all(c.secure and (c.path=='/alta/' if c.name=='TF_ALTAS_CLIENT' else c.path=='/alta/admin/') for c in client.jar if c.name.startswith('TF_ALTAS_'))
        checks.append('Cookies HTTPS independientes con rutas diferentes')
        for path in ['/alta/.private/config.json','/alta/admin/.private/config.json','/alta/app/Core.php','/alta/admin/app/Core.php','/alta/admin/assets/missing.php']:
            assert guest.request(path)[0]==404
        reservations_status=guest.request('/reservas/')[0]
        assert guest.request('/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=invalid&hub.challenge=smoke')[0] in (401,403)
        assert guest.request('/webhooks/whatsapp',{'object':'invalid_smoke','entry':[]})[0] in (400,401,403)
        checks.append('Archivos privados del formulario cerrados y webhook rechaza solicitudes sin autorización')
        return {'passed':len(checks),'checks':checks,'reservations_unauthenticated_status':reservations_status,'reservations_auth_verified':reservations_status==401,'real_personal_data_used':False,'messages_sent':0,'contracts_created':0,'client_portal':'https://whatsapp.gimnasio.example/alta/','admin_portal':'https://whatsapp.gimnasio.example/alta/admin/'}
    finally:
        if draft and client:
            try:client.post('draft_cancel')
            except Exception:pass
        access({'operation':'delete','id':identity})

if __name__=='__main__':
    try:print(json.dumps(main(),ensure_ascii=False))
    except Exception as error:print(json.dumps({'error':type(error).__name__,'details':'Se omiten respuestas con credenciales o datos.'}));raise SystemExit(1)
