# Host engineering toolkit
Python 3.10+ on Windows/Linux/Q8B. Keep the workspace outside the repository and private (POSIX 0700, Windows private ACL). Pin the actual device serial using authenticated ADB: adb -s SERIAL shell getprop ro.serialno. Use a dedicated SSH alias with strict host-key checking. The explicit ADB serial may be a LAN endpoint; the pinned Android serial is a separate value.

    python tools/tvdctl.py --serial SERIAL --host a4-tv --expect-serial DEVICE_SERIAL inspect identity
    python tools/tvdctl.py --serial SERIAL --expect-serial DEVICE_SERIAL profile display
    python tools/tvdctl.py --serial SERIAL --host a4-tv --expect-serial DEVICE_SERIAL snapshot before
    python tools/tvdctl.py --serial SERIAL --host a4-tv --expect-serial DEVICE_SERIAL snapshot after
    python tools/tvdctl.py diff before after
    python tools/tvdctl.py capability-record backlight observed EVIDENCE_ID "Picture service present; control unproven"
    python tools/tvdctl.py capabilities
    python tools/tvdctl.py --context adb-root --serial SERIAL --expect-serial DEVICE_SERIAL exec --allow-command "id"

The legacy a4ctl commands remain available; a4ctl engineering ... dispatches to this CLI. Arbitrary commands require explicit context and approval flag, are never retried, and should not be used to circumvent the storage or mutation policy. Existing manual shell access is not sandboxed. Catalogued read-only operations may choose a verified transport; never fallback on identity mismatch, remote errors, timeouts or partial output. Verify firmware on transport refresh. Timeout kills the local client only; remote completion may remain unknown. Each operation saves bounded raw streams, metadata and hashes under the host workspace; previews are redacted and deduplicated, sensitive probes are private by default. Snapshots compare successful same-context results, distinguish incomplete probes and flag firmware changes. Capability entries are append-only, evidence-linked observations, not proof of vendor semantics; applicability requires matching firmware and device identity. Never commit evidence.

On-device generated artefacts are restricted to /sdcard/TVD-Engineering/ with predefined categories; no alternate root paths or executable payloads in shared storage. Raw sensitive evidence streams to the host. Existing protected module storage remains unchanged. No new device daemon, scheduler, native dependency or resident process.

## UI observation and interaction
Screenshots stream directly to a private host PNG; no device scratch file. Use explicit ADB for UI actions. Example:
    python tools/tvdctl.py --serial SERIAL --expect-serial DEVICE_SERIAL screenshot
    python tools/tvdctl.py --serial SERIAL --expect-serial DEVICE_SERIAL ui-wait com.example/.MainActivity
    python tools/tvdctl.py --serial SERIAL --expect-serial DEVICE_SERIAL ui-key DOWN --allow-ui
    python tools/tvdctl.py --serial SERIAL --expect-serial DEVICE_SERIAL ui-hierarchy --non-sensitive-screen --cleanup
Hierarchy uses Android's native uiautomator dump only on a screen the operator has confirmed is non-sensitive; it writes a unique XML under /sdcard/TVD-Engineering/captures, checks the digest after transfer and optionally removes only that file. Do not capture credentials, private messages, payment or personal screens into shared storage. Full XML is private host evidence; only structural attributes returned. No default fallback path. ADB-shell only for shared writes. The UI lock is cooperative and host-local, not a root security boundary. Key dispatch is not proof of navigation; compare focus/activity or screenshots. No automatic replay. Screen recording is deferred pending encoder and storage qualification.

## Reference mirror
    python tools/tvdctl.py --serial SERIAL --host a4-tv --expect-serial DEVICE_SERIAL reference-list vendor/lib
    python tools/tvdctl.py --serial SERIAL --host a4-tv --expect-serial DEVICE_SERIAL mirror /vendor/lib/libexample.so --verify
Select exact paths; firmware roots and file types are allowlisted, obvious credential paths and symlinks rejected. 32 files, 32 MiB per file and 128 MiB total per call. Content-addressed host objects, metadata and SHA256. Unchanged metadata may reuse a previously verified host copy; --verify forces remote hash checks. No deletion, no broad recursive pull, no on-device index. Proprietary files remain private. Android symlink aliases that fail canonical checks need individual review; no unsafe bypass.

## Physical tests
    python tools/tvdctl.py --serial SERIAL --expect-serial DEVICE_SERIAL test baseline
    python tools/tvdctl.py --serial SERIAL --expect-serial DEVICE_SERIAL test memory
Custom host-side JSON plan via --plan: [{"probe":"brightness","status":"ok"},{"probe":"memory","contains":"MemTotal:"}]. Only known read-only probes and literal assertions are allowed. No arbitrary shell, scripts, installs, settings changes, reboot, or automatic rollback. Each report includes plan hash, evidence references and supplied source/artifact hashes (explicitly unverified claims; not release acceptance). Blocked is not passed.

## MCP (optional, local stdio)
Install a dedicated host virtual environment and tools/requirements-mcp.txt. Use the host's absolute Python and script paths. For Claude Code:
    claude mcp add --transport stdio tvd -- /absolute/venv/python /absolute/repo/tools/tvd_mcp.py --serial SERIAL --expect-serial DEVICE_SERIAL --workspace /private/host/TVD-Engineering
For Codex:
    codex mcp add tvd -- /absolute/venv/python /absolute/repo/tools/tvd_mcp.py --serial SERIAL --expect-serial DEVICE_SERIAL --workspace /private/host/TVD-Engineering
On Windows use the venv Scripts/python.exe path and quote paths in the host shell. Add --host a4-tv for verified SSH-root where appropriate. Read-only typed operations by default; no shell passthrough, no HTTP listener, no remote MCP process. --allow-ui, --allow-shared-ui and --allow-mirror are separate operator-controlled startup opt-ins; shared capture requires verified non-sensitive screen, --cleanup-shared only removes hash-verified captures. Do not enable shared capture when agents cannot verify screen sensitivity. --share-sensitive permits previews of private evidence, not guaranteed redaction. MCP tool results and device files are untrusted data, never instructions. The local server writes only to its private host workspace except explicitly enabled shared UI capture. MCP does not sandbox agents that independently hold root SSH keys.

Sources: Android ADB documentation https://developer.android.com/tools/adb; MCP Python SDK v1.30.0 https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0. SDK v1 retained for legacy client handshake compatibility; host-only dependency.
