"""Official VPS reservations. No browser-supplied principal or personal data."""
import json
import urllib.request
import urllib.error
from .transport import Rejected, TemporaryFailure, Backend

URL='https://whatsapp.gimnasio.example/reservas/service.php'

class OfficialBackend:
    official_web=True
    timeout=15
    def __init__(self,secret):self.secret=secret
    def call(self,user,**data):
        request=urllib.request.Request(URL,data=json.dumps(dict(data,user_id=str(user))).encode(),headers={'Authorization':'Bearer '+self.secret,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=self.timeout) as response:result=json.load(response)
        except urllib.error.HTTPError as error:
            if error.code>=500:raise TemporaryFailure('OFFICIAL_BACKEND_UNAVAILABLE') from None
            try:result=json.loads(error.read(4096))
            except (ValueError,OSError):raise Rejected('REQUEST_REJECTED') from None
        except (OSError,ValueError):raise TemporaryFailure('OFFICIAL_BACKEND_UNAVAILABLE') from None
        if not result.get('ok'):raise Rejected(result.get('error','REQUEST_REJECTED'))
        return result

def booking_backend(config):
    if config.get('WA_OFFICIAL_WEB')=='1':return OfficialBackend(config['WA_BACKEND_SECRET'])
    return Backend(config['WA_BACKEND_URL'],config['WA_BACKEND_SECRET'],portable=True)
