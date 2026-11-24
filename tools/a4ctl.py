#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host-only explicit-context A4 command runner. No automatic mutation retries."""
import argparse, shlex, subprocess, sys
EXPECTED = {"ro.product.device": ("xiaoyushan_emT","xiaoyushan"),
            "ro.build.version.sdk": ("28",)}
def argv_for(context, serial, host, command):
    if context == "ssh-root":
        if not host or host.startswith("-"): raise ValueError("safe SSH host alias required")
        return ["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
                "-o","ServerAliveInterval=15","-o","ServerAliveCountMax=2",host,command]
    if not serial or serial.startswith("-"): raise ValueError("explicit ADB serial required")
    return ["adb","-s",serial,"shell",command if context=="adb-shell" else "su -c "+shlex.quote(command)]
def execute(args,command,capture=False):
    return subprocess.run(argv_for(args.context,args.serial,args.host,command),timeout=args.timeout,
                          text=True,capture_output=capture,check=False)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--context",choices=("adb-shell","adb-root","ssh-root"),required=True)
    p.add_argument("--serial"); p.add_argument("--host"); p.add_argument("--timeout",type=int,default=30)
    p.add_argument("operation",choices=("doctor","exec"))
    p.add_argument("command",nargs="?")
    a=p.parse_args()
    if not 1<=a.timeout<=600: p.error("timeout must be 1..600 seconds")
    try:
        for prop,allowed in EXPECTED.items():
            r=execute(a,"getprop "+prop,True)
            if r.returncode or r.stdout.strip() not in allowed:
                print("Target verification failed for "+prop,file=sys.stderr); return 3
        r=execute(a,"id -u",True)
        if r.returncode or r.stdout.strip() != ("2000" if a.context=="adb-shell" else "0"):
            print("Unexpected Android execution UID",file=sys.stderr); return 3
        if a.operation=="doctor": return execute(a,"id; getenforce; getprop ro.product.cpu.abi").returncode
        if not a.command: p.error("exec requires a single command string")
        return execute(a,a.command).returncode
    except (ValueError,OSError,subprocess.TimeoutExpired) as e:
        print(str(e)+"; outcome may be unknown, no retry",file=sys.stderr); return 4
if __name__=="__main__": sys.exit(main())
