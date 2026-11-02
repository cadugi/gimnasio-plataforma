"""Empaqueta únicamente código/documentación autorizados; excluye estado local y secretos."""
import hashlib,json,re,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES={'app','public','migrations','scripts','tests','fixtures','docs','deploy'}
ROOT_FILES={'README.md','INFORME_IMPLEMENTACION.md','.gitignore','.env.example','Iniciar aplicación.cmd','Detener aplicación.cmd','Configurar acceso.cmd','INICIAR_DEMO.cmd'}
FORBIDDEN={'.private','__pycache__','.git','node_modules'}
ALLOWED_EXTENSIONS={'.php','.js','.css','.jpg','.png','.md','.json','.sql','.py','.ps1','.conf','.html','.pdf','.txt'}

def build():
    files=[]
    for p in ROOT.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(ROOT)
        if any(part in FORBIDDEN for part in rel.parts):continue
        if len(rel.parts)==1:
            if p.name not in ROOT_FILES:continue
        elif rel.parts[0] not in DIRECTORIES or p.suffix.lower() not in ALLOWED_EXTENSIONS:continue
        files.append((rel,p.read_bytes()))
    config=ROOT/'.private/config.json';secret_values=[]
    if config.is_file():
        cfg=json.loads(config.read_text(encoding='utf-8'));keyfile=Path(cfg['key_file'])
        if keyfile.is_file():secret_values=[v.encode() for v in json.loads(keyfile.read_text()).values()]
    for rel,data in files:
        assert not any(value in data for value in secret_values),f'Secreto detectado: {rel}'
        assert not re.search(rb'\b[0-9]{8,12}:AA[A-Za-z0-9_-]{25,}\b',data),f'Token detectado: {rel}'
        assert not data.startswith(b'SQLite format 3'),f'Base excluida: {rel}'
        assert not re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',data),f'Clave privada detectada: {rel}'
    manifest=''.join(hashlib.sha256(data).hexdigest()+'  '+rel.as_posix()+'\n' for rel,data in sorted(files))
    target=ROOT.parent/(ROOT.name+'_Portable.zip')
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel,data in files:z.writestr(ROOT.name+'/'+rel.as_posix(),data)
        z.writestr(ROOT.name+'/MANIFEST.sha256',manifest)
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    return {'zip':str(target),'files':len(files)+1,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size,'private_state_included':False,'known_secrets_found':0}

if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False,indent=2))
