"""Configura un administrador mediante entrada oculta; no guarda contraseñas en archivos."""
import getpass,json,os,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
php=os.environ.get('TF_PHP_BINARY') or shutil.which('php') or 'C:/Users/User/Documents/xampp/php/php.exe'
name=input('Usuario administrador: ').strip()
password=getpass.getpass('Contraseña (mínimo 12 caracteres, letras y cifras): ')
repeat=getpass.getpass('Repite la contraseña: ')
if password!=repeat:raise SystemExit('Las contraseñas no coinciden.')
result=subprocess.run([php,str(root/'scripts/reset_admin.php')],input=json.dumps({'username':name,'password':password}),text=True,encoding='utf-8',cwd=root)
password=repeat=''
sys.exit(result.returncode)
