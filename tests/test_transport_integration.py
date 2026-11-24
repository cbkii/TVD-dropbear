# SPDX-License-Identifier: Apache-2.0
"""Exercise actual shell quoting, markers and transport selection via a local fake ADB."""
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"tools"))
from tvdcore import Store, Runner, IdentityError
from tvdprofiles import inspect

@unittest.skipUnless(os.name=="posix" and shutil.which("sh"),"POSIX shell integration fixture")
class TransportIntegration(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=pathlib.Path(tmp.name)
        self.store=Store(self.root/"workspace")
        adb=self.root/"adb"
        adb.write_text("""#!/bin/sh
test "$1" = -s && test "$2" = fixture && test "$3" = shell || exit 99
shift 3
getprop() {
    case "$1" in
        ro.product.device) echo xiaoyushan;;
        ro.build.version.sdk) echo 28;;
        ro.serialno) printf '%s\\n' "$TVD_FIXTURE_SERIAL";;
        ro.build.fingerprint) echo 'vendor/device/build:9/test:user/release-keys';;
        ro.product.cpu.abi) echo armeabi-v7a;;
    esac
}
id() { test "$1" = -u && echo 2000; }
eval "$1"
""",encoding="utf-8")
        adb.chmod(0o700)
        env=patch.dict(os.environ,{"PATH":str(self.root)+os.pathsep+os.environ["PATH"],"TVD_FIXTURE_SERIAL":"fixture-device"})
        env.start(); self.addCleanup(env.stop)
    def test_actual_shell_markers_and_multiline(self):
        runner=Runner("fixture",None,"fixture-device",store=self.store,context="adb-shell")
        result=inspect(runner,"identity")
        self.assertEqual(result["status"],"ok")
        self.assertIn(b"armeabi-v7a",runner.read_result(result))
        result=runner.execute("printf '%s\\n' \"a b ' c\"\nexit 7",read_only=False,sensitive=False)
        self.assertEqual(result["remote_exit"],7)
        self.assertIn("a b ' c",result["stdout_preview"])
    def test_cached_identity_cannot_execute_on_replacement(self):
        runner=Runner("fixture",None,"fixture-device",store=self.store,context="adb-shell")
        runner.verify("adb-shell")
        with patch.dict(os.environ,{"TVD_FIXTURE_SERIAL":"replacement"}):
            with self.assertRaises(IdentityError):
                runner.execute("printf unsafe",read_only=True)
