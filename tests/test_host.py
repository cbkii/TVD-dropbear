import importlib.util, pathlib, unittest, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location("a4ctl",pathlib.Path(__file__).resolve().parents[1]/"tools/a4ctl.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class HostTest(unittest.TestCase):
    def test_explicit(self):
        self.assertEqual(m.argv_for("adb-shell","serial",None,"id"),["adb","-s","serial","shell","id"])
        self.assertEqual(m.argv_for("adb-root","serial",None,"id; uptime")[-1],"su -c 'id; uptime'")
        self.assertIn("StrictHostKeyChecking=yes",m.argv_for("ssh-root",None,"a4-tv","id"))
    def test_no_target_or_option(self):
        for context,serial,host in [("adb-shell",None,None),("adb-root","-bad",None),("ssh-root",None,"-bad"),("ssh-root",None,"a:b")]:
            with self.assertRaises(ValueError): m.argv_for(context,serial,host,"id")
    def test_file_transfers(self):
        a=SimpleNamespace(context="ssh-root",host="a4-tv",serial=None)
        args=m.transfer_argv(a,"sync","/vendor/etc/","./copy")
        self.assertIn("--protect-args",args)
        self.assertNotIn("--delete",args)
        self.assertIn("a4-tv:/vendor/etc/",args)
        self.assertIn("-s",m.transfer_argv(a,"pull","/vendor/file","copy"))
        with self.assertRaises(ValueError): m.transfer_argv(a,"pull","/foo/*","copy")
        a.context="adb-root"
        with self.assertRaises(ValueError): m.transfer_argv(a,"push","copy","/data/file")
