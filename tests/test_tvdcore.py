import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"tools"))
from tvdcore import Store, Runner, IdentityError, validate_shared, bounded, preview
from tvdprofiles import normalise
from tvdstate import record_capability, compare

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name)
    def test_paths(self):
        self.assertEqual(validate_shared("/sdcard/TVD-Engineering/staging/a.apk"),"/sdcard/TVD-Engineering/staging/a.apk")
        for bad in ("/data/local/tmp/a","/sdcard/TVD-Engineering/staging/../a","/sdcard/TVD-Engineering/staging/a/b","/sdcard/TVD-Engineering/staging/a;id"):
            with self.assertRaises(ValueError): validate_shared(bad)
    def test_bounded(self):
        r=bounded([sys.executable,"-c","print('a'*50000)"],5,1024)
        self.assertEqual(r["kind"],"output_limit")
        self.assertLessEqual(len(r["stdout"])+len(r["stderr"]),1024)
        r=bounded([sys.executable,"-c","import time; time.sleep(10)"],1,1024)
        self.assertEqual(r["kind"],"timeout")
    def test_preview(self):
        self.assertNotIn("supersecret",preview(b"token=supersecret\nfoo\nfoo"))
        self.assertIn("repeated",preview(b"foo\nfoo"))
    def test_identity_mismatch_never_fallback(self):
        runner=Runner("serial","a4-tv","real",store=self.store)
        with patch.object(runner,"_call",return_value={"kind":"exited","local_exit":0,"stdout":b"xiaoyushan\n28\nwrong\nfirmware\n2000\n"}):
            with self.assertRaises(IdentityError): runner.execute("id",read_only=True)
    def test_explicit_required_for_arbitrary(self):
        runner=Runner("serial","a4-tv","real",store=self.store)
        with self.assertRaises(ValueError): runner.execute("id")
    def test_normalise(self):
        self.assertEqual(normalise("packages",b"b\na\nb\n"),["a","b"])
    def test_evidence_required(self):
        with self.assertRaises(ValueError): record_capability(self.store,"foo","supported","x","note")
    def test_snapshot_comparison(self):
        a={"schema":1,"kind":"configuration","identity":{"serial_sha256":"a","firmware":"f"},"probes":{"packages":{"status":"ok","context":"adb-shell","values":["a"]}}}
        b={**a,"probes":{"packages":{"status":"unavailable"}}}
        self.store.json("snapshots","before.json",a); self.store.json("snapshots","after.json",b)
        self.assertEqual(compare(self.store,"before","after")["changes"]["packages"]["status"],"not_comparable")
