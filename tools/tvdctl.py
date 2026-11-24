#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host engineering CLI; uses the same core as the optional MCP server."""
import argparse
import json
import sys
from tvdcore import Runner, Store, DEFAULT_HOME, evidence_page, Unavailable
from tvdprofiles import PROBES, PROFILES, inspect, profile
from tvdstate import SNAPSHOTS, snapshot, compare, record_capability, capabilities
from tvdui import hierarchy, keypress, wait_foreground, KEYS
from tvdmirror import ROOTS, list_references, mirror
from tvdtests import load_plan, run_test

def options(p):
    p.add_argument("--serial")
    p.add_argument("--host")
    p.add_argument("--expect-serial")
    p.add_argument("--context",choices=("auto","adb-shell","adb-root","ssh-root"),default="auto")
    p.add_argument("--timeout",type=int,default=20)
    p.add_argument("--workspace",default=str(DEFAULT_HOME))
    p.add_argument("--share-sensitive",action="store_true",help="explicitly include private diagnostic previews; redaction is best effort")

def runner_for(a,store):
    return Runner(a.serial,a.host,a.expect_serial,a.timeout,store,a.context,a.share_sensitive)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    options(p)
    sub=p.add_subparsers(dest="operation",required=True)
    x=sub.add_parser("inspect"); x.add_argument("probe",choices=PROBES)
    x=sub.add_parser("profile"); x.add_argument("name",choices=PROFILES)
    x=sub.add_parser("snapshot"); x.add_argument("name"); x.add_argument("--kind",choices=SNAPSHOTS,default="configuration")
    x=sub.add_parser("diff"); x.add_argument("before"); x.add_argument("after")
    x=sub.add_parser("capability-record"); x.add_argument("name"); x.add_argument("outcome",choices=("observed","supported","failed","unproven")); x.add_argument("evidence"); x.add_argument("note")
    sub.add_parser("capabilities")
    x=sub.add_parser("evidence"); x.add_argument("id"); x.add_argument("--stream",choices=("stdout","stderr"),default="stdout"); x.add_argument("--offset",type=int,default=0); x.add_argument("--lines",type=int,default=60); x.add_argument("--contains")
    x=sub.add_parser("exec"); x.add_argument("command"); x.add_argument("--allow-command",action="store_true")
    sub.add_parser("screenshot")
    x=sub.add_parser("ui-hierarchy"); x.add_argument("--non-sensitive-screen",action="store_true"); x.add_argument("--cleanup",action="store_true")
    x=sub.add_parser("ui-key"); x.add_argument("key",choices=KEYS); x.add_argument("--allow-ui",action="store_true")
    x=sub.add_parser("ui-wait"); x.add_argument("component"); x.add_argument("--seconds",type=int,default=15)
    x=sub.add_parser("reference-list"); x.add_argument("root",choices=ROOTS)
    x=sub.add_parser("mirror"); x.add_argument("paths",nargs="+"); x.add_argument("--verify",action="store_true")
    x=sub.add_parser("test"); x.add_argument("name"); x.add_argument("--plan"); x.add_argument("--source-sha"); x.add_argument("--artifact-sha256"); x.add_argument("--artifact"); x.add_argument("--package")
    try:
        a=p.parse_args()
        store=Store(a.workspace)
        if a.operation=="diff": result=compare(store,a.before,a.after)
        elif a.operation=="capability-record": result=record_capability(store,a.name,a.outcome,a.evidence,a.note)
        elif a.operation=="capabilities":
            identity=None
            if a.serial or a.host:
                r=runner_for(a,store)
                for context in r.choices("any"):
                    try: identity=r.verify(context); break
                    except Unavailable: continue
            result=capabilities(store,identity["firmware"],identity["serial_sha256"]) if identity else capabilities(store)
        elif a.operation=="evidence": result=evidence_page(store,a.id,a.stream,a.offset,a.lines,a.contains,a.share_sensitive)
        else:
            r=runner_for(a,store)
            if a.operation=="inspect": result=inspect(r,a.probe)
            elif a.operation=="profile": result=profile(r,a.name)
            elif a.operation=="snapshot": result=snapshot(r,a.name,a.kind)
            elif a.operation=="screenshot": result=r.binary_capture()
            elif a.operation=="ui-hierarchy": result=hierarchy(r,allow_shared=a.non_sensitive_screen,cleanup=a.cleanup)
            elif a.operation=="ui-key": result=keypress(r,a.key,allow_ui=a.allow_ui)
            elif a.operation=="ui-wait": result=wait_foreground(r,a.component,a.seconds)
            elif a.operation=="reference-list": result=list_references(r,a.root)
            elif a.operation=="mirror": result=mirror(r,a.paths,a.verify)
            elif a.operation=="test": result=run_test(r,a.name,load_plan(a.name,a.plan),a.source_sha,a.artifact_sha256,artifact=a.artifact,package=a.package)
            elif a.operation=="exec":
                if not a.allow_command: raise ValueError("explicit --allow-command required; arbitrary shell is not a read-only operation")
                result=r.execute(a.command,read_only=False,sensitive=True)
        print(json.dumps(result,indent=2,ensure_ascii=True))
        return 1 if isinstance(result,dict) and (result.get("status") not in (None,"ok") and isinstance(result.get("status"),str) or result.get("complete") is False or result.get("passed") is False or result.get("matched") is False) else 0
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr); return 2
if __name__=="__main__":
    sys.exit(main())
