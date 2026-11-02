"""Prueba los rechazos del controlador antes de conectar con la base de datos."""
import json,pathlib,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class WaitlistRemoveAuth(unittest.TestCase):
 def call(self,server,post):
  script="putenv('TF_PUBLIC_ORIGIN=https://fixture.invalid');$r=json_decode(stream_get_contents(STDIN),true);$_SERVER=$r['server'];$_POST=$r['post'];register_shutdown_function(function(){echo '\\nHTTP:'.http_response_code();});require "+json.dumps(str(ROOT/'web/public/eliminar_cola.php'))+";"
  p=subprocess.run(['php','-r',script],input=json.dumps(dict(server=server,post=post)),text=True,capture_output=True);self.assertEqual(p.returncode,0,p.stderr);return int(p.stdout.rsplit('HTTP:',1)[1])
 def server(self):return dict(REMOTE_USER='qa_total',REQUEST_METHOD='POST',HTTP_ORIGIN='https://fixture.invalid',HTTP_X_TOPFITNESS_REQUEST='1')
 def test_anonymous_rejected(self):
  s=self.server();s.pop('REMOTE_USER');self.assertEqual(self.call(s,{}),401)
 def test_get_rejected(self):
  s=self.server();s['REQUEST_METHOD']='GET';self.assertEqual(self.call(s,{}),405)
 def test_origin_and_request_header_required(self):
  for key in ['HTTP_ORIGIN','HTTP_X_TOPFITNESS_REQUEST']:
   s=self.server();s.pop(key);self.assertEqual(self.call(s,{}),403)
 def test_invalid_id_rejected_before_database_access(self):
  for ident in ['0','1abc',[],None]:self.assertEqual(self.call(self.server(),dict(id=ident,horario_id='1',fecha='2026-10-26')),400)
 def test_array_date_rejected(self):self.assertEqual(self.call(self.server(),dict(id='1',horario_id='1',fecha=[])),400)
if __name__=='__main__':unittest.main()
