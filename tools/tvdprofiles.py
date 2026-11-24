# SPDX-License-Identifier: Apache-2.0
"""Fixed, low-impact diagnostic probes. No user-controlled shell interpolation."""
from dataclasses import dataclass
import re
import uuid
from tvdcore import utc

@dataclass(frozen=True)
class Probe:
    command: str
    context: str = "any"
    sensitive: bool = False
    normalise: str = "ordered"

PROBES = {
    "identity": Probe("getprop ro.product.device; getprop ro.build.version.sdk; getprop ro.product.cpu.abi; getprop ro.build.fingerprint"),
    "context": Probe("id; getenforce; cat /proc/self/attr/current; readlink /proc/self/ns/mnt"),
    "memory": Probe("grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree|Cached|SReclaimable):' /proc/meminfo"),
    "zram": Probe("for f in /sys/block/zram*/disksize /sys/block/zram*/mm_stat; do if test -r \"$f\"; then echo \"$f\"; cat \"$f\"; fi; done"),
    "pressure": Probe("for f in /proc/pressure/memory /proc/pressure/cpu; do if test -r \"$f\"; then echo \"$f\"; cat \"$f\"; fi; done"),
    "processes": Probe("ps -A -o NAME",normalise="multiset"),
    "packages": Probe("pm list packages -f --user 0",normalise="set"),
    "disabled": Probe("pm list packages -d --user 0",normalise="set"),
    "services": Probe("service list",normalise="services"),
    "media_codec": Probe("dumpsys -t 5 media.codec",sensitive=True),
    "media_metrics": Probe("dumpsys -t 5 media.metrics",sensitive=True),
    "audio": Probe("dumpsys -t 5 audio",sensitive=True),
    "display": Probe("dumpsys -t 5 display",sensitive=True),
    "brightness": Probe("settings get system screen_brightness; settings get system screen_brightness_mode"),
    "picture_services": Probe("service list | grep -Ei 'picture|display|tv|mstar|hisense'",normalise="services"),
    "foreground": Probe("dumpsys -t 5 activity activities | grep -E 'mResumedActivity|topResumedActivity'",sensitive=True),
    "window": Probe("dumpsys -t 5 window windows | grep -E 'mCurrentFocus|mFocusedApp'",sensitive=True),
    "crash": Probe("logcat -b crash -d -t 300",sensitive=True),
    "playback_logs": Probe("logcat -d -t 800 -s MediaCodec ACodec OMXClient OMXNodeInstance ActivityManager AndroidRuntime",sensitive=True),
    "bluetooth": Probe("dumpsys -t 5 bluetooth_manager",sensitive=True),
    "network": Probe("ip link show; ip route show",sensitive=True),
    "connectivity": Probe("dumpsys -t 5 connectivity",sensitive=True),
    "modules": Probe("for f in /data/adb/modules/*/module.prop; do if test -f \"$f\"; then echo \"$f\"; grep -E '^(id|version|versionCode)=' \"$f\"; fi; done","root",normalise="ordered"),
    "magisk": Probe("magisk -v; getenforce","root"),
    "listener": Probe("if test -x /data/adb/modules/tvddropbear/tvddctl; then /data/adb/modules/tvddropbear/tvddctl status --json; else exit 1; fi","root"),
    "ota": Probe("pm path com.hisense.tv.ota; getprop ro.build.display.id"),
    "storage": Probe("df -k /sdcard; getprop ro.crypto.state; getprop ro.crypto.type"),
    "devnull": Probe("test -c /dev/null && echo character-device"),
    "framework": Probe("command -v am pm cmd dumpsys service settings content app_process logcat"),
}
PROFILES = {
    "status": ("identity","context","devnull","storage"),
    "memory": ("memory","zram","pressure","processes"),
    "playback": ("media_codec","media_metrics","audio","memory","playback_logs","crash"),
    "display": ("brightness","display","picture_services","foreground","window"),
    "application": ("foreground","window","crash","packages","disabled"),
    "bluetooth": ("bluetooth","services"),
    "network": ("network","connectivity"),
    "magisk": ("magisk","modules","listener","devnull"),
    "ota": ("ota","identity"),
    "startup": ("identity","processes","memory","foreground","crash"),
    "vendor": ("services","picture_services","framework"),
}

def inspect(runner,name):
    probe=PROBES.get(name)
    if probe is None:
        raise ValueError("unknown probe")
    return runner.execute(probe.command,probe.context,read_only=True,sensitive=probe.sensitive,label=name)

def profile(runner,name):
    if name not in PROFILES:
        raise ValueError("unknown profile")
    results={}
    for probe in PROFILES[name]:
        try:
            results[probe]=inspect(runner,probe)
        except ValueError as exc:
            from tvdcore import IdentityError
            if isinstance(exc,IdentityError):
                raise
            results[probe]={"status":"unavailable","error":str(exc)}
    report={"schema":1,"profile":name,"utc":utc(),"results":results,
            "complete":all(x["status"]=="ok" for x in results.values())}
    report["file"]=runner.store.json("diagnostics",uuid.uuid4().hex+".json",report)
    return report

def normalise(name,data):
    text=data.decode("utf-8","replace")
    lines=[x.rstrip() for x in text.splitlines() if x.strip()]
    mode=PROBES[name].normalise
    if mode=="services":
        return sorted(set(re.sub(r"^\s*\d+\s+","",x) for x in lines if not x.startswith("Found ")))
    if mode=="set":
        return sorted(set(lines))
    if mode=="multiset":
        from collections import Counter
        return dict(sorted(Counter(lines).items()))
    return lines
