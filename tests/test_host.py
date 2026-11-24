import importlib.util, pathlib, unittest
spec=importlib.util.spec_from_file_location("a4ctl",pathlib.Path(__file__).resolve().parents[1]/"tools/a4ctl.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class HostTest(unittest.TestCase):
    def test_explicit(self):
        self.assertEqual(m.argv_for("adb-shell","serial",None,"id"),["adb","-s","serial","shell","id"])
        self.assertEqual(m.argv_for("adb-root","serial",None,"id; uptime")[-1],"su -c 'id; uptime'")
        self.assertIn("StrictHostKeyChecking=yes",m.argv_for("ssh-root",None,"a4-tv","id"))
    def test_no_target_or_option(self):
        for context,serial,host in [("adb-shell",None,None),("adb-root","-bad",None),("ssh-root",None,"-bad")]:
            with self.assertRaises(ValueError): m.argv_for(context,serial,host,"id")
