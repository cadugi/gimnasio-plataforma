#!/usr/bin/env python3
"""Pruebas HTTP de lectura. Recibe la contraseña por stdin; no imprime secretos."""
import http.client, json, ssl
ORIGIN='https://whatsapp.gimnasio.example'
class Browser:
    def __init__(self):self.cookies={};self.csrf=''
    def request(self,method,path,body=None):
        # Conectar a loopback manteniendo SNI y validación del certificado público.
        c=http.client.HTTPSConnection('whatsapp.gimnasio.example',context=ssl.create_default_context(),timeout=25)
        import socket
        c._create_connection=lambda address,timeout,source_address=None:socket.create_connection(('127.0.0.1',443),timeout,source_address)
        headers={'Origin':ORIGIN,'X-TopFitness-Request':'1'}
        if self.cookies:headers['Cookie']='; '.join(k+'='+v for k,v in self.cookies.items())
        if self.csrf:headers['X-CSRF-Token']=self.csrf
        if body is not None:headers['Content-Type']='application/json';body=json.dumps(body)
        c.request(method,path,body,headers);r=c.getresponse();data=r.read()
        for key,val in r.getheaders():
            if key.lower()=='set-cookie':
                pair=val.split(';')[0];name,value=pair.split('=',1);self.cookies[name]=value
        status=r.status;c.close()
        try:out=json.loads(data)
        except Exception:out={}
        if status!=200:raise RuntimeError(str(status)+' '+path.split('?')[0])
        if isinstance(out,dict) and (out.get('ok') is False or out.get('success') is False):raise RuntimeError('Respuesta fallida '+path.split('?')[0])
        return out

def verify(password):
    result=[]
    cc=Browser();d=cc.request('POST','/administracion/api/login',dict(user='qa_total',pw=password));cc.csrf=d['csrf']
    me=cc.request('GET','/administracion/api/me');assert me['user']=='qa_total' and me['role']=='owner';result.append('centro_login_owner')
    a=cc.request('GET','/administracion/api/diario/acceso');assert a['unlocked'] and a['qa_bypass']
    cc.request('POST','/administracion/api/diario/desbloquear',{})
    cc.request('POST','/administracion/api/diario/bloquear',{})
    assert cc.request('GET','/administracion/api/diario/acceso')['unlocked']
    cc.request('GET','/administracion/api/diario');result.append('diario_sin_password_y_sin_rebloqueo')
    cc.request('GET','/admin/')
    cc.request('GET','/admin/obtener_horarios.php');result.append('reservas_sso_admin_sin_otro_login')
    for mod in ['altas','caja']:
        cc.request('POST','/administracion/api/modulo/'+mod,{})
    cc.request('GET','/alta/admin/')
    a=cc.request('GET','/alta/admin/api.php?action=bootstrap')['data'];assert a['user']['username']=='qa_total' and a['user']['role']=='admin';result.append('altas_sso_admin_nominal')
    cc.request('GET','/alta/caja/')
    a=cc.request('GET','/alta/caja/api/me');u=a.get('user',{});assert u['username']=='qa_total' and u['role']=='admin';assert set(u['perms'])=={'close','config','export','quotas','quotas_delete','register','reopen','users','view'};result.append('caja_sso_admin_9_permisos')
    altas=Browser();a=altas.request('GET','/alta/admin/api.php?action=bootstrap')['data'];altas.csrf=a['csrf']
    a=altas.request('POST','/alta/admin/api.php',dict(action='login',username='qa_total',password=password))['data'];altas.csrf=a['csrf']
    a=altas.request('GET','/alta/admin/api.php?action=bootstrap')['data'];assert a['user']['username']=='qa_total' and a['user']['role']=='admin';result.append('altas_login_directo')
    caja=Browser();a=caja.request('POST','/alta/caja/api/login',dict(username='qa_total',password=password));caja.csrf=a['csrf']
    a=caja.request('GET','/alta/caja/api/me');assert a['user']['username']=='qa_total' and not a['user']['must_change'];result.append('caja_login_directo_sin_cambio_obligatorio')
    public=Browser()
    for path in ['/reservas/','/alta/','/alta/caja/','/administracion/']:public.request('GET',path)
    result.append('4_rutas_publicas_200')
    return result
if __name__=='__main__':
    import sys
    print(json.dumps(verify(sys.stdin.read().strip())))
