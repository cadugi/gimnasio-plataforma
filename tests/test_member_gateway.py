import json,pathlib,sys,time,unittest,hmac,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'centro-administracion'))
import socios
class MemberGateway(unittest.TestCase):
 def setUp(self):self.s={'h':'session-a','csrf':'secret-a','name':'test','role':'owner'}
 def test_refs_cannot_be_forged_reused_between_sessions_or_used_for_another_action(self):
  token=socios.pack(self.s,{'kind':'member','id':'test'})
  self.assertEqual(socios.unpack(self.s,token,'member')['id'],'test')
  for session,t,k in [(dict(self.s,h='other'),token,'member'),(self.s,token+'x','member'),(self.s,token,'quota')]:
   with self.assertRaises(socios.SearchError):socios.unpack(session,t,k)
  with self.assertRaises(socios.SearchError):socios.unpack(self.s,'not-json')
 def test_browser_csrf_token_cannot_sign_references(self):
  token=socios.pack(self.s,{'kind':'member','id':'test'});body=token.split('.')[0]
  forged=body+'.'+hmac.new(self.s['csrf'].encode(),(self.s['h']+body).encode(),hashlib.sha256).hexdigest()
  with self.assertRaises(socios.SearchError):socios.unpack(self.s,forged)
 def test_viewer_cannot_poll_quota_history_even_with_a_valid_reference(self):
  viewer=dict(self.s,role='viewer');ref=socios.pack(viewer,{'kind':'quota','id':'00000000-0000-0000-0000-000000000001','operation':'clients.history'})
  with self.assertRaises(socios.SearchError) as e:socios.Gateway(None,None).poll_quota(viewer,ref)
  self.assertEqual(e.exception.status,403)
 def test_expired_refs_rejected(self):
  original=socios.time.time
  try:
   socios.time.time=lambda:1;token=socios.pack(self.s,{'kind':'member'})
  finally:socios.time.time=original
  with self.assertRaises(socios.SearchError):socios.unpack(self.s,token)
 def test_only_explicit_reference_merges_people(self):
  portal=[dict(id='portal',name='Ana',phone='612345678',number='1',innux_reference='INNUX:10')]
  innux=[dict(id='10',name='Ana',phone='612345678',number='1',innux_reference='INNUX:10'),dict(id='20',name='Ana',phone='612345678',number='1',innux_reference='INNUX:20')]
  r=socios.merge(portal,innux,[dict(name='Ana',phone='612345678')]);self.assertEqual(len(r),3);self.assertTrue(r[0]['in_innux']);self.assertNotIn('in_innux',portal[0])
 def test_no_permission_upgrade_for_reservations(self):
  g=socios.Gateway(lambda *a,**k:self.fail('No debe llamar Reservas'),None)
  for role in ['viewer','manager']:
   with self.assertRaises(socios.SearchError) as e:g.reservas(dict(self.s,role=role),'cookie',query='Ana')
   self.assertEqual(e.exception.status,403)
 def test_validation_prevents_empty_and_oversize_queries(self):
  for q in ['',None,{},'a','x'*61,'Ana\nGarcía']:
   with self.assertRaises(socios.SearchError):socios.query(q)
  self.assertEqual(socios.query(' Ana '),'Ana')
 def test_partial_sources_are_explicit_and_innux_is_async(self):
  class Gateway(socios.Gateway):
   def altas(self,s,action,**data):
    if action=='member_search':return {'items':[dict(id='a',name='Ana',innux_reference=None)]}
    return {'id':'search-id'}
   def reservas(self,*a,**kw):raise ConnectionError('offline')
  r=Gateway(None,None).search(self.s,'cookie','Ana');self.assertEqual(len(r['items']),1);self.assertEqual(r['sources']['reservas']['state'],'unavailable');self.assertEqual(r['sources']['innux']['state'],'pending');self.assertEqual(socios.unpack(self.s,r['pending'],'search')['id'],'search-id')
 def test_reservation_selection_stays_separate(self):
  g=socios.Gateway(None,None);r=g.wrap(self.s,[dict(source='reservas',name='Ana',phone='612345678')]);p=socios.unpack(self.s,r[0]['ref'],'member');self.assertEqual(p['source'],'reservas');self.assertEqual(p['phone'],'612345678')
if __name__=='__main__':unittest.main()
