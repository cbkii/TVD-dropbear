import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"tools"))
from tvdcore import Store, Runner, IdentityError, evidence_page, digest

class SafetyTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.store=Store(d.name)
    def test_guard_and_exit(self):
        r=Runner("serial",None,"real",store=self.store)
        def call(context,command,cap=0):
            if "TVD_EXIT_" not in command:
                return {"kind":"exited","local_exit":0,"stdout":b"xiaoyushan\n28\nreal\nf\n2000\n","stderr":b"","duration_ms":1}
            import re
            self.assertIn('test "$(getprop ro.serialno)" = real',command)
            marker=re.search(r"TVD_EXIT_[0-9a-f]{32}",command).group()
            return {"kind":"exited","local_exit":0,"stdout":("ok\n"+marker+":7\n").encode(),"stderr":b"","duration_ms":2}
        with patch.object(r,"_call",side_effect=call):
            result=r.execute("id",read_only=True,sensitive=False)
        self.assertEqual(result["remote_exit"],7)
        self.assertEqual(result["status"],"remote_error")
        self.assertEqual(evidence_page(self.store,result["id"])["text"],"ok")
    def test_changed_identity_guard(self):
        r=Runner("serial",None,"real",store=self.store)
        def call(context,command,cap=0):
            if "TVD_EXIT_" not in command:
                return {"kind":"exited","local_exit":0,"stdout":b"xiaoyushan\n28\nreal\nf\n2000\n","stderr":b"","duration_ms":1}
            import re
            marker=re.search(r"TVD_EXIT_[0-9a-f]{32}",command).group()
            return {"kind":"exited","local_exit":93,"stdout":("\n"+marker+":GUARD\n").encode(),"stderr":b"","duration_ms":2}
        with patch.object(r,"_call",side_effect=call):
            with self.assertRaises(IdentityError): r.execute("id",read_only=True)
    def test_evidence_privacy(self):
        ident="a"*32
        raw=b"password=private\nother\n"
        self.store.write("evidence",ident+".stdout",raw)
        self.store.json("evidence",ident+".json",{"id":ident,"sensitive":True,"stdout_sha256":digest(raw),"complete":True})
        with self.assertRaises(ValueError): evidence_page(self.store,ident)
        self.assertNotIn("private",evidence_page(self.store,ident,share_sensitive=True)["text"])
        with self.assertRaises(ValueError): evidence_page(self.store,"../foo")
    def test_ssh_trust_failure(self):
        r=Runner("serial","a4-tv","real",store=self.store,context="ssh-root")
        with patch.object(r,"_call",return_value={"kind":"exited","local_exit":255,"stderr":b"Host key verification failed.","stdout":b""}):
            with self.assertRaises(IdentityError): r.verify("ssh-root")
