# SPDX-License-Identifier: Apache-2.0
"""Host-only bounded execution and evidence storage. No device-side agent runtime."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import threading
import time
import uuid

import a4ctl

SHARED = "/sdcard/TVD-Engineering"
CATEGORIES = {"staging", "captures", "diagnostics", "snapshots", "test-results", "exports"}
CONTEXTS = ("adb-shell", "adb-root", "ssh-root")
MAX_OUTPUT = 8 * 1024 * 1024
MAX_PREVIEW = 3000
DEFAULT_HOME = Path.home() / "TVD-Engineering"
IDENTITY = "getprop ro.product.device; getprop ro.build.version.sdk; getprop ro.serialno; getprop ro.build.fingerprint; id -u"
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
SENSITIVE = re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|(?:password|passwd|token|secret|api[_-]?key|cookie)\s*[:=]\s*)\S+")
URL_SECRET = re.compile(r"(?i)(https?://)[^/\s@]+:[^/\s@]+@|https?://[^\s]+[?][^\s]+")
PEM = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)")

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def safe_name(value):
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value) or value in (".", ".."):
        raise ValueError("invalid identifier")
    return value

def shared_path(category, name):
    if category not in CATEGORIES:
        raise ValueError("invalid shared-storage category")
    return f"{SHARED}/{category}/{safe_name(name)}"

def validate_shared(path):
    if not isinstance(path, str) or not path.startswith(SHARED + "/"):
        raise ValueError("device writes must be under " + SHARED)
    parts = path[len(SHARED)+1:].split("/")
    if len(parts) != 2 or parts[0] not in CATEGORIES:
        raise ValueError("expected workspace category and filename")
    return shared_path(*parts)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def redact(text):
    text = PEM.sub("[REDACTED PRIVATE KEY]", text)
    text = URL_SECRET.sub("[REDACTED URL]", text)
    return SENSITIVE.sub(r"\1[REDACTED]", text)

def preview(data, limit=MAX_PREVIEW):
    """Best effort only; never treat log text as trusted instructions."""
    text = redact(data.decode("utf-8", "replace"))
    lines = text.splitlines()
    compact = []
    count = 0
    prev = None
    for line in lines:
        if line == prev:
            count += 1
            continue
        if count:
            compact.append(f"[previous line repeated {count} times]")
        compact.append(line)
        prev, count = line, 0
    if count:
        compact.append(f"[previous line repeated {count} times]")
    out = "\n".join(compact)
    if len(out) > limit:
        out = out[:limit//2] + "\n[preview truncated; see evidence]\n" + out[-limit//2:]
    return out

class Store:
    """Local evidence only. POSIX 0700/0600; on Windows use a private user ACL."""
    def __init__(self, root=DEFAULT_HOME):
        self.root = Path(root).expanduser().absolute()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("unsafe host workspace")
        if os.name == "posix" and self.root.stat().st_mode & 0o077:
            raise ValueError("host workspace must be private (chmod 700)")
    def folder(self, name):
        p = self.root / safe_name(name)
        p.mkdir(exist_ok=True, mode=0o700)
        if p.is_symlink() or not p.is_dir() or (os.name == "posix" and p.stat().st_mode & 0o077):
            raise ValueError("unsafe workspace subdirectory")
        return p
    def write(self, category, name, data):
        p = self.folder(category) / safe_name(name)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        except BaseException:
            p.unlink(missing_ok=True)
            raise
        return str(p.relative_to(self.root))
    def json(self, category, name, value):
        return self.write(category, name, (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode())
    def read(self, category, name, cap=MAX_OUTPUT):
        p = self.folder(category) / safe_name(name)
        if p.is_symlink() or not p.is_file():
            raise ValueError("not a workspace file")
        with p.open("rb") as f:
            data = f.read(cap + 1)
        if len(data) > cap:
            raise ValueError("workspace object exceeds read limit")
        return data
    def load(self, category, name):
        return json.loads(self.read(category, name))

def bounded(argv, seconds, cap=MAX_OUTPUT):
    """Drain both streams concurrently with an aggregate byte ceiling and wall timeout.
    Killing the LOCAL client is not proof of remote cancellation.
    """
    if not 1 <= seconds <= 600 or not 1024 <= cap <= 64*1024*1024:
        raise ValueError("invalid execution bounds")
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        return {"local_exit": None, "kind": "client_unavailable", "stdout": b"", "stderr": str(exc).encode(),
                "duration_ms": int((time.monotonic()-started)*1000)}
    buffers = [bytearray(), bytearray()]
    guard = threading.Lock()
    overflow = threading.Event()
    def drain(pipe, out):
        try:
            while True:
                chunk = pipe.read1(65536)
                if not chunk:
                    break
                with guard:
                    room = cap - sum(map(len, buffers))
                    out.extend(chunk[:max(0,room)])
                    if len(chunk) > room:
                        overflow.set()
                        break
        except OSError:
            overflow.set()
        finally:
            pipe.close()
    readers = [threading.Thread(target=drain, args=(pipe, buf), daemon=True)
               for pipe,buf in zip((proc.stdout,proc.stderr),buffers)]
    for thread in readers:
        thread.start()
    kind = "exited"
    deadline = started + seconds
    while proc.poll() is None:
        if overflow.is_set():
            kind = "output_limit"
            break
        if time.monotonic() >= deadline:
            kind = "timeout"
            break
        time.sleep(0.025)
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        kind = "timeout"
    for thread in readers:
        thread.join(timeout=max(0,min(1,deadline-time.monotonic())))
    if overflow.is_set():
        kind = "output_limit"
    elif any(thread.is_alive() for thread in readers):
        kind = "timeout"
    with guard:
        out, err = map(bytes, buffers)
    return {"local_exit":proc.returncode, "kind":kind, "stdout":out, "stderr":err,
            "duration_ms":int((time.monotonic()-started)*1000)}

class IdentityError(ValueError):
    pass

class Unavailable(ValueError):
    pass

class Runner:
    def __init__(self, serial=None, host=None, expect_serial=None, timeout=20, store=None,
                 context="auto", share_sensitive=False):
        if context not in ("auto", *CONTEXTS):
            raise ValueError("invalid context")
        if not expect_serial or not expect_serial.strip() or any(ord(c)<32 for c in expect_serial):
            raise ValueError("pin exact Android ro.serialno with --expect-serial")
        if not serial and not host:
            raise ValueError("explicit ADB serial and/or SSH alias required")
        if serial:
            a4ctl.adb_prefix(serial)
        if host:
            a4ctl.ssh_alias(host)
        if not 1 <= timeout <= 120:
            raise ValueError("timeout must be 1..120 seconds")
        self.serial, self.host, self.expect_serial = serial, host, expect_serial
        self.timeout, self.store, self.context = timeout, store or Store(), context
        self.share_sensitive = share_sensitive
        self._verified = {}
        self._firmware = None

    def choices(self, required):
        if required not in ("shell","root","any"):
            raise ValueError("invalid required context")
        allowed = {"shell":("adb-shell",),"root":("ssh-root","adb-root"),
                   "any":("adb-shell","ssh-root","adb-root")}[required]
        if self.context != "auto":
            if self.context not in allowed:
                raise ValueError("explicit context incompatible with operation")
            allowed = (self.context,)
        return [c for c in allowed if (self.host if c=="ssh-root" else self.serial)]

    def _call(self, context, command, cap=MAX_OUTPUT):
        return bounded(a4ctl.argv_for(context,self.serial,self.host,command),self.timeout,cap)

    def verify(self, context, fresh=False):
        cached = self._verified.get(context)
        if cached and not fresh and time.monotonic()-cached[0] < 5:
            return cached[1]
        r = self._call(context,IDENTITY,16384)
        if r["kind"] != "exited" or r["local_exit"] != 0:
            self._verified.pop(context,None)
            raise Unavailable(f"{context} preflight unavailable")
        lines = r["stdout"].decode("utf-8","replace").splitlines()
        if len(lines)!=5:
            raise IdentityError("unexpected identity response; no fallback")
        model,sdk,serial,firmware,uid = lines
        if model not in a4ctl.EXPECTED["ro.product.device"] or sdk!="28" or serial!=self.expect_serial:
            raise IdentityError("A4 identity mismatch; no fallback")
        if not firmware or uid!=("2000" if context=="adb-shell" else "0"):
            raise IdentityError("firmware or execution UID mismatch; no fallback")
        if self._firmware is not None and firmware!=self._firmware:
            raise IdentityError("firmware changed during session; restart and revalidate")
        self._firmware=firmware
        info={"device":model,"sdk":sdk,"serial_sha256":digest(serial.encode()),"firmware":firmware,"uid":uid}
        self._verified[context]=(time.monotonic(),info)
        return info

    def _save(self, context, identity, r, label, sensitive, remote_exit):
        ident=uuid.uuid4().hex
        out=self.store.write("evidence",ident+".stdout",r["stdout"])
        err=self.store.write("evidence",ident+".stderr",r["stderr"])
        status = ("ok" if remote_exit==0 else "remote_error") if remote_exit is not None else (
            "transport_unknown" if r["kind"]=="exited" else r["kind"])
        meta={"schema":1,"id":ident,"label":label,"utc":utc(),"context":context,"identity":identity,
              "status":status,"remote_exit":remote_exit,"local_exit":r["local_exit"],
              "duration_ms":r["duration_ms"],"stdout":out,"stderr":err,
              "stdout_sha256":digest(r["stdout"]),"stderr_sha256":digest(r["stderr"]),
              "stdout_bytes":len(r["stdout"]),"stderr_bytes":len(r["stderr"]),
              "complete":remote_exit is not None,"sensitive":sensitive}
        self.store.json("evidence",ident+".json",meta)
        show=not sensitive or self.share_sensitive
        return dict(meta,stdout_preview=preview(r["stdout"]) if show else "[private evidence on host]",
                    stderr_preview=preview(r["stderr"],1000) if show else "[private evidence on host]")

    def execute(self, command, required="any", *, read_only=False, sensitive=True, label="command", cap=MAX_OUTPUT):
        # Only built-in typed operations may set read_only=True; caller-supplied shell is never auto-retried.
        if not isinstance(command,str) or not command or len(command)>16384 or "\x00" in command:
            raise ValueError("invalid command")
        if not read_only and self.context=="auto":
            raise ValueError("mutation/arbitrary command requires explicit execution context")
        errors=[]
        for context in self.choices(required):
            try:
                identity=self.verify(context,fresh=not read_only)
            except Unavailable as exc:
                errors.append(str(exc))
                if not read_only:
                    raise
                continue
            marker="TVD_EXIT_"+uuid.uuid4().hex
            wrapped="(\n"+command+"\n)\ntvd_rc=$?\nprintf '\\n"+marker+":%s\\n' \"$tvd_rc\""
            r=self._call(context,wrapped,cap)
            remote_exit=None
            if r["kind"]=="exited":
                match=re.search(rb"\n"+marker.encode()+rb":([0-9]{1,3})\r?\n\Z",r["stdout"])
                if match and int(match[1])<=255:
                    remote_exit=int(match[1])
                    r["stdout"]=r["stdout"][:match.start()]
            result=self._save(context,identity,r,label,sensitive,remote_exit)
            # No retries after timeout, partial output, unknown mutation, or remote error.
            # A clean client-start/transport failure on a catalogued read-only operation may fallback.
            if read_only and remote_exit is None and r["kind"] in ("exited","client_unavailable") and not r["stdout"]:
                self._verified.pop(context,None)
                errors.append(result["id"])
                continue
            result["fallback_attempts"]=errors
            return result
        raise Unavailable("no verified context available: "+", ".join(errors))

    def read_result(self,result):
        if result["status"]!="ok" or not result["complete"]:
            raise ValueError("incomplete remote result")
        return self.store.read("evidence",result["id"]+".stdout")

    def binary_capture(self):
        # ADB's exec-out avoids a PTY and shared storage. SSH stdout is also binary-safe.
        for context in self.choices("any"):
            if context=="adb-root":
                continue
            try:
                identity=self.verify(context)
            except Unavailable:
                continue
            argv=([*a4ctl.adb_prefix(self.serial),"exec-out","screencap","-p"] if context=="adb-shell"
                  else a4ctl.argv_for(context,self.serial,self.host,"screencap -p"))
            r=bounded(argv,self.timeout,MAX_OUTPUT)
            if r["kind"]!="exited" or r["local_exit"]!=0 or not r["stdout"].startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("screenshot failed; no automatic retry")
            name=uuid.uuid4().hex+".png"
            return {"file":self.store.write("captures",name,r["stdout"]),"sha256":digest(r["stdout"]),
                    "bytes":len(r["stdout"]),"context":context,"identity":identity,"utc":utc()}
        raise Unavailable("no verified screenshot context")
