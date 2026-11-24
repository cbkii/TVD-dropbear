# SPDX-License-Identifier: Apache-2.0
"""Explicit, bounded, read-only firmware reference mirror; no broad /data access."""
import json
from pathlib import PurePosixPath
import re
import shlex
import uuid
import a4ctl
from tvdcore import bounded, digest, utc, safe_name

ROOTS=("vendor/etc","vendor/lib","vendor/lib64","system/framework","system/etc","system/priv-app","odm/etc","odm/lib","odm/lib64")
MAX_FILE=32*1024*1024
MAX_TOTAL=128*1024*1024
MAX_FILES=32

def reference_path(path):
    if not isinstance(path,str) or not re.fullmatch(r"/[A-Za-z0-9_./+-]{1,400}",path):
        raise ValueError("invalid reference path")
    if str(PurePosixPath(path))!=path or ".." in path.split("/") or "." in path.split("/"):
        raise ValueError("noncanonical reference path")
    if not any(path.startswith("/"+root+"/") for root in ROOTS):
        raise ValueError("path outside reference roots")
    # Exclude obvious keys, credentials and non-engineering data. No guarantee that all vendor
    # files are nonsensitive: archives remain private on the host.
    if re.search(r"(?i)(?:key|keystore|passwd|shadow|secret|credential|token|drm|wifi|wpa|\.pem|\.crt|\.p12)",path):
        raise ValueError("potential credential material excluded")
    if PurePosixPath(path).suffix.lower() not in (".so",".jar",".apk",".xml",".conf",".cfg",".ini",".rc",".prop",".json",".txt"):
        raise ValueError("unsupported reference file type")
    return path

def list_references(runner,root):
    if root not in ROOTS:
        raise ValueError("unknown reference root")
    path="/"+root
    # Read-only listing; -maxdepth and a bounded result prevent broad traversal.
    result=runner.execute("test -d "+shlex.quote(path)+" && find "+shlex.quote(path)+" -maxdepth 3 -type f | head -n 1001",
                          read_only=True,sensitive=True,label="reference-list",cap=256*1024)
    lines=runner.read_result(result).decode("utf-8","replace").splitlines()
    paths=[]
    for line in lines[:1000]:
        try: paths.append(reference_path(line))
        except ValueError: continue
    return {"paths":sorted(set(paths)),"truncated":len(lines)>1000,"evidence":result["id"]}

def metadata(runner,path):
    q=shlex.quote(path)
    # Refuse symlinks escaping the selected path; do not follow even platform aliases by guessing.
    command=("test -f "+q+" && test ! -L "+q+" && test \"$(readlink -f "+q+")\" = "+q+
             " && stat -c '%s %Y %a %u %g' "+q)
    result=runner.execute(command,read_only=True,sensitive=True,label="reference-metadata",cap=16384)
    lines=runner.read_result(result).decode().strip().split()
    if len(lines)!=5 or not all(x.isdigit() for x in lines):
        raise ValueError("invalid reference metadata")
    return result,tuple(map(int,lines))

def remote_hash(runner,context,path):
    q=shlex.quote(path)
    r=runner._call(context,runner.guard(context)+" && test -f "+q+" && test ! -L "+q+
                   " && test \"$(readlink -f "+q+")\" = "+q+" && sha256sum "+q,16384)
    m=re.match(rb"([0-9a-f]{64})\s",r["stdout"])
    if r["kind"]!="exited" or r["local_exit"]!=0 or not m:
        raise ValueError("reference digest unavailable")
    return m[1].decode()

def mirror(runner,paths,verify=False):
    if not paths or len(paths)>MAX_FILES:
        raise ValueError("select 1..32 explicit reference paths")
    paths=list(dict.fromkeys(reference_path(p) for p in paths))
    records=[]; total=0
    for path in paths:
        r,attrs=metadata(runner,path)
        size,mtime,mode,uid,gid=attrs
        if size>MAX_FILE or total+size>MAX_TOTAL:
            raise ValueError("reference transfer budget exceeded")
        total+=size
        context=r["context"]
        identity=runner.verify(context,fresh=True)
        key=digest(json.dumps([identity["serial_sha256"],identity["firmware"],path],sort_keys=True).encode())
        index=runner.store.folder("mirror-index")
        matches=sorted(index.glob(key+"-*.json"),key=lambda p:p.stat().st_mtime,reverse=True)
        prior=runner.store.load("mirror-index",matches[0].name) if matches else None
        if prior and prior["attributes"]==list(attrs) and not verify:
            try:
                existing=runner.store.read("mirror-objects",prior["sha256"],MAX_FILE)
                if digest(existing)==prior["sha256"]:
                    records.append(dict(prior,reused=True,remote_hash_rechecked=False))
                    continue
            except (OSError,ValueError):
                pass
        expected=remote_hash(runner,context,path)
        try:
            existing=runner.store.read("mirror-objects",expected,MAX_FILE)
            if digest(existing)!=expected:
                raise ValueError("existing host object has invalid hash")
            reused=True
        except FileNotFoundError:
            # Store.read raises ValueError for missing objects; handled below by existence test.
            reused=False
        except ValueError:
            if (runner.store.folder("mirror-objects")/expected).exists():
                raise
            reused=False
        if not reused:
            q=shlex.quote(path)
            command=runner.guard(context)+" && test -f "+q+" && test ! -L "+q+" && test \"$(readlink -f "+q+")\" = "+q+" && cat "+q
            if context=="ssh-root":
                argv=a4ctl.argv_for(context,runner.serial,runner.host,command)
            else:
                argv=[*a4ctl.adb_prefix(runner.serial),"exec-out",command if context=="adb-shell" else "su -c "+shlex.quote(command)]
            raw=bounded(argv,runner.timeout,max(1024,size+1024))
            data=raw["stdout"]
            if raw["kind"]!="exited" or raw["local_exit"]!=0 or len(data)!=size or digest(data)!=expected:
                raise ValueError("reference transfer incomplete or changed")
            try: runner.store.write("mirror-objects",expected,data)
            except FileExistsError:
                if digest(runner.store.read("mirror-objects",expected,MAX_FILE))!=expected: raise
        if remote_hash(runner,context,path)!=expected:
            raise ValueError("remote reference changed during collection")
        record={"path":path,"sha256":expected,"file":"mirror-objects/"+expected,"attributes":list(attrs),
                "identity":identity,"context":context,"evidence":r["id"],"utc":utc(),"reused":reused,
                "remote_hash_rechecked":True}
        runner.store.json("mirror-index",key[:64]+"-"+uuid.uuid4().hex[:8]+".json",record)
        records.append(record)
    return {"records":records,"selected_bytes":total,"file":runner.store.json("mirror",uuid.uuid4().hex+".json",records)}
