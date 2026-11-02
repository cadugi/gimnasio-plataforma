"""Recepción local conectada al formulario público; credenciales solo en memoria."""
import ctypes
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from innux_reception_core import Enrollment, Portal, Registry, ReceptionError, ORIGIN, require
from innux_reception_ui import OfficialUI


class App:
    def __init__(self, root):
        self.root = root; self.portal = Portal(); self.engine = None; self.items = []
        self.photo_path = None
        root.title('TOP FITNESS · Altas de recepción'); root.geometry('910x620'); root.configure(bg='#111411')
        style = ttk.Style(); style.theme_use('clam')
        style.configure('TFrame', background='#111411')
        style.configure('TLabel', background='#111411', foreground='#f0f4ef', font=('Segoe UI',11))
        style.configure('TButton', font=('Segoe UI',11), padding=10, background='#65d837', foreground='#071205')
        self.frame = ttk.Frame(root,padding=24); self.frame.pack(fill='both',expand=True)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.login_screen()

    def clear(self):
        for widget in self.frame.winfo_children(): widget.destroy()

    def safe(self, fn):
        self.root.config(cursor='watch'); self.root.update_idletasks()
        try: return fn()
        except ReceptionError as exc: messagebox.showwarning('Revisar alta',str(exc),parent=self.root)
        except Exception: messagebox.showerror('Operación interrumpida','No se ha podido completar la operación. Revisa Innux antes de repetir. No se muestran datos técnicos ni personales.',parent=self.root)
        finally: self.root.config(cursor='')

    def login_screen(self):
        self.clear()
        ttk.Label(self.frame,text='TOP FITNESS',font=('Segoe UI',26,'bold'),foreground='#65d837').pack(anchor='w')
        ttk.Label(self.frame,text='Recepción · Conexión con Innux',font=('Segoe UI',16)).pack(anchor='w',pady=(4,30))
        ttk.Label(self.frame,text='Usa tu cuenta de trabajador del formulario web.').pack(anchor='w')
        ttk.Label(self.frame,text='Usuario').pack(anchor='w',pady=(20,4)); user=ttk.Entry(self.frame,width=40);user.pack(anchor='w')
        ttk.Label(self.frame,text='Contraseña').pack(anchor='w',pady=(12,4)); password=ttk.Entry(self.frame,width=40,show='●');password.pack(anchor='w')
        def login():
            secret=password.get();password.delete(0,'end')
            try:self.portal.login(user.get(),secret)
            finally:secret=None
            self.inbox()
        ttk.Button(self.frame,text='Conectar',command=lambda:self.safe(login)).pack(anchor='w',pady=20)
        ttk.Label(self.frame,text='La contraseña y la sesión no se guardan en archivos.').pack(anchor='w')
        user.focus_set()

    def inbox(self):
        data=self.portal.request('enrollment_inbox')
        self.items=[item for item in data['items'] if item['innux_state']=='PENDING_MANUAL']
        self.clear()
        ttk.Label(self.frame,text='TOP FITNESS · ALTAS',font=('Segoe UI',23,'bold'),foreground='#65d837').pack(anchor='w')
        ttk.Label(self.frame,text='Selecciona un contrato firmado. La ficha debe estar aceptada por el centro.').pack(anchor='w',pady=12)
        self.list=tk.Listbox(self.frame,bg='#1c211b',fg='white',selectbackground='#376923',font=('Segoe UI',12),height=10)
        self.list.pack(fill='both',expand=True)
        for item in self.items:self.list.insert('end',item['name']+'  ·  '+item['reference']+('  ·  Pendiente aceptación' if not item['center_accepted_at'] else ''))
        ttk.Button(self.frame,text='Preparar ficha en Innux',command=lambda:self.safe(self.fill)).pack(side='left',pady=18)
        ttk.Button(self.frame,text='Actualizar',command=lambda:self.safe(self.inbox)).pack(side='left',padx=10)
        ttk.Button(self.frame,text='Panel web',command=lambda:webbrowser.open(ORIGIN+'/alta/admin/')).pack(side='right')

    def fill(self):
        selection=self.list.curselection();require(len(selection)==1,'Selecciona una inscripción.')
        detail=self.portal.request('contract_detail',id=self.items[selection[0]]['id'])
        require(self.engine is None,'Hay una operación anterior pendiente de revisión. Cierra el conector para empezar otra.')
        import pyodbc
        self.engine=Enrollment(Registry(pyodbc.connect),OfficialUI())
        # Do not discard partially written state after an exception.
        self.engine.fill(detail)
        self.prepared()

    def prepared(self):
        self.clear();detail=self.engine.detail;p=self.engine.personal
        ttk.Label(self.frame,text='Revisa la ficha en Innux',font=('Segoe UI',23,'bold'),foreground='#65d837').pack(anchor='w')
        ttk.Label(self.frame,text=p['name']+' '+p['surname'],font=('Segoe UI',18)).pack(anchor='w',pady=18)
        ttk.Label(self.frame,text='Número propuesto por Innux: '+self.engine.number).pack(anchor='w')
        ttk.Label(self.frame,text='Los datos personales están rellenados. No se han asignado cuotas ni datos bancarios.').pack(anchor='w',pady=12)
        ttk.Label(self.frame,text='Comprueba los datos, la fecha y la foto antes de guardar.\nInnux aplicará sus validaciones y las condiciones de su licencia.').pack(anchor='w',pady=12)
        if detail.get('has_photo'):
            ttk.Button(self.frame,text='Preparar foto del formulario',command=lambda:self.safe(self.prepare_photo)).pack(anchor='w',pady=8)
        ttk.Button(self.frame,text='Guardar ficha en Innux',command=lambda:self.safe(self.save)).pack(anchor='w',pady=16)
        ttk.Button(self.frame,text='Comprobar alta y vincular número',command=lambda:self.safe(self.verify)).pack(anchor='w')

    def prepare_photo(self):
        import urllib.request, subprocess, tempfile, hashlib
        from innux_reception_core import ENDPOINT
        detail=self.portal.request('contract_detail',id=self.engine.detail['id'])
        require(detail['state']=='SIGNED','El contrato ya no está firmado.')
        request=urllib.request.Request(ENDPOINT+'?action=enrollment_photo&id='+detail['id'])
        with self.portal.http.open(request,timeout=20) as response:
            require(response.headers.get_content_type()=='image/jpeg','No se pudo obtener la foto.')
            photo=response.read(900001)
        require(len(photo)<=900000 and photo[:2]==b'\xff\xd8','Foto no válida.')
        require(hashlib.sha256(photo).hexdigest()==detail['snapshot'].get('photo_hash'),'La foto no coincide con la del contrato firmado.')
        if self.photo_path is None:
            folder=Path(tempfile.mkdtemp(prefix='TopFitnessFoto-',dir=os.environ['LOCALAPPDATA']))
            sid=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True).stdout.split(',')[-1].strip().strip('"')
            import re
            require(re.fullmatch(r'S-1-[0-9-]+',sid),'No se pudo proteger el archivo temporal.')
            subprocess.run(['icacls',str(folder),'/inheritance:r','/grant:r',sid+':(OI)(CI)F','SYSTEM:(OI)(CI)F'],capture_output=True,check=True,creationflags=0x08000000)
            self.photo_path=folder/'foto-inscripcion.jpg'
        self.photo_path.write_bytes(photo)
        # The installed photo picker has not yet been verified: never click an unknown control.
        self.root.clipboard_clear();self.root.clipboard_append(str(self.photo_path))
        messagebox.showinfo('Foto preparada','En la ficha de Innux pulsa el botón de buscar foto. Pega la ruta copiada con Ctrl+V y abre la imagen.\n\nEl archivo temporal se elimina al cerrar este conector.',parent=self.root)

    def save(self):
        require(messagebox.askyesno('Confirmar alta','¿Has revisado los datos y la fotografía? Se pulsará Guardar en el programa oficial de Innux.',parent=self.root),'Guardado cancelado.')
        fresh=self.portal.request('contract_detail',id=self.engine.detail['id'])
        self.engine.save(fresh,confirmed=True)
        messagebox.showinfo('Guardado solicitado','Revisa cualquier aviso de Innux. Después pulsa «Comprobar alta y vincular número». No se reintentará el guardado automáticamente.',parent=self.root)

    def verify(self):
        result=self.engine.verify()
        fresh=self.portal.request('contract_detail',id=self.engine.detail['id'])
        require(fresh['state']=='SIGNED' and fresh['center_accepted_at'],'El contrato requiere revisión del centro.')
        self.portal.request('mark_innux',member_id=fresh['member']['id'],innux_reference='INNUX:'+result['client_id'],innux_number=result['number'],confirmed_manual=True,evidence='Conector recepción: comprobación SELECT por documento, nacimiento y propietario único de número; ficha oficial revisada por trabajador.')
        messagebox.showinfo('Alta comprobada','La ficha existe en Innux y el número ha quedado vinculado al contrato. Las cuotas y domiciliaciones deben revisarse en Innux.',parent=self.root)
        self.close()

    def close(self):
        if self.photo_path:
            try:self.photo_path.unlink(missing_ok=True);self.photo_path.parent.rmdir();self.root.clipboard_clear()
            except OSError:pass
        try:self.portal.logout()
        except Exception:pass
        self.root.destroy()


def main():
    # A single connector per interactive Windows session.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,'Local\\TopFitnessEnrollmentConnector')
    already_running=ctypes.get_last_error()==183
    root=tk.Tk()
    if already_running:
        root.withdraw();messagebox.showwarning('Top Fitness','El conector de recepción ya está abierto.');root.destroy();return
    App(root);root.mainloop()
    kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle(mutex)


if __name__=='__main__':main()
