"""Abre el conector con la misma elevación que Innux, previa confirmación UAC."""
import ctypes
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
runtime=Path(sys.executable).with_name('pythonw.exe')
if not runtime.is_file():runtime=Path(sys.executable)
result=ctypes.windll.shell32.ShellExecuteW(None,'runas',str(runtime),subprocess.list2cmdline([str(root/'scripts/innux_reception.py')]),str(root),1)
if result<=32:
    ctypes.windll.user32.MessageBoxW(None,'No se abrió el conector. Innux está elevado y necesita aceptar el aviso de Windows.','Top Fitness',0x30)
