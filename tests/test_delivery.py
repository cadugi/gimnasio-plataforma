"""Regresiones de permisos, revocación y fechas: datos ficticios, sin producción."""
import importlib.util,pathlib,sys,sqlite3,json,unittest,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'centro-administracion'));sys.path.insert(0,str(ROOT/'caja'))
spec=importlib.util.spec_from_file_location('cc_delivery',ROOT/'centro-administracion/app.py');cc=importlib.util.module_from_spec(spec);spec.loader.exec_module(cc)
from caja import sso,ledger
class Delivery(unittest.TestCase):
 def test_reservas_owner_only(self):
  class Request:
   path='/administracion/_auth'
   def session(self):return self.user
   def send(self,status,*args):self.status=status
  for role,expected in [('owner',200),('manager',403),('viewer',403)]:
   q=Request();q.user={'name':'test','role':role};cc.H.do_GET(q);self.assertEqual(q.status,expected)
  q=Request();q.user=None;cc.H.do_GET(q);self.assertEqual(q.status,401)
 def test_last_closure_ignores_future_and_orders_calendar(self):
  c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;c.execute('CREATE TABLE closures(id INTEGER PRIMARY KEY,day TEXT,snapshot TEXT)')
  for i,day in [(1,'2026-10-21'),(2,'2027-06-01'),(3,'2026-10-19')]:c.execute('INSERT INTO closures VALUES(?,?,?)',(i,day,json.dumps({'totals':{'counted':i*100}})))
  self.assertEqual(ledger.last_closure_cash(c,'2026-10-22'),{'day':'2026-10-21','counted':100})
  self.assertIsNone(ledger.last_closure_cash(c,'2026-10-18'))
 def test_sso_logout_revokes_only_subject_and_is_not_login(self):
  c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;c.executescript('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT);CREATE TABLE sessions(user_id INTEGER);CREATE TABLE sso_tickets(jti TEXT PRIMARY KEY,expires TEXT);CREATE TABLE audit(id INTEGER PRIMARY KEY,created TEXT,action TEXT,actor TEXT,detail TEXT);')
  c.execute("INSERT INTO users VALUES(1,'cc.alicia'),(2,'cc.bea')");c.execute('INSERT INTO sessions VALUES(1),(1),(2)')
  now=int(time.time());p=dict(mod='caja',sub='alicia',role='admin',iat=now,exp=now+60,jti='logout-1',op='logout');key=b'x'*40;ticket=sso.sign(key,p)
  with self.assertRaises(sso.SsoError):sso.verify(key,ticket)
  verified=sso.verify(key,ticket,operation='logout');sso.logout(c,verified)
  self.assertEqual([r[0] for r in c.execute('SELECT user_id FROM sessions')],[2])
  with self.assertRaises(sso.SsoError):sso.logout(c,verified)
  p.update(op='login',jti='login-1')
  with self.assertRaises(sso.SsoError):sso.verify(key,sso.sign(key,p),operation='logout')
 def test_cc_logout_payload_has_separate_operation(self):
  original=cc.sso_key;cc.sso_key=lambda module:b'x'*40
  try:
   payload=sso.verify(b'x'*40,cc.sso_ticket('caja','alicia','owner','logout'),operation='logout');self.assertEqual(payload['sub'],'alicia')
  finally:cc.sso_key=original
if __name__=='__main__':unittest.main()
