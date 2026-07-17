# Vendored Static Tools

The official Funcom containers do not consistently contain the small command
line tools required by DASH startup, recovery, and diagnostics. DASH mounts
these x86_64 static binaries read-only and copies one only when the target image
does not already provide that command.

They are third-party components, not covered by the repository's MIT license.
Their notices are under `vendor/licenses/` and summarized in
`THIRD_PARTY_NOTICES.md`.

| File | Version and upstream artifact | SHA-256 |
| --- | --- | --- |
| `bin/busybox` | Locally built BusyBox 1.36.1 from the accompanied source/config | `7c9813085183b8ecd78da3847ae3b5b4c9cc0f6232c6770a36afb0f861c8fe7d` |
| `bin/curl` | [`moparisthebest/static-curl` v8.17.0 `curl-amd64`](https://github.com/moparisthebest/static-curl/releases/tag/v8.17.0) | `b01914a4cbd8497d8550010c2d27d2030614d532aaca60e89a3929a734c451b5` |
| `bin/jq` | [`jqlang/jq` jq-1.7.1 `jq-linux-amd64`](https://github.com/jqlang/jq/releases/tag/jq-1.7.1) | `5942c9b0934e510ee61eb3e30273f1b3fe2590df93933a93d7c58b81d19c8ff5` |
| `bin/rg` | [`BurntSushi/ripgrep` 15.1.0 x86_64 musl archive](https://github.com/BurntSushi/ripgrep/releases/tag/15.1.0) | `ebeaf56f8a25e102e9419933423738b3a2a613a444fd749d695e15eba53f71f2` |

The curl build reports curl/libcurl 8.17.0, OpenSSL 3.5.4, zlib 1.3.1,
libssh2 1.11.1, nghttp2 1.65.0, and musl. The applicable license texts are
included. Its upstream release records the same SHA-256 digest as the vendored
file.

## BusyBox corresponding source

BusyBox is GPL-2.0-only. Its complete upstream source archive, exact build
configuration, license, and build script accompany the binary:

```text
source/busybox-1.36.1.tar.bz2
source/busybox-1.36.1.config
licenses/BUSYBOX-GPL-2.0.txt
build-busybox.sh
```

The source archive SHA-256 is
`b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314`.
The build configuration enables a static x86_64 binary and disables the `tc`
applet, which no longer compiles against current Linux UAPI headers. Rebuild to
a temporary path without changing the tracked binary:

```bash
vendor/build-busybox.sh --output /tmp/dash-busybox
/tmp/dash-busybox --help
```

Compiler and libc versions can change the rebuilt bytes. The accompanied source
and configuration are the corresponding source/build inputs for the distributed
binary; the tracked SHA-256 identifies the exact distributed executable.
