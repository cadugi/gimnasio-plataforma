"""Acceso de escritorio: inicia solo este servidor y abre la aplicación, sin consola."""
import contextlib,ctypes,os,webbrowser,sys
import runtime

def main():
    runtime.PRIVATE.mkdir(exist_ok=True)
    with (runtime.PRIVATE/'launcher.log').open('a',encoding='utf-8') as log:
        try:
            with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):runtime.start()
            webbrowser.open('http://127.0.0.1:8095/'+('?view=registrations' if '--reception' in sys.argv else ''),new=2)
        except Exception as error:
            log.write(type(error).__name__+': '+str(error)+'\n');log.flush()
            if os.name=='nt':ctypes.windll.user32.MessageBoxW(0,'No se pudo abrir la aplicación. Revisa .private/launcher.log en la carpeta TopFitness_Altas_Contratos. No se ha detenido ningún otro servicio.','Top Fitness · Altas y contratos',0x10)
            else:raise

if __name__=='__main__':main()
