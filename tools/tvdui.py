# SPDX-License-Identifier: Apache-2.0
"""On-demand UI inspection and bounded D-pad input. No accessibility service."""
import re
import time
import uuid
import xml.etree.ElementTree as ET
import shlex
from contextlib import contextmanager
import a4ctl
from tvdcore import SHARED, shared_path, bounded, digest, utc, safe_name
from tvdprofiles import inspect

KEYS={"UP":19,"DOWN":20,"LEFT":21,"RIGHT":22,"CENTER":23,"BACK":4,"HOME":3}
CAP=2*1024*1024

@contextmanager
def mutation_lock(runner):
    # Cooperative local coordination only. Does not restrict direct root sessions or other hosts.
    p=runner.store.folder("locks")/"ui.lock"
    try:
        p.mkdir(mode=0o700)
    except FileExistsError:
        raise ValueError("UI lock held; inspect owner manually; no stale-lock guessing")
    try:
        yield
    finally:
        p.rmdir()

def shell_runner(runner):
    if runner.context not in ("auto","adb-shell") or not runner.serial:
        raise ValueError("UI interaction requires explicit ADB transport and shell context")
    from tvdcore import Runner
    return Runner(runner.serial,runner.host,runner.expect_serial,runner.timeout,runner.store,"adb-shell",runner.share_sensitive)

def safe_workspace(category):
    # /sdcard itself is a platform-managed symlink; reject symlinks BELOW its resolved root.
    dest=SHARED+"/"+category
    return (
        'base=$(readlink -f /sdcard) && test -n "$base" && '
        'test ! -L '+shlex.quote(SHARED)+' && '
        'mkdir -p '+shlex.quote(dest)+' && test ! -L '+shlex.quote(dest)+' && '
        'test "$(readlink -f '+shlex.quote(dest)+')" = "$base/TVD-Engineering/'+category+'" && '
        'df -k '+shlex.quote(dest)+" | awk 'END {exit !($4 >= 16384)}'"
    )

def hierarchy(runner, *, allow_shared=False, cleanup=False):
    """UI XML may contain secrets. Only use shared storage for a verified non-sensitive screen."""
    if not allow_shared:
        raise ValueError("explicit non-sensitive shared UI capture opt-in required")
    r=shell_runner(runner)
    path=shared_path("captures","ui-"+uuid.uuid4().hex+".xml")
    q=shlex.quote(path)
    with mutation_lock(r):
        r.verify("adb-shell",fresh=True)
        command=(safe_workspace("captures")+" && test ! -e "+q+" && test ! -L "+q+
                 " && (ulimit -f 4096 && uiautomator dump "+q+")"+" && test -f "+q+" && test ! -L "+q+
                 " && test \"$(stat -c %s "+q+")\" -le "+str(CAP)+" && sha256sum "+q)
        result=r.execute(command,"shell",label="ui-hierarchy",sensitive=True)
        output=r.read_result(result).decode("utf-8","replace")
        expected=re.search(r"(?m)^([0-9a-f]{64})\s+",output)
        if not expected:
            raise ValueError("hierarchy digest unavailable; shared file retained")
        raw=bounded([*a4ctl.adb_prefix(r.serial),"exec-out",r.guard("adb-shell")+" && cat "+q],r.timeout,CAP)
        data=raw["stdout"]
        if raw["kind"]!="exited" or raw["local_exit"]!=0 or digest(data)!=expected[1]:
            raise ValueError("hierarchy transfer incomplete; shared file retained")
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise ValueError("unsafe XML")
        try: tree=ET.fromstring(data)
        except ET.ParseError as exc: raise ValueError("invalid hierarchy XML") from exc
        nodes=[]
        for node in tree.iter("node"):
            # No text/content-description returned by default. Full XML stays in private host storage.
            if len(nodes)>=200:
                break
            attrs=node.attrib
            nodes.append({k:attrs.get(k,"") for k in ("class","resource-id","bounds","focused","focusable","enabled")})
        file=r.store.write("captures",safe_name(path.rsplit("/",1)[-1]),data)
        cleaned=False
        if cleanup:
            # Recheck transferred content before removing only our exact file.
            check=r.execute("test ! -L "+q+" && test \"$(sha256sum "+q+" | cut -d' ' -f1)\" = "+expected[1]+" && rm "+q,
                            "shell",label="ui-cleanup")
            cleaned=check["status"]=="ok"
        return {"file":file,"sha256":digest(data),"device_path":path,"cleaned":cleaned,
                "nodes":nodes,"utc":utc(),"sensitive":True}

def keypress(runner,key,*,allow_ui=False):
    if not allow_ui or key not in KEYS:
        raise ValueError("explicit UI approval and allowlisted D-pad key required")
    r=shell_runner(runner)
    with mutation_lock(r):
        before=inspect(r,"window")
        if before["status"]!="ok":
            raise ValueError("UI precondition unavailable; no key sent")
        action=r.execute("input keyevent "+str(KEYS[key]),"shell",label="ui-key")
        # Do not replay on unknown completion. Observe; success of key dispatch is not success of navigation.
        after=inspect(r,"window") if action["status"]=="ok" else None
        return {"key":key,"dispatch":action,"before":before,"after":after,
                "navigation_verified":False}

def wait_foreground(runner,component,seconds=15):
    if not re.fullmatch(r"[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+",component) or not 1<=seconds<=30:
        raise ValueError("explicit package/activity and 1..30 seconds required")
    r=shell_runner(runner)
    deadline=time.monotonic()+seconds
    evidence=[]
    while time.monotonic()<deadline:
        # Bound each probe by the remaining budget, including device identity check.
        r.timeout=max(1,min(runner.timeout,int(deadline-time.monotonic()),5))
        result=inspect(r,"foreground")
        evidence.append(result["id"])
        if result["status"]!="ok":
            return {"matched":False,"status":"observation_failed","evidence":evidence}
        text=r.read_result(result).decode("utf-8","replace")
        if re.search(r"(?<![A-Za-z0-9_.$/])"+re.escape(component)+r"(?![A-Za-z0-9_.$/])",text):
            return {"matched":True,"evidence":evidence}
        time.sleep(min(1,max(0,deadline-time.monotonic())))
    return {"matched":False,"status":"deadline","evidence":evidence}
