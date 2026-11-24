# TVD Dropbear

Headless, key-only SSH engineering transport for rooted Android TV. Fork of [VD Dropbear](https://github.com/VD171/VD-dropbear) by VD171, Apache-2.0. Primary target Toshiba/Hisense A4, Android 9/API 28, ARM userspace. **Testing only; physical qualification pending.**

Retains authenticated ADB. One native listener when enabled; no updater, WebUI, password authentication, watchdog or default LAN exposure. SFTP (including modern SCP) and rsync are on demand. Root-only login: every enrolled key is full administrative access, not a sandbox. No private keys on TV. Do not expose to the public Internet.

Read [engineering and deployment guide](docs/TVD-ENGINEERING.md) before use. Build/testing artefacts from Actions; stable releases require actual device acceptance. Upstream documentation retained as historical reference, not instructions for this fork. [Licence](LICENSE) and [third-party notices](THIRD-PARTY-NOTICES.md).
