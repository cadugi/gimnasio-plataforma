"""Integración del endpoint PHP con tablas MySQL TEMPORARY; no escribe datos reales.
Uso en el VPS: sudo env TF_RUN_MYSQL_INTEGRATION=1 python3 tests/test_waitlist_endpoint.py
"""
import datetime,json,os,pathlib,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('TF_RUN_MYSQL_INTEGRATION')=='1','Integración MySQL solo bajo petición explícita')
class WaitlistEndpoint(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='tf-waitlist-');p=pathlib.Path(cls.tmp.name);(p/'sso').mkdir();(p/'public').mkdir();(p/'fixture-only').touch()
  for f in ['admin_legacy_inscribir_cliente.php','public_phone.php','public_booking_rules.php','booking_identity.php']:shutil.copyfile(ROOT/'web/sso'/f,p/'sso'/f)
  (p/'public/conexion.php').write_text("<?php $conn=new mysqli('localhost','root','','topfitness_reservas');$conn->set_charset('utf8mb4');")
  shutil.copyfile(ROOT/'web/public/admin_inscribir_multiple.php',p/'public/admin_inscribir_multiple.php')
  cls.env=dict(os.environ,TF_WAITLIST_FIXTURE_ROOT=str(p))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def request(self,**data):
  p=subprocess.run(['php',str(ROOT/'tests/fixtures/waitlist_endpoint.php')],input=json.dumps(data),capture_output=True,text=True,env=self.env)
  self.assertEqual(p.returncode,0,p.stderr);self.assertIn('__FIXTURE__',p.stdout,p.stdout+' '+p.stderr)
  body,stats=p.stdout.split('\n__FIXTURE__');return json.loads(body),json.loads(stats)
 def full(self):return [dict(name='Plaza A',phone='641827395'),dict(name='Plaza B',phone='652918374')]
 def test_admin_full_class_enters_waitlist(self):
  r,s=self.request(occupied=self.full());self.assertTrue(r['success']);self.assertEqual(r['status'],'WAITLIST');self.assertEqual(r['posicion'],1);self.assertEqual((s['occupied'],s['waiting']),(2,1));self.assertEqual(s['actors'],['qa_total'])
 def test_old_force_flag_cannot_exceed_capacity(self):
  r,s=self.request(occupied=self.full(),force=True);self.assertEqual(r['status'],'WAITLIST');self.assertEqual((s['occupied'],s['waiting']),(2,1));self.assertNotIn('requires_confirmation',r)
 def test_free_spot_is_reserved(self):
  r,s=self.request(occupied=self.full()[:1]);self.assertEqual(r['status'],'INSCRIBED');self.assertEqual((s['occupied'],s['waiting']),(2,0))
 def test_unlimited_class_keeps_unlimited_behavior(self):
  r,s=self.request(limit=0,occupied=self.full());self.assertEqual(r['status'],'INSCRIBED');self.assertEqual((s['occupied'],s['waiting']),(3,0))
 def test_repeated_waiting_person_keeps_turn(self):
  r,s=self.request(occupied=self.full(),waiting=[dict(name='Persona nueva',phone='674192835')]);self.assertEqual(r['status'],'WAITLIST');self.assertTrue(r['already']);self.assertEqual(r['posicion'],1);self.assertEqual(s['waiting'],1)
 def test_normalized_name_and_phone_keep_existing_wait(self):
  r,s=self.request(occupied=self.full(),name='  ÁNA   pérez ',phone='+34 674 192 835',waiting=[dict(name='ana perez',phone='674192835')]);self.assertTrue(r['already']);self.assertEqual(s['waiting'],1)
 def test_two_people_sharing_phone_stay_separate(self):
  r,s=self.request(occupied=self.full(),name='Luis Pérez',waiting=[dict(name='Ana Pérez',phone='674192835')]);self.assertFalse(r['success']);self.assertEqual(r['code'],'WAITLIST_IDENTITY_CONFLICT');self.assertEqual(s['http'],409);self.assertEqual(s['waiting'],1)
 def test_waiting_other_date_does_not_change_that_queue(self):
  r,s=self.request(occupied=self.full(),waiting=[dict(name='Persona nueva',phone='674192835',date='2030-01-08')]);self.assertEqual(r['posicion'],1);self.assertEqual(s['waiting'],2)
 def test_existing_reservation_does_not_get_queued(self):
  r,s=self.request(occupied=self.full(),name='Plaza A',phone='641827395');self.assertFalse(r['success']);self.assertEqual(s['http'],409);self.assertEqual(s['waiting'],0)
 def test_already_overfull_class_never_adds_another_reservation(self):
  r,s=self.request(occupied=self.full()+[dict(name='Exceso antiguo',phone='695182734')],force=True);self.assertEqual(r['status'],'WAITLIST');self.assertEqual((s['occupied'],s['waiting']),(3,1))
 def test_bulk_full_class_goes_to_waitlist(self):
  r,s=self.request(bulk=True,occupied=self.full());self.assertEqual(r['resultados'][0]['estado'],'EN_ESPERA');self.assertEqual((s['occupied'],s['waiting']),(2,1));self.assertEqual(s['actors'],['qa_total'])
 def test_bulk_repeated_wait_keeps_turn(self):
  r,s=self.request(bulk=True,occupied=self.full(),waiting=[dict(name='Persona nueva',phone='674192835')]);self.assertEqual(r['resultados'][0]['estado'],'YA_EN_ESPERA');self.assertEqual(s['waiting'],1)
 def test_bulk_free_spot_is_reserved(self):
  r,s=self.request(bulk=True,occupied=self.full()[:1]);self.assertEqual(r['resultados'][0]['estado'],'APUNTADO');self.assertEqual((s['occupied'],s['waiting']),(2,0))
 def test_public_full_class_still_goes_to_waitlist(self):
  from zoneinfo import ZoneInfo
  tomorrow=(datetime.datetime.now(ZoneInfo('Europe/Madrid'))+datetime.timedelta(days=1)).date().isoformat()
  r,s=self.request(admin=False,date=tomorrow,occupied=self.full());self.assertEqual(r['status'],'WAITLIST');self.assertEqual((s['occupied'],s['waiting']),(2,1))
if __name__=='__main__':unittest.main()
