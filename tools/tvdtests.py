# SPDX-License-Identifier: Apache-2.0
"""Declarative, read-only physical-device assertions. No executable test definitions."""
import json
import hashlib
import shlex
from pathlib import Path
import re
import uuid
from tvdcore import utc, digest, safe_name
from tvdprofiles import inspect, PROBES
BUILTIN={
    "baseline":[{"probe":"devnull","contains":"character-device"},{"probe":"identity","contains":"28"},{"probe":"framework","contains":"/system/bin/am"}],
    "display":[{"probe":"brightness","status":"ok"},{"probe":"picture_services","status":"ok"}],
    "memory":[{"probe":"memory","contains":"MemTotal:"},{"probe":"processes","status":"ok"}],
    "ota":[{"probe":"ota","contains":"com.hisense.tv.ota"}],
}
def validate_steps(steps):
    if not isinstance(steps,list) or not 1<=len(steps)<=12:
        raise ValueError("test must contain 1..12 probe assertions")
    for step in steps:
        if not isinstance(step,dict) or set(step) not in ({"probe","contains"},{"probe","status"}):
            raise ValueError("only named probe and literal assertion are permitted")
        if step["probe"] not in PROBES:
            raise ValueError("unknown test probe")
        if "contains" in step and (not isinstance(step["contains"],str) or not 1<=len(step["contains"])<=200):
            raise ValueError("invalid literal assertion")
        if "status" in step and step["status"]!="ok":
            raise ValueError("only successful probe status may pass")
    return steps

def load_plan(name, path=None):
    safe_name(name)
    if path is None:
        if name not in BUILTIN: raise ValueError("unknown built-in test")
        return validate_steps(BUILTIN[name])
    with Path(path).open("rb") as f: data=f.read(32769)
    if len(data)>32768: raise ValueError("test definition too large")
    return validate_steps(json.loads(data))

def apk_identity(runner,artifact,package):
    """Verify actual host APK against installed single APK. Split sets are deliberately unsupported."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+",package):
        raise ValueError("invalid package identifier")
    path=Path(artifact)
    if path.suffix.lower()!=".apk" or not path.is_file() or path.stat().st_size>512*1024*1024:
        raise ValueError("bounded host APK required")
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    expected=h.hexdigest()
    r=runner.execute("pm path "+shlex.quote(package),read_only=True,label="installed-apk-path",sensitive=True)
    output=runner.read_result(r).decode("utf-8","replace").splitlines()
    if len(output)!=1 or not output[0].startswith("package:"):
        raise ValueError("single installed APK required; split sets not qualified")
    remote=output[0][8:]
    if not re.fullmatch(r"/(?:data/app|system/app|system/priv-app|vendor/app|product/app)/[A-Za-z0-9_./=+~-]+\.apk",remote) or ".." in remote.split("/"):
        raise ValueError("unexpected package path")
    # Reading an installed APK is not creating an engineering workspace under /data.
    r=runner.execute("sha256sum "+shlex.quote(remote),read_only=True,label="installed-apk-hash",sensitive=True)
    actual=runner.read_result(r).decode("utf-8","replace").split()
    if not actual or actual[0]!=expected:
        raise ValueError("installed APK differs from host artifact")
    return {"package":package,"sha256":expected,"evidence":r["id"],"identity":r["identity"]}
def run_test(runner,name,steps,source_sha=None,artifact_sha256=None,*,artifact=None,package=None):
    safe_name(name)
    validate_steps(steps)
    for val,length in ((source_sha,40),(artifact_sha256,64)):
        if val is not None and not re.fullmatch("[0-9a-f]{"+str(length)+"}",val):
            raise ValueError("invalid provenance hash")
    if bool(artifact)!=bool(package): raise ValueError('artifact and package must be supplied together')
    before=apk_identity(runner,artifact,package) if artifact else None
    if before and artifact_sha256 and artifact_sha256!=before['sha256']: raise ValueError('claimed artifact hash differs')
    results=[]
    for step in steps:
        try:
            r=inspect(runner,step["probe"])
            passed=r["status"]=="ok"
            if passed and "contains" in step:
                passed=step["contains"].encode() in runner.read_result(r)
            results.append({"probe":step["probe"],"status":"pass" if passed else "fail",
                            "evidence":r["id"],"identity":r["identity"],"context":r["context"]})
        except ValueError as exc:
            from tvdcore import IdentityError
            if isinstance(exc,IdentityError): raise
            results.append({"probe":step["probe"],"status":"blocked","reason":str(exc)})
    after=apk_identity(runner,artifact,package) if artifact else None
    if before and (before["sha256"]!=after["sha256"] or before["identity"]["firmware"]!=after["identity"]["firmware"] or before["identity"]["serial_sha256"]!=after["identity"]["serial_sha256"]):
        raise ValueError("installed artifact or device changed during test")
    report={"schema":1,"name":name,"utc":utc(),"kind":"read-only physical observation",
            "plan_sha256":digest(json.dumps(steps,sort_keys=True).encode()),
            "claimed_source_sha":source_sha,"claimed_artifact_sha256":artifact_sha256,
            "artifact_identity_verified":bool(before),"artifact_verification_before":before,"artifact_verification_after":after,"results":results,
            "passed":all(x["status"]=="pass" for x in results)}
    return dict(report,file=runner.store.json("test-results",name+"-"+uuid.uuid4().hex[:12]+".json",report))
