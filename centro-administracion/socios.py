"""Lecturas federadas de socios. Identidades enlazadas solo por referencia explícita.
Sesiones SSO nominales en memoria; referencias firmadas y ligadas a la sesión del Centro.
No se persisten fichas, búsquedas, teléfonos ni índices de datos personales.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor


# Secreto solo del servidor; los tokens CSRF visibles en el navegador no son claves de firma.
_REF_KEY = secrets.token_bytes(32)


class SearchError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def query(value):
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= 60 or any(ord(c) < 32 for c in value):
        raise SearchError('Escribe entre 2 y 60 caracteres del nombre, teléfono o número de socio.')
    return value.strip()


def pack(session, payload):
    body = base64.urlsafe_b64encode(json.dumps(dict(payload, expires=int(time.time())+1800), separators=(',', ':')).encode()).decode().rstrip('=')
    mac = hmac.new(_REF_KEY, (session['h']+session['csrf']+body).encode(), hashlib.sha256).hexdigest()
    return body+'.'+mac


def unpack(session, token, kind=None):
    try:
        if not isinstance(token, str) or len(token)>3000:raise ValueError()
        body, mac = token.split('.')
        expected = hmac.new(_REF_KEY, (session['h']+session['csrf']+body).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):raise ValueError()
        p = json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        if p['expires'] < time.time() or (kind and p['kind'] != kind):raise ValueError()
        return p
    except (ValueError, KeyError, TypeError):
        raise SearchError('La selección ha caducado. Busca de nuevo.', 400)


def merge(portal, innux, reservations):
    """Nunca agrupar por nombre, teléfono, ni por un número sin vínculo de Innux."""
    result = [dict(v, source='altas') for v in portal]
    linked = {v['innux_reference']: v for v in result if v.get('innux_reference')}
    for value in innux:
        if value.get('innux_reference') in linked:
            linked[value['innux_reference']]['in_innux'] = True
        else:
            result.append(dict(value, source='innux'))
    result.extend(dict(v, source='reservas') for v in reservations)
    return result


class Gateway:
    def __init__(self, transport, login):
        self.transport, self.login = transport, login
        self.sessions, self.lock = {}, threading.RLock()

    def drop(self, s):
        with self.lock:
            for key in list(self.sessions):
                if key[0]==s['h']:self.sessions.pop(key,None)

    def module(self, s, module, path, body=None, retry=True):
        key=(s['h'],module,s['role'])
        with self.lock:
            now=time.time()
            self.sessions={k:v for k,v in self.sessions.items() if now-v[0]<600}
            cached=self.sessions.get(key)
            if not cached:
                cookies=self.login(module,s['name'],s['role'])
                if not cookies:raise SearchError('No se pudo abrir la consulta.',503)
                cookie='; '.join(c.split(';')[0] for c in cookies)
                base='/alta/admin/api.php?action=bootstrap' if module=='altas' else '/alta/caja/api/me?clients=1'
                r, raw=self.transport('GET',base,headers={'Cookie':cookie})
                value=json.loads(raw)
                if r.status!=200:raise SearchError('No se pudo abrir la consulta.',503)
                csrf=value['data']['csrf'] if module=='altas' else value.get('csrf')
                # Caja /me no expone CSRF en todas las versiones; /bootstrap sí lo hace.
                if module=='caja' and not csrf:
                    r,raw=self.transport('GET','/alta/caja/api/bootstrap',headers={'Cookie':cookie});csrf=json.loads(raw).get('csrf')
                if not csrf:raise SearchError('No se pudo abrir la consulta.',503)
                cached=(now,cookie,csrf);self.sessions[key]=cached
        headers={'Cookie':cached[1],'X-CSRF-Token':cached[2],'Content-Type':'application/json'}
        r,raw=self.transport('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers)
        if r.status==401 and retry:
            with self.lock:self.sessions.pop(key,None)
            return self.module(s,module,path,body,False)
        value=json.loads(raw)
        if r.status!=200 or not value.get('ok'):raise SearchError('No se pudo consultar '+('Altas' if module=='altas' else 'Innux')+'.',503)
        return value.get('data') if module=='altas' else value

    def altas(self,s,action,**data):
        return self.module(s,'altas','/alta/admin/api.php',dict(action=action,**data))

    def reservas(self,s,cookie,**data):
        if s['role']!='owner':raise SearchError('Tu cuenta no tiene acceso a Reservas.',403)
        r,raw=self.transport('POST','/admin/socios.php',json.dumps(data),{'Content-Type':'application/json','Cookie':cookie,'X-TopFitness-Request':'1'})
        value=json.loads(raw)
        if r.status!=200 or not value.get('success'):raise SearchError('Reservas no está disponible ahora.',503)
        return value

    def wrap(self,s,items):
        out=[]
        for v in items:
            p={'kind':'member','source':v['source']}
            if v['source']=='altas':p['id']=v['id']
            elif v['source']=='innux':p.update(id=v['id'],search_id=v['search_id'])
            else:p.update(name=v['name'],phone=v['phone'])
            out.append(dict(v,ref=pack(s,p)))
        return out

    def search(self,s,cookie,q):
        q=query(q);result={'items':[],'sources':{},'has_more':False}
        calls={'altas':lambda:self.altas(s,'member_search',query=q),
               'reservas':lambda:self.reservas(s,cookie,action='search',query=q),
               'innux':lambda:self.altas(s,'member_innux_start',query=q)}
        values={}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={k:pool.submit(fn) for k,fn in calls.items()}
            for name,future in futures.items():
                try:
                    values[name]=future.result();result['sources'][name]={'state':'ok'}
                    result['has_more'] |= values[name].get('has_more',False)
                except Exception:
                    result['sources'][name]={'state':'unavailable' if name!='reservas' or s['role']=='owner' else 'forbidden'}
        result['items']=self.wrap(s,merge(values.get('altas',{}).get('items',[]),[],values.get('reservas',{}).get('items',[])))
        if 'innux' in values:
            result['pending']=pack(s,{'kind':'search','id':values['innux']['id']})
            result['sources']['innux']={'state':'pending'}
        return result

    def poll_search(self,s,token):
        p=unpack(s,token,'search');r=self.altas(s,'member_innux_result',id=p['id'])
        items=[dict(v,source='innux',search_id=p['id']) for v in r['items']]
        return dict(state=r['state'],items=self.wrap(s,items),has_more=r.get('has_more',False))

    def detail(self,s,cookie,token):
        p=unpack(s,token,'member');member=None;portal={};warnings=[]
        if p['source']=='altas':
            portal=self.altas(s,'member_detail',id=p['id']);member=portal['member']
            if not member:raise SearchError('Ficha no encontrada.',404)
        elif p['source']=='innux':
            v=self.altas(s,'member_innux_result',id=p['search_id'],client_id=p['id']);member=v['items'][0]
            try:portal=self.altas(s,'member_detail',innux_reference=member['innux_reference'])
            except Exception:warnings.append('No se pudieron consultar los contratos de Altas.')
            if portal.get('member'):member=dict(member,**portal['member'])
        elif p['source']=='reservas':member={'name':p['name'],'phone':p['phone']}
        else:raise SearchError('Selección no válida.')
        result={'member':member,'portal':portal,'warnings':warnings,'source':p['source']}
        try:result['reservations']=self.reservas(s,cookie,action='detail',name=member['name'],phone=member.get('phone',''),reference=member.get('innux_reference') or '',selected=p['source']=='reservas')
        except Exception:result['reservations']={'unavailable':True,'forbidden':s['role']!='owner'}
        ref=member.get('innux_reference') or ''
        if re.fullmatch(r'INNUX:[1-9][0-9]{0,19}',ref) and str(member.get('number') or '').isdigit():
            jobs={}
            for operation,path in [('client','get'),('quotas','history')]:
                if operation=='quotas' and s['role']=='viewer':continue
                try:
                    r=self.module(s,'caja','/alta/caja/api/clients/'+path,dict(client_id=ref[6:],number=str(member['number']),**({'limit':30} if operation=='quotas' else {})))
                    jobs[operation]=pack(s,{'kind':'quota','id':r['job_id'],'operation':'clients.'+path})
                except Exception:pass
            result['jobs']=jobs
            result['quotas_available']=bool(jobs)
        else:result['quotas_available']=False
        return result

    def poll_quota(self,s,token):
        p=unpack(s,token,'quota')
        if not re.fullmatch(r'[a-f0-9-]{36}',p['id']) or p['operation'] not in ('clients.get','clients.history'):raise SearchError('Consulta no válida.')
        if p['operation']=='clients.history' and s['role'] not in ('owner','manager'):raise SearchError('Tu cuenta no tiene permiso para consultar cuotas.',403)
        r=self.module(s,'caja','/alta/caja/api/jobs/'+p['id'])['job']
        if r['operation']!=p['operation']:raise SearchError('Consulta no válida.',403)
        return {'status':r['status'],'result':r['result'] if r['status']=='succeeded' else None,'updated':r.get('completed_at'),'operation':p['operation']}
