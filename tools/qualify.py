#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only compatibility collector using the common bounded, pinned execution core."""
import argparse
import json
from pathlib import Path
import sys
from tvdcore import Runner, Store, DEFAULT_HOME, utc, Unavailable, IdentityError
from tvdprofiles import inspect, PROBES

COMMON=("identity","context","devnull","unlock","framework","foreground","storage","memory","uptime")
ROOT=("magisk","listener","listener_processes")
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial",required=True)
    p.add_argument("--host")
    p.add_argument("--expect-serial",required=True)
    p.add_argument("--workspace",default=str(DEFAULT_HOME))
    p.add_argument("--timeout",type=int,default=15)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if not 1<=a.timeout<=60: p.error("timeout must be 1..60")
    try:
        store=Store(a.workspace)
        contexts=["adb-shell","adb-root"]+(["ssh-root"] if a.host else [])
        report={"schema":2,"utc":utc(),"contexts":{}}
        firmware=None
        for context in contexts:
            runner=Runner(a.serial,a.host,a.expect_serial,a.timeout,store,context)
            result={}; report["contexts"][context]=result
            try: identity=runner.verify(context,fresh=True)
            except Unavailable as exc:
                result["preflight_error"]=str(exc); continue
            if firmware and firmware!=identity["firmware"]:
                raise IdentityError("firmware changed between contexts")
            firmware=identity["firmware"]
            for name in COMMON+(ROOT if context!="adb-shell" else ()):
                try: result[name]=inspect(runner,name)
                except Unavailable as exc: result[name]={"status":"unavailable","error":str(exc)}
        report["complete"]=all("preflight_error" not in values and all(x.get("status")=="ok" for x in values.values()) for values in report["contexts"].values())
        ref=store.json("diagnostics","qualification-"+__import__("uuid").uuid4().hex+".json",report)
        # Only the summary is copied to the caller's chosen local host path.
        with a.output.open("x",encoding="utf-8") as f: json.dump(dict(report,host_evidence=ref),f,indent=2)
        print("Read-only evidence captured; no physical acceptance implied.")
        return 0 if report["complete"] else 1
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr); return 2
if __name__=="__main__": sys.exit(main())
