"""Abre el módulo de altas únicamente al pulsar el menú. No accede a Caja/Innux."""
from pathlib import Path
import os
import subprocess
from tkinter import messagebox

def open_enrollments(parent):
    base=Path(__file__).resolve().parent.parent
    launcher=base/'TopFitness_Altas_Contratos'/'scripts'/'open_demo.py'
    candidates=[Path(os.environ.get('LOCALAPPDATA',''))/'Programs'/'CajaPython'/'pythonw.exe',
                base/'CajaGimnasio-Pruebas'/'Runtime'/'pythonw.exe']
    python=next((p for p in candidates if p.is_file()),None)
    if not launcher.is_file() or python is None:
        messagebox.showerror('Altas digitales','No se encuentra el módulo de altas o su entorno local.',parent=parent)
        return
    try:
        subprocess.Popen([str(python),str(launcher),'--reception'],cwd=str(launcher.parent),
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
    except OSError:
        messagebox.showerror('Altas digitales','No se pudo abrir el módulo de altas. Revisa su configuración local.',parent=parent)
