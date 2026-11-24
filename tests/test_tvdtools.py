import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"tools"))
from tvdcore import Store
from tvdui import hierarchy, keypress, safe_workspace
from tvdmirror import reference_path, mirror
from tvdtests import validate_steps, run_test

class ToolTests(unittest.TestCase):
    def test_reference_paths(self):
        self.assertEqual(reference_path("/vendor/lib/test.so"),"/vendor/lib/test.so")
        for p in ("/data/system/a.xml","/vendor/lib/../../data/a.xml","/vendor/etc/wifi.conf","/vendor/lib/foo.so;id","/system/priv-app/"):
            with self.assertRaises(ValueError): reference_path(p)
    def test_mirror_budget(self):
        r=Mock()
        with self.assertRaises(ValueError): mirror(r,["/vendor/lib/a.so"]*33)
        r.execute.assert_not_called()
    def test_ui_opt_in(self):
        r=Mock()
        with self.assertRaises(ValueError): hierarchy(r)
        with self.assertRaises(ValueError): keypress(r,"DOWN")
        with self.assertRaises(ValueError): keypress(r,"POWER",allow_ui=True)
        r.execute.assert_not_called()
        self.assertIn("/sdcard/TVD-Engineering/captures",safe_workspace("captures"))
    def test_test_schema(self):
        self.assertEqual(validate_steps([{"probe":"memory","contains":"MemTotal:"}])[0]["probe"],"memory")
        for plan in ([{"command":"reboot"}],[{"probe":"memory","status":"remote_error"}],[{"probe":"unknown","status":"ok"}]):
            with self.assertRaises(ValueError): validate_steps(plan)
    def test_failed_probe_not_pass(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            r=Mock(store=Store(d))
            with patch("tvdtests.inspect",return_value={"status":"remote_error","id":"a","identity":{},"context":"adb-shell"}):
                result=run_test(r,"case",[{"probe":"memory","status":"ok"}])
            self.assertFalse(result["passed"])
            self.assertFalse(result["artifact_identity_verified"])
