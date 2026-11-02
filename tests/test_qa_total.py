"""Límites de la excepción QA: identidad, rol, revocación y SSO sin resurrección."""
import importlib.util
import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'centro-administracion'))
sys.path.insert(0, str(ROOT/'caja'))
spec=importlib.util.spec_from_file_location('cc',ROOT/'centro-administracion/app.py')
cc=importlib.util.module_from_spec(spec);spec.loader.exec_module(cc)
from caja import sso

class QaBoundary(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.before=cc.DB;cc.DB=str(pathlib.Path(self.temp.name)/'cc.sqlite')
        with sqlite3.connect(cc.DB) as c:c.execute('CREATE TABLE qa_total_access(uid INTEGER PRIMARY KEY)');c.execute('INSERT INTO qa_total_access VALUES(42)');c.execute('CREATE TABLE diario_access(h TEXT,expires REAL)')
    def tearDown(self):
        cc.DB=self.before;self.temp.cleanup()
    def test_requires_exact_identity_owner_and_registered_id(self):
        self.assertTrue(cc.qa_total_enabled(dict(name='qa_total',role='owner',uid=42)))
        for values in [dict(name='other',role='owner',uid=42),dict(name='QA_TOTAL',role='owner',uid=42),dict(name='qa_total',role='manager',uid=42),dict(name='qa_total',role='owner',uid=43),None]:
            self.assertFalse(cc.qa_total_enabled(values))
    def test_revocation_removes_bypass_without_restart(self):
        with sqlite3.connect(cc.DB) as c:c.execute('DROP TABLE qa_total_access')
        self.assertFalse(cc.qa_total_enabled(dict(name='qa_total',role='owner',uid=42)))
    def test_journal_unlocked_only_for_registered_qa(self):
        self.assertTrue(cc.H.diario_allowed(None,dict(name='qa_total',role='owner',uid=42)))
        self.assertFalse(cc.H.diario_allowed(None,dict(name='other',role='viewer',uid=42)))
        self.assertFalse(cc.H.diario_allowed(None,dict(name='other',role='owner',uid=42,h='ordinary-session')))
        self.assertFalse(cc.H.diario_allowed(None,dict(name='qa_total',role='owner',uid=43,h='different-id')))
    def test_sso_never_creates_or_reactivates_qa(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.executescript('CREATE TABLE sso_tickets(jti TEXT PRIMARY KEY,expires TEXT);CREATE TABLE users(id INTEGER,username TEXT,role TEXT,active INTEGER,sso INTEGER);')
        for active in [None,0]:
            if active is not None:c.execute("INSERT INTO users VALUES(1,'qa_total','admin',0,0)")
            with self.assertRaises(sso.SsoError):sso.login(c,dict(jti=str(active),sub='qa_total',role='admin'))
        self.assertEqual(c.execute('SELECT active FROM users').fetchone()[0],0)

if __name__=='__main__':unittest.main()
