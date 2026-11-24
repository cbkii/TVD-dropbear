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
