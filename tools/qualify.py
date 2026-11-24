#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only A4 context/overhead evidence collector; no boot, install or configuration changes."""
import argparse, datetime, json, pathlib, subprocess
import a4ctl
PROBES={
    "uid":"id",
    "selinux":"getenforce; cat /proc/self/attr/current",
    "sdk_abi":"getprop ro.build.version.sdk; getprop ro.product.cpu.abi; getprop ro.product.cpu.abilist",
    "storage":"getprop ro.crypto.state; getprop ro.crypto.type; getprop sys.user.0.ce_available",
    "platform":"getprop ro.product.device; getprop ro.build.display.id",
    "devnull":"test -c /dev/null && stat /dev/null",
    "namespace":"readlink /proc/self/ns/mnt",
    "framework":"command -v am pm cmd dumpsys service settings content app_process logcat; service check activity; settings get system screen_brightness",
    "activity":"dumpsys -t 5 activity activities | grep -m 1 mResumedActivity",
    "packages":"pm path com.android.tv.settings",
    "memory":"grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo",
    "uptime":"cat /proc/uptime",
    "listener": "test -x /data/adb/modules/tvddropbear/tvddctl && /data/adb/modules/tvddropbear/tvddctl status --json",
    "listener_processes": "for p in $(pgrep -x tvddropbear 2>/dev/null); do echo PID=$p; cat /proc/$p/stat; if test -r /proc/$p/smaps_rollup; then grep '^Pss:' /proc/$p/smaps_rollup; else awk '/^Pss:/{sum+=$2}END{print \"Pss_kB=\"sum}' /proc/$p/smaps; fi; done",
}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial",required=True); p.add_argument("--host"); p.add_argument("--expect-serial")
    p.add_argument("--timeout",type=int,default=15)
    p.add_argument("--output",type=pathlib.Path,required=True)
    a=p.parse_args()
    if not 1<=a.timeout<=60: p.error("timeout must be 1..60")
    contexts=["adb-shell","adb-root"]+(["ssh-root"] if a.host else [])
    report={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"contexts":{}}
    for context in contexts:
        a.context=context
        result={}; report["contexts"][context]=result
        try: a4ctl.verify(a)
        except (ValueError,OSError,subprocess.TimeoutExpired) as e:
            result["preflight_error"]=str(e); continue
        for name,command in PROBES.items():
            try:
                r=a4ctl.execute(a,command,True)
                result[name]={"exit":r.returncode,"stdout":r.stdout[:16000],"stderr":r.stderr[:2000]}
            except (ValueError,OSError,subprocess.TimeoutExpired) as e:
                result[name]={"error":str(e)}
    # User chooses private local path; refuse overwrite of previous evidence.
    with a.output.open("x",encoding="utf-8") as f: json.dump(report,f,indent=2)
    print("Read-only evidence captured. Review before sharing; no physical acceptance implied.")
if __name__=="__main__": main()
