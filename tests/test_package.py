import importlib.util,pathlib,unittest
spec=importlib.util.spec_from_file_location("package",pathlib.Path(__file__).resolve().parents[1]/"scripts/package.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PackageTest(unittest.TestCase):
    def test_abi(self):
        for abi,(c,machine) in m.ABIS.items():
            data=bytearray(64); data[:4]=b"\x7fELF"; data[4]=c; data[5]=1; data[18:20]=machine.to_bytes(2,"little")
            m.check_elf(data,abi)
            with self.assertRaises(ValueError): m.check_elf(data,"arm64-v8a" if c==1 else "armeabi-v7a")
    def test_no_updater(self):
        self.assertFalse(any("vdlu" in n or "webroot" in n for n in m.STATIC))
        self.assertEqual(set(m.TOOLS),{"tvddropbear","dropbearkey","sftp-server","rsync"})
