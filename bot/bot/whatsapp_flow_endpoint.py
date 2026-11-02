"""Meta data endpoint: signed requests, RSA-OAEP/SHA256, AES-128-GCM."""
import base64
import hashlib
import hmac
import json
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .transport import Rejected, TemporaryFailure


class FlowEndpoint:
    def __init__(self,secret,pem,service_factory):
        self.secret=secret
        self.key=serialization.load_pem_private_key(pem,password=None)
        if not isinstance(self.key,rsa.RSAPrivateKey) or self.key.key_size<2048:raise ValueError('RSA key required')
        self.factory=service_factory

    def process(self,raw,signature):
        expected='sha256='+hmac.new(self.secret.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature or ''):return 432,b''
        try:
            envelope=json.loads(raw)
            key=self.key.decrypt(base64.b64decode(envelope['encrypted_aes_key'],validate=True),
                                 padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
            iv=base64.b64decode(envelope['initial_vector'],validate=True)
            if len(key)!=16 or len(iv)!=16:raise ValueError('Invalid key/IV')
            request=json.loads(AESGCM(key).decrypt(iv,base64.b64decode(envelope['encrypted_flow_data'],validate=True),None))
            if not isinstance(request,dict):raise ValueError('Invalid request')
        except (ValueError,KeyError,TypeError,InvalidTag):return 421,b''
        try:
            with self.factory() as service:
                response=service.exchange(request)
        except Rejected as error:
            # 427 desactiva el botón del Flow y muestra este mensaje (sin cifrar, según Meta).
            message={'FLOW_EXPIRED':'Este proceso ha caducado. Vuelve a reservar desde el menú.',
                     'ACCESS_DENIED':'Esta persona ya no está autorizada para reservar.',
                     'SERVICE_UNAVAILABLE':'No hemos podido conectar con el gimnasio. Inténtalo de nuevo en unos segundos.'}.get(
                         error.code,'La selección ha cambiado. Cierra y vuelve a abrir el menú.')
            return 427,json.dumps({'error_msg':message}).encode()
        except TemporaryFailure:return 503,b''
        encrypted=AESGCM(key).encrypt(bytes(v^255 for v in iv),json.dumps(response).encode(),None)
        return 200,base64.b64encode(encrypted)
