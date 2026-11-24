# TVD engineering reference

## Design
Upstream baseline v1.11 (5db14725c51be34e22c7fa9d3b7df491fa77a4c9). Preserve Dropbear cryptography, Android PTY, dynamic Bionic linkage, issue #1 private /dev key shim and PR #2 normal PID file. Remove VDLU, upstream feed, passwords and UI. ARM32/ARM64; daemon API 24, bundles API 28. No IPv6 or forwarding in first TV profile. IPv4 loopback or explicit RFC1918 address; no wildcard/public binds. No legacy scp -O; modern scp uses SFTP. rsync does not preserve ACL/xattrs in this build. Host key and public keys persist in root-owned /data/adb/tvddropbear. DE storage requires explicit acceptance; device encryption depends on firmware. Root credentials are not a privilege sandbox.

## Before install
Use existing ADB with explicit -s SERIAL; verify root, SDK, ABI, getenforce, /dev/null character device, crypto state, toybox setsid, stat, awk, available listener ports and recovery. Reject coexistence with upstream; stop and remove it separately, preserve backups; never silently import credentials. Build exact ZIP, verify SHA256 and provenance. No physical tests have been run at this baseline. Do not extract executable test payloads into shared storage or create engineering workspaces under /data/local/tmp. Use the normal explicitly authorised disabled-by-default Magisk installation and loopback trial with independent ADB recovery. Existing protected module storage is reserved for the module.

## Provision
Fresh installation does not enable the listener. Keep ADB reachable; use ADB root for lifecycle. On Magisk installed path:
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl init --accept-de-storage'"
Generate Ed25519 client keys on the host (one per agent). Pass only public key via stdin:
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl keys add'" < agent.pub
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl fingerprint'"
Use authenticated ADB to verify the host fingerprint before trusting SSH. Trial without persistent enable:
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl trial'"
    adb -s SERIAL forward tcp:2222 tcp:2222
After trial, stop via ADB. Enable/start only after owner authorises persistent service:
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl enable'"
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl start'"
    adb -s SERIAL forward tcp:2222 tcp:2222
    ssh -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -i agent_key -p 2222 root@127.0.0.1
Provision known_hosts via independently verified fingerprint first. For direct LAN, stop via ADB, set BIND to reserved private address, start. No forwarding or router exposure. The current boot entry makes one bounded start attempt; a LAN address not assigned at boot may require manual start. No automatic retries beyond initial readiness. Use ADB if SSH fails.

## Lifecycle and rollback
tvddctl status --json, doctor, logs, fingerprint, keys list/add/remove, config show/set BIND/PORT, enable/disable/trial/start/stop/restart. Key revocation prevents future use; existing sessions are not forcibly terminated. Stop targets only verified listener; sessions may survive. Disable writes ENABLED=0 then stops listener. If ambiguous state, inspect PID, /proc/PID/exe, /proc/PID/stat and sockets via ADB; never blindly clear ownership or kill by name. For lock left by crash, verify no controller/start in flight before removing the empty control.lock directory. Reboot only after approved rollback and ADB recovery verified. PID/lock state lives in root-only /dev/tvddropbear/state (tmpfs, automatically cleared at boot); persistent keys/config remain under /data/adb/tvddropbear. Magisk disable/remove is separate from listener state; uninstall retains keys and configuration. Back up before upgrade; stop via ADB and close sessions before changing native binaries. Never delete /dev/null or chmod Android parent directories. Do not run root agent sessions in parallel for mutations.

## Qualification gates
- Native binaries: ELF ABI/API, on-device help/version, keygen, PTY, command exit status, SFTP and rsync hashes. Reject passwords, unknown keys and non-root usernames.
- Compare SSH-root, ADB-shell and ADB-root: id, getenforce, namespaces and platform tools am, pm, cmd, dumpsys, service, settings, content, app_process, logcat. Do not weaken security.
- Measure baseline ADB only, upstream stock (offline updater risk; controlled test only), configured upstream and TVD. Capture PSS, CPU ticks, process counts, idle outbound traffic, startup, concurrent sessions, transfer hashes and latency, standby/wake, network loss, reboot/upgrade/rollback. No introduced wakelock or idle workers; target under 3 MiB idle PSS, measure rather than assume.
- Verify /dev/null remains a character device through all lifecycle tests; verify unrelated processes untouched, stale PID/lock fail closed, occupied port fails, key revocation and host key persistence.
- Actual A4 acceptance and independent review required before persistent LAN use or stable release. Maintain evidence by SHA and artifact hash.

## Known limitations and follow-up
First candidate has no live-device validation, no IPv6, no legacy SCP, no remote-forwarding, no password, no isolated non-root account, no persistent watchdog. Boot bind timing, platform env, PID races and actual /proc socket availability require qualification. Status logs contain last transition only; no growing daemon log. Daemon stderr is discarded by default to avoid unbounded logs; detailed foreground diagnostic tooling is still pending. Never start a competing listener. Use dedicated host keys and strict host checking. Host helper explicitly selects context, never retries ambiguous mutations.

## Dependency security and release provenance
2026-11-24: upstream VD v1.11 bundled rsync 3.4.1, which is superseded by security releases. TVD pins rsync 3.5.2 (https://rsync.samba.org/security.html), OpenSSH 10.4p1 (https://www.openssh.org/releasenotes.html), zlib 1.4 (https://zlib.net/) and Dropbear 2026.94 source commit 28216cd9af822732a1549b78621c2ea9a76a0fe5. Verify pinned tarball hashes prior to extraction, record native binary provenance and ship exact rsync corresponding source with release. New dependency versions need native build and device qualification; do not assume old Android compatibility patches still suffice. The stable workflow promotes the exact tested ZIP rather than rebuilding it. Only an explicitly qualified ABI may be promoted. Record hash and source SHA before approval. Candidate version suffix must be removed in a new reviewed source commit before building a stable-version candidate; that candidate must itself be qualified.

## Host tools
From a workstation with Python 3 and explicit authenticated ADB serial / SSH alias:
    python tools/a4ctl.py --context adb-root --serial SERIAL doctor
    python tools/a4ctl.py --context ssh-root --host a4-tv exec "id; getenforce"
    python tools/a4ctl.py --context ssh-root --host a4-tv --timeout 120 sync /vendor/etc/ ./reference/vendor-etc/
    python tools/a4ctl.py --context adb-shell --serial SERIAL install test.apk
    python tools/a4ctl.py --context adb-shell --serial SERIAL screenshot capture.png
    python tools/qualify.py --serial SERIAL --host a4-tv --output evidence.json
The SSH alias must resolve through host SSH configuration, with root login, dedicated key and verified known_hosts. Optionally pin ro.serialno with --expect-serial. No automatic fallback; timeouts mean outcome may be unknown. SSH transfers require modern OpenSSH SCP/SFTP and host rsync (e.g. WSL on Windows). Root ADB context is not a root file transfer transport; use SSH for protected files. Read-only qualification evidence compares contexts, records PSS/process ticks and selected state, and does not perform mutation. Inspect sensitive evidence before publishing.

## Installer details
Magisk v30.7 install_module excludes META-INF from extraction; the internal integrity manifest covers only extracted runtime files. The external ZIP SHA256 covers the installer itself. Magisk's pending module path is modules_update (singular). The installer rejects recovery-mode installation, wrong userspace ABI and active TVD daemon/session processes. Do not bypass checks or install during active playback.

## Agent toolkit
See [host toolkit](TVD-HOST-TOOLS.md) for structured execution, evidence, snapshots and capability tracking. The host retains raw output and only explicitly opted-in previews expose sensitive probes. Redaction is best-effort, not a guarantee. No new resident TV process.
