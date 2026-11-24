# SPDX-License-Identifier: Apache-2.0
"""Host-only evidence-indexed snapshots, comparisons and knowledge records."""
import difflib
import json
import uuid
from tvdcore import utc, safe_name, digest, redact
from tvdprofiles import PROBES, inspect, normalise

SNAPSHOTS = {
    "configuration": ("packages","disabled","brightness","services","modules"),
    "runtime": ("memory","zram","pressure","processes","listener"),
    "platform": ("identity","context","framework","services","picture_services","ota"),
}

def snapshot(runner, name, kind="configuration"):
    safe_name(name)
    if kind not in SNAPSHOTS:
        raise ValueError("unknown snapshot kind")
    results={}
    identity=None
    for p in SNAPSHOTS[kind]:
        try:
            r=inspect(runner,p)
            identity=r["identity"]
            record={"status":r["status"],"evidence":r["id"],"context":r["context"]}
            if r["status"]=="ok":
                record["values"]=normalise(p,runner.read_result(r))
            results[p]=record
        except ValueError as exc:
            from tvdcore import IdentityError
            if isinstance(exc,IdentityError):
                raise
            results[p]={"status":"unavailable","error":str(exc)}
    if identity is None:
        raise ValueError("no verified snapshot source")
    report={"schema":1,"kind":kind,"utc":utc(),"identity":identity,"probes":results}
    file=runner.store.json("snapshots",name+".json",report)
    return {"file":file,"kind":kind,"complete":all(r["status"]=="ok" for r in results.values()),"status":{p:r["status"] for p,r in results.items()}}

def compare(store,before,after):
    a=store.load("snapshots",safe_name(before)+".json")
    b=store.load("snapshots",safe_name(after)+".json")
    if a["schema"]!=b["schema"] or a["kind"]!=b["kind"] or a["identity"]["serial_sha256"]!=b["identity"]["serial_sha256"]:
        raise ValueError("incompatible snapshots")
    changes={}
    for p in sorted(set(a["probes"])|set(b["probes"])):
        x,y=a["probes"].get(p,{}),b["probes"].get(p,{})
        if x.get("status")!="ok" or y.get("status")!="ok" or x.get("context")!=y.get("context"):
            changes[p]={"status":"not_comparable","before":x.get("status"),"after":y.get("status")}
            continue
        left,right=x["values"],y["values"]
        if left!=right:
            l=json.dumps(left,indent=2).splitlines()
            r=json.dumps(right,indent=2).splitlines()
            diff=list(difflib.unified_diff(l,r,fromfile=before,tofile=after,n=1,lineterm=""))
            changes[p]={"status":"changed","diff":[redact(s) for s in diff[:120]],"truncated":len(diff)>120}
    return {"kind":a["kind"],"before":before,"after":after,
            "firmware_changed":a["identity"]["firmware"]!=b["identity"]["firmware"],
            "changes":changes}

def record_capability(store, name, outcome, evidence_id, note):
    safe_name(name)
    if outcome not in ("observed","supported","failed","unproven"):
        raise ValueError("invalid capability outcome")
    if not isinstance(note,str) or len(note)>2000:
        raise ValueError("note limit")
    if not isinstance(evidence_id,str) or len(evidence_id)!=32:
        raise ValueError("exact evidence ID required")
    evidence=store.load("evidence",safe_name(evidence_id)+".json")
    if evidence["id"]!=evidence_id or not evidence["identity"]:
        raise ValueError("invalid evidence")
    if outcome=="supported" and evidence["status"]!="ok":
        raise ValueError("successful evidence required")
    # An observed exit code is not proof of a claimed vendor semantic; human/agent note is labelled.
    entry={"schema":1,"name":name,"outcome":outcome,"note":redact(note),
           "evidence":evidence_id,"evidence_status":evidence["status"],"context":evidence["context"],
           "identity":evidence["identity"],"utc":utc()}
    return {"file":store.json("knowledgebase",name+"-"+uuid.uuid4().hex[:12]+".json",entry),"entry":entry}

def capabilities(store,firmware=None,serial_hash=None):
    entries=[]
    for path in sorted(store.folder("knowledgebase").glob("*.json"))[:500]:
        try:
            record=store.load("knowledgebase",path.name)
            # Firmware validity is never assumed across devices or updates.
            record["applicability"]=("current" if firmware and serial_hash and
                record["identity"]["firmware"]==firmware and record["identity"]["serial_sha256"]==serial_hash
                else "not_verified_for_current_device")
            entries.append(record)
        except (ValueError,KeyError,OSError):
            continue
    return entries
