#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble an allowlisted Magisk ZIP from newly built ARM binaries."""
import argparse, hashlib, json, pathlib, subprocess, zipfile, re
ROOT = pathlib.Path(__file__).resolve().parents[1]
MOD = ROOT / "module"
STATIC = ("module.prop", "customize.sh", "service.sh", "action.sh", "uninstall.sh",
          "tvddctl", "common/config.default", "common/vddropbear.sh",
          ".vd/sha256-gate.sh", "META-INF/com/google/android/update-binary",
          "META-INF/com/google/android/updater-script",
          "licenses/dropbear-LICENSE", "licenses/libtomcrypt-LICENSE",
          "licenses/openssh-LICENSE", "licenses/rsync-COPYING", "licenses/zlib-LICENSE")
TOOLS = ("tvddropbear", "dropbearkey", "sftp-server", "rsync")
ABIS = {"armeabi-v7a": (1, 40), "arm64-v8a": (2, 183)}
def digest(data): return hashlib.sha256(data).hexdigest()
def check_elf(data, abi):
    elfclass, machine = ABIS[abi]
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != elfclass or data[5] != 1 or int.from_bytes(data[18:20], "little") != machine:
        raise ValueError("wrong ELF ABI: " + abi)
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--abi", choices=ABIS, required=True)
    p.add_argument("--out", type=pathlib.Path, default=ROOT/"dist")
    a = p.parse_args()
    items = {n:(MOD/n).read_bytes() for n in STATIC}
    for n in ("LICENSE","NOTICE","THIRD-PARTY-NOTICES.md"):
        items[n] = (ROOT/n).read_bytes()
    binaries = {}
    for n in TOOLS:
        path = f"bin/{a.abi}/{n}"
        data = (MOD/path).read_bytes()
        check_elf(data,a.abi)
        items[path] = data
        binaries[n] = {"sha256":digest(data),"size":len(data),"target_api":24 if n in ("tvddropbear","dropbearkey") else 28}
    # Single ABI in each ZIP. Explicit build provenance, not a claim of bitwise reproducibility.
    sha = subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT,text=True).strip()
    source_hashes = (ROOT/"build/bundles/source-sha256.txt").read_text()
    source_revision = (ROOT/"build/dropbear.commit").read_text().strip()
    info = {"components":{"dropbear":"2026.94","rsync":"3.5.2","openssh":"10.4p1","zlib":"1.4"},"source_sha":sha,"abi":a.abi,"dropbear_commit":source_revision,"bundle_source_hashes":source_hashes,
            "ndk":"27.0.12077973","binaries":binaries}
    items["bin/PROVENANCE.json"] = (json.dumps(info,indent=2)+"\n").encode()
    items["manifest.sha256"] = "".join(digest(data)+"  "+n+"\n" for n,data in sorted(items.items()) if not n.startswith("META-INF/")).encode()
    version = re.search(r"^version=(.+)$",items["module.prop"].decode(),re.M).group(1)
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-testing)?",version): raise ValueError("invalid version")
    a.out.mkdir(parents=True,exist_ok=True)
    out = a.out/f"TVD-dropbear-{version}-{a.abi}.zip"
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(items.items()):
            meta=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0))
            meta.create_system=3; meta.compress_type=zipfile.ZIP_DEFLATED
            executable = not name.endswith(".sha256") and (name.endswith(".sh") or name in ("tvddctl","META-INF/com/google/android/update-binary") or name.startswith("bin/"+a.abi+"/"))
            meta.external_attr=(0o100755 if executable else 0o100644)<<16
            z.writestr(meta,data)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None and set(z.namelist()) == set(items)
        for name,data in items.items(): assert z.read(name)==data
    out.with_suffix(".zip.sha256").write_text(digest(out.read_bytes())+"  "+out.name+"\n")
    # Corresponding GPL rsync source and the exact build recipe are release assets.
    import tarfile
    src=a.out/f"TVD-dropbear-rsync-source-{a.abi}.tar.gz"
    with tarfile.open(src,"w:gz") as t:
        t.add(ROOT/"build/bundles/rsync.tar.gz",arcname="rsync.tar.gz")
        t.add(ROOT/"scripts/build-bundles.sh",arcname="build-bundles.sh")
        t.add(ROOT/"build/bundles/source-sha256.txt",arcname="source-sha256.txt")
        t.add(ROOT/"module/licenses/rsync-COPYING",arcname="COPYING")
    src.with_suffix(".gz.sha256").write_text(digest(src.read_bytes())+"  "+src.name+"\n")
    print(out)
if __name__=="__main__": main()
