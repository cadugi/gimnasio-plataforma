"""Ayudante elevado de inspección. No admite guardar, escribir datos o ejecutar órdenes."""
from pathlib import Path
import ctypes,json,os,sys,time
from collections import deque

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.private/innux-inspection'
sys.path.insert(0,str(ROOT.parent/'CajaGimnasio'))
from innux_launcher import NativeInnux,navigate,is_registration,normal

CAPTIONS={'guardar','guardar cambios','cancelar','aceptar','nuevo cliente','novo cliente',
 'nombre','nome','apellidos','apelidos','nif','dni','dni/nif','numero','número','nº cliente',
 'data de nascimento','fecha de nacimiento','data nascimento','morada','dirección',
 'localidade','población','codigo postal','código postal','email','e-mail','telefone',
 'telemóvel','telemovel','fotografia','foto','activo','ativo','datos','dados','geral','general',
 'dados pessoais','datos personales','titular','iban','banco','mensalidade','cuota'}

def write(result):
    result['timestamp']=time.time();result['helper_pid']=os.getpid();result['can_save']=False
    temporary=STATE/'report.next';temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(STATE/'report.json')

class RestrictedNative(NativeInnux):
    def __init__(self):super().__init__();self.actions=[]
    def launch(self):raise RuntimeError('Abre Innux manualmente.')
    def activate(self,window):
        if not (normal(window['title']).startswith('innux sports') or is_registration(window['title'])):raise RuntimeError('Ventana pendiente.')
        super().activate(window)
    def click(self,button):
        super().click(button);self.actions.append(normal(button['title']))

def inspect(native):
    root,modals=native.inspect()
    result={'state':'READY','innux_running':root is not None,'modal_count':len(modals),'registration_open':False,'controls':[],'actions':native.actions}
    registration=next((w for w in modals if is_registration(w['title'])),None)
    from pywinauto import Desktop
    if registration:
        start=Desktop(backend='uia').window(handle=registration['handle']).wrapper_object()
        result['registration_open']=True
    elif root:
        # Innux embeds the customer page inside MainForm, rather than using a modal.
        # This page is shared by new and existing customers: do not infer NEW state.
        main=Desktop(backend='uia').window(handle=root['handle']).wrapper_object()
        from innux_reception_ui import visible_controls
        pages=[node for node in visible_controls(main) if node.element_info.automation_id=='frmPaginaCliente']
        pages=[page for page in pages if page.is_visible()]
        if len(pages)!=1:return result
        start=pages[0]
        result['state']='CLIENT_PAGE_VISIBLE'
        result['creation_mode_verified']=False
    else:return result
    queue=deque([(start,0,'root')]);count=0
    while queue and count<600:
        node,depth,path=queue.popleft();count+=1
        try:
            info=node.element_info;kind=info.control_type
            if kind in {'DataGrid','Table','DataItem','List','ListItem','Tree','TreeItem'}:continue
            if not node.is_visible():continue
            control={'path':path,'type':kind,'automation_id':info.automation_id,'class_name':info.class_name,'enabled':node.is_enabled()}
            # Never serialize editable values, arbitrary names, grid rows or screenshots.
            if kind in {'Text','Button','TabItem','Group'}:
                label=node.window_text()
                if normal(label) in CAPTIONS:control['caption']=label
            result['controls'].append(control)
            if depth<15:
                for index,child in enumerate(node.children()):queue.append((child,depth+1,path+'/'+str(index)))
        except Exception:continue
    return result

def main():
    STATE.mkdir(parents=True,exist_ok=True)
    if not ctypes.windll.shell32.IsUserAnAdmin():write({'state':'ADMIN_REQUIRED'});return
    # An older request must not be executed on startup.
    request=STATE/'request.json';last=request.read_bytes() if request.exists() else b''
    native=RestrictedNative();write(inspect(native));deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        time.sleep(.3)
        try:
            raw=request.read_bytes() if request.exists() else b''
            if not raw or raw==last:continue
            last=raw;command=json.loads(raw)
            if command.get('action')=='stop':write({'state':'STOPPED'});return
            if command.get('action')=='open_new_client':
                root,modals=native.inspect()
                if root is None or (modals and not any(is_registration(w['title']) for w in modals)):
                    write({'state':'EXISTING_WINDOW_REQUIRES_ATTENTION','request_id':command.get('id')});continue
                try:navigate(native,timeout=15)
                except Exception:
                    report=inspect(native);report['state']='MANUAL_OPEN_REQUIRED';report['request_id']=command.get('id');write(report);continue
            elif command.get('action')!='inspect':
                write({'state':'ACTION_REJECTED','request_id':command.get('id')});continue
            result=inspect(native);result['request_id']=command.get('id');write(result)
        except Exception:write({'state':'INSPECTION_FAILED'})
    write({'state':'EXPIRED'})

if __name__=='__main__':
    try:main()
    except Exception:
        STATE.mkdir(parents=True,exist_ok=True);write({'state':'INSPECTION_FAILED'})
