import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"tools"))
from tvdcore import digest
from tvdtests import apk_identity

class ApkTests(unittest.TestCase):
    def test_exact_installed_hash(self):
        with tempfile.TemporaryDirectory() as d:
            apk=pathlib.Path(d)/"a.apk"; apk.write_bytes(b"test APK fixture")
            runner=Mock()
            runner.execute.side_effect=[{"id":"path"},{"id":"hash","identity":{"firmware":"f","serial_sha256":"s"}}]
            runner.read_result.side_effect=[b"package:/data/app/com.example-a/base.apk\n",(digest(apk.read_bytes())+"  /data/app/com.example-a/base.apk\n").encode()]
            result=apk_identity(runner,apk,"com.example")
            self.assertEqual(result["sha256"],digest(apk.read_bytes()))
    def test_split_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            apk=pathlib.Path(d)/"a.apk"; apk.write_bytes(b"x")
            runner=Mock()
            runner.read_result.return_value=b"package:/data/app/com.example/base.apk\npackage:/data/app/com.example/split.apk\n"
            with self.assertRaises(ValueError): apk_identity(runner,apk,"com.example")
            self.assertEqual(runner.execute.call_count,1)
