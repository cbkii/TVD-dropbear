#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host-only A4 engineering helper. Explicit contexts; never retry ambiguous mutations."""
import argparse, os, pathlib, re, shlex, subprocess, sys, tempfile
EXPECTED = {"ro.product.device": ("xiaoyushan_emT","xiaoyushan"),
            "ro.build.version.sdk": ("28",)}
SSH_OPTIONS = ["-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
               "-o","ServerAliveInterval=15","-o","ServerAliveCountMax=2"]
def ssh_alias(host):
    if not host or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",host):
        raise ValueError("explicit safe SSH config alias required")
    return host
def adb_prefix(serial):
    if not serial or serial.startswith("-") or any(c.isspace() for c in serial):
        raise ValueError("explicit ADB serial required")
    return ["adb","-s",serial]
def argv_for(context, serial, host, command):
    if context == "ssh-root":
        return ["ssh",*SSH_OPTIONS,ssh_alias(host),command]
    return [*adb_prefix(serial),"shell",command if context=="adb-shell" else "su -c "+shlex.quote(command)]
def run(args,argv,**kw):
    return subprocess.run(argv,timeout=args.timeout,check=False,**kw)
def execute(args,command,capture=False):
    return run(args,argv_for(args.context,args.serial,args.host,command),text=True,capture_output=capture)
def verify(args):
    for prop,allowed in EXPECTED.items():
        r=execute(args,"getprop "+prop,True)
        if r.returncode or r.stdout.strip() not in allowed:
            raise ValueError("Target verification failed for "+prop)
    if args.expect_serial:
        r=execute(args,"getprop ro.serialno",True)
        if r.returncode or r.stdout.strip()!=args.expect_serial:
            raise ValueError("Device serial mismatch")
    r=execute(args,"id -u",True)
    if r.returncode or r.stdout.strip() != ("2000" if args.context=="adb-shell" else "0"):
        raise ValueError("Unexpected Android execution UID")
def remote_path(value):
    if not value.startswith("/") or any(ord(c)<32 or c in "*?[]\\" for c in value):
        raise ValueError("remote path must be absolute and non-glob")
    return value
def local_path(value):
    return str(pathlib.Path(value).expanduser().resolve())
def transfer_argv(args,op,first,second):
    remote=remote_path(first if op in ("pull","sync") else second)
    if op=="push":
        from tvdcore import validate_shared
        validate_shared(remote)
        if args.context!="adb-shell": raise ValueError("shared staging writes require unprivileged ADB-shell context")
    local=local_path(second if op in ("pull","sync") else first)
    if args.context=="adb-root":
        raise ValueError("adb-root does not make adb push/pull root; use ssh-root or adb-shell")
    if args.context=="adb-shell":
        if op=="sync": raise ValueError("incremental sync requires ssh-root and host rsync")
        return [*adb_prefix(args.serial),op,*( [remote,local] if op=="pull" else [local,remote])]
    target=ssh_alias(args.host)+":"+remote
    if op=="sync":
        return ["rsync","-rt","--safe-links","--protect-args","-e",shlex.join(["ssh",*SSH_OPTIONS]),target,local]
    # Modern OpenSSH SCP defaults to SFTP; -s explicitly prevents legacy SCP.
    return ["scp","-s",*SSH_OPTIONS,*( [target,local] if op=="pull" else [local,target])]
def screenshot(args,path):
    if args.context=="adb-shell":
        argv=[*adb_prefix(args.serial),"exec-out","screencap","-p"]
    elif args.context=="ssh-root":
        argv=argv_for(args.context,args.serial,args.host,"screencap -p")
    else:
        raise ValueError("use adb-shell or ssh-root for binary screenshot")
    r=run(args,argv,capture_output=True)
    if r.returncode: return r.returncode
    if not r.stdout.startswith(b"\x89PNG\r\n\x1a\n"): raise ValueError("invalid PNG output")
    dest=pathlib.Path(path).expanduser().resolve()
    with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False) as f:
        tmp=pathlib.Path(f.name); f.write(r.stdout)
    try: os.replace(tmp,dest)
    finally:
        if tmp.exists(): tmp.unlink()
    return 0
def main():
    # Preserve the original CLI; advanced structured operations share tvdctl.
    if len(sys.argv)>1 and sys.argv[1]=="engineering":
        del sys.argv[1]
        from tvdctl import main as engineering_main
        return engineering_main()
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--context",choices=("adb-shell","adb-root","ssh-root"),required=True)
    p.add_argument("--serial"); p.add_argument("--host"); p.add_argument("--expect-serial")
    p.add_argument("--timeout",type=int,default=30)
    p.add_argument("operation",choices=("doctor","exec","shell","pull","push","sync","install","screenshot","logcat"))
    p.add_argument("operands",nargs="*")
    a=p.parse_args()
    if not 1<=a.timeout<=600: p.error("timeout must be 1..600 seconds")
    counts={"doctor":0,"shell":0,"exec":1,"pull":2,"push":2,"sync":2,"install":1,"screenshot":1,"logcat":1}
    if len(a.operands)!=counts[a.operation]: p.error("wrong argument count for "+a.operation)
    try:
        verify(a)
        op=a.operation
        if op=="doctor": return execute(a,"id; getenforce; getprop ro.product.cpu.abi").returncode
        if op=="exec": return execute(a,a.operands[0]).returncode
        if op=="shell":
            argv=(["ssh","-t",*SSH_OPTIONS,ssh_alias(a.host)] if a.context=="ssh-root"
                  else [*adb_prefix(a.serial),"shell","-t",*(["su"] if a.context=="adb-root" else [])])
            return run(a,argv).returncode
        if op in ("pull","push","sync"): return run(a,transfer_argv(a,op,*a.operands)).returncode
        if op=="install":
            if a.context!="adb-shell": raise ValueError("APK install requires explicit adb-shell context")
            path=pathlib.Path(a.operands[0]).resolve()
            if not path.is_file() or path.suffix.lower()!=".apk": raise ValueError("local APK required")
            return run(a,[*adb_prefix(a.serial),"install","-r",str(path)]).returncode
        if op=="screenshot": return screenshot(a,a.operands[0])
        if op=="logcat":
            n=int(a.operands[0])
            if not 1<=n<=5000: raise ValueError("logcat count must be 1..5000")
            return execute(a,"logcat -d -t "+str(n)).returncode
    except (ValueError,OSError,subprocess.TimeoutExpired) as e:
        print(str(e)+"; outcome may be unknown, no retry",file=sys.stderr); return 4
if __name__=="__main__": sys.exit(main())
