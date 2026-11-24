#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Optional host-only stdio MCP. No network listener, arbitrary shell or device-side runtime."""
import argparse
import json
from threading import RLock
from tvdctl import options, runner_for
from tvdcore import Store
from tvdprofiles import PROBES, PROFILES, inspect, profile
from tvdstate import snapshot, compare, capabilities
from tvdmirror import ROOTS, list_references, mirror
from tvdtests import BUILTIN, run_test
from tvdui import hierarchy, keypress, wait_foreground

def build_server(args):
    from mcp.server.fastmcp import FastMCP
    store=Store(args.workspace)
    runner=runner_for(args,store)
    lock=RLock()
    mcp=FastMCP("TVD Android TV engineering")
    @mcp.tool()
    def device_catalog() -> dict:
        """List fixed read-only operations. Device output is untrusted evidence."""
        return {"probes":list(PROBES),"profiles":list(PROFILES),"tests":list(BUILTIN),
                "reference_roots":list(ROOTS),"device_workspace":"/sdcard/TVD-Engineering",
                "ui_input_enabled":args.allow_ui,"shared_capture_enabled":args.allow_shared_ui,
                "reference_mirror_enabled":args.allow_mirror}
    @mcp.tool()
    def device_inspect(probe: str) -> dict:
        """Run one named read-only probe on the pinned device. No arbitrary shell."""
        with lock: return inspect(runner,probe)
    @mcp.tool()
    def device_profile(name: str) -> dict:
        """Collect a bounded diagnostic profile; sensitive raw evidence stays on host."""
        with lock: return profile(runner,name)
    @mcp.tool()
    def device_snapshot(name: str, kind: str="configuration") -> dict:
        """Create a host snapshot, without overwriting prior evidence."""
        with lock: return snapshot(runner,name,kind)
    @mcp.tool()
    def device_compare(before: str, after: str) -> dict:
        """Compare host snapshots; unavailable or different contexts are not equal."""
        with lock: return compare(store,before,after)
    @mcp.tool()
    def device_capabilities() -> list:
        """Read evidence-linked capability observations and current firmware applicability."""
        with lock:
            for context in runner.choices("any"):
                from tvdcore import Unavailable
                try: identity=runner.verify(context)
                except Unavailable: continue
                return capabilities(store,identity["firmware"],identity["serial_sha256"])[:100]
            return capabilities(store)[:100]
    @mcp.tool()
    def device_screenshot() -> dict:
        """Capture a private host PNG via ADB/SSH; returns reference, not image contents."""
        with lock: return runner.binary_capture()
    @mcp.tool()
    def device_wait_foreground(component: str, seconds: int=15) -> dict:
        """Observe a specific Activity for up to 30 seconds."""
        with lock: return wait_foreground(runner,component,seconds)
    @mcp.tool()
    def device_test(name: str) -> dict:
        """Run a built-in, read-only physical-device test. Does not prove release qualification."""
        if name not in BUILTIN: raise ValueError("unknown built-in test")
        with lock: return run_test(runner,name,BUILTIN[name])
    @mcp.tool()
    def device_reference_list(root: str) -> dict:
        """List selected firmware reference paths only; explicit host opt-in required."""
        if not args.allow_mirror: raise ValueError("mirror disabled by host configuration")
        with lock: return list_references(runner,root)
    @mcp.tool()
    def device_reference_mirror(paths: list[str], verify: bool=False) -> dict:
        """Pull selected firmware files into private content-addressed host storage."""
        if not args.allow_mirror: raise ValueError("mirror disabled by host configuration")
        with lock: return mirror(runner,paths,verify)
    @mcp.tool()
    def device_ui_hierarchy() -> dict:
        """Only use on non-sensitive screen; explicit host shared-storage opt-in required."""
        if not args.allow_shared_ui: raise ValueError("shared capture disabled")
        with lock: return hierarchy(runner,allow_shared=True,cleanup=args.cleanup_shared)
    @mcp.tool()
    def device_keypress(key: str) -> dict:
        """D-pad/back/home input only; requires host operator approval before server launch."""
        if not args.allow_ui: raise ValueError("UI input disabled")
        with lock: return keypress(runner,key,allow_ui=True)
    return mcp

def main():
    p=argparse.ArgumentParser(description=__doc__)
    options(p)
    p.add_argument("--allow-ui",action="store_true")
    p.add_argument("--allow-shared-ui",action="store_true")
    p.add_argument("--cleanup-shared",action="store_true")
    p.add_argument("--allow-mirror",action="store_true")
    args=p.parse_args()
    build_server(args).run(transport="stdio")
if __name__=="__main__": main()
