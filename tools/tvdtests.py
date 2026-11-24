# SPDX-License-Identifier: Apache-2.0
"""Declarative, read-only physical-device assertions. No executable test definitions."""
import json
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

def run_test(runner,name,steps,source_sha=None,artifact_sha256=None):
    safe_name(name)
    validate_steps(steps)
    for val,length in ((source_sha,40),(artifact_sha256,64)):
        if val is not None and not re.fullmatch("[0-9a-f]{"+str(length)+"}",val):
            raise ValueError("invalid provenance hash")
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
    report={"schema":1,"name":name,"utc":utc(),"kind":"read-only physical observation",
            "plan_sha256":digest(json.dumps(steps,sort_keys=True).encode()),
            "claimed_source_sha":source_sha,"claimed_artifact_sha256":artifact_sha256,
            "artifact_identity_verified":False,"results":results,
            "passed":all(x["status"]=="pass" for x in results)}
    return dict(report,file=runner.store.json("test-results",name+"-"+uuid.uuid4().hex[:12]+".json",report))
