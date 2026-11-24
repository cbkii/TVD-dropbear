#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host engineering CLI; uses the same core as the optional MCP server."""
import argparse
import json
import sys
from tvdcore import Runner, Store, DEFAULT_HOME
from tvdprofiles import PROBES, PROFILES, inspect, profile
from tvdstate import SNAPSHOTS, snapshot, compare, record_capability, capabilities

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
    x=sub.add_parser("exec"); x.add_argument("command"); x.add_argument("--allow-command",action="store_true")
    sub.add_parser("screenshot")
    try:
        a=p.parse_args()
        store=Store(a.workspace)
        if a.operation=="diff": result=compare(store,a.before,a.after)
        elif a.operation=="capability-record": result=record_capability(store,a.name,a.outcome,a.evidence,a.note)
        elif a.operation=="capabilities": result=capabilities(store)
        else:
            r=runner_for(a,store)
            if a.operation=="inspect": result=inspect(r,a.probe)
            elif a.operation=="profile": result=profile(r,a.name)
            elif a.operation=="snapshot": result=snapshot(r,a.name,a.kind)
            elif a.operation=="screenshot": result=r.binary_capture()
            elif a.operation=="exec":
                if not a.allow_command: raise ValueError("explicit --allow-command required; arbitrary shell is not a read-only operation")
                result=r.execute(a.command,read_only=False,sensitive=True)
        print(json.dumps(result,indent=2,ensure_ascii=True))
        return 1 if isinstance(result,dict) and (result.get("status") not in (None,"ok") and isinstance(result.get("status"),str) or result.get("complete") is False) else 0
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr); return 2
if __name__=="__main__":
    sys.exit(main())
