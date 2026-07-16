# Reproducible Loader Packages

The Linux server, Linux client, and Windows client loader packagers emit
deterministic archives and a machine-readable provenance manifest. This makes
an archive digest useful as a release identity instead of merely a transport
checksum.

## Build Contract

For identical source content, explicit version, toolchain, build type,
platform, and `SOURCE_DATE_EPOCH`, repeated builds produce byte-identical
`.tar.gz` archives. The packagers normalize:

- archive member order;
- member timestamps to `SOURCE_DATE_EPOCH`;
- numeric ownership to UID/GID `0`;
- gzip headers without an original filename or wall-clock timestamp;
- generated README build time;
- ABI `file` output so it does not contain the caller's absolute build path;
- packaged test receipts so test duration is not release data; and
- Python test execution so `__pycache__` bytecode is not staged.

The default epoch is the source commit timestamp. Override it when rebuilding
an older release or when a release pipeline supplies a canonical epoch:

```bash
SOURCE_DATE_EPOCH=1700000000 \
  DUNE_WINDOWS_CLIENT_LOADER_VERSION=release-1 \
  scripts/package-windows-client-loader.sh
```

The equivalent version variables are
`DUNE_LINUX_CLIENT_LOADER_VERSION` and
`DUNE_LINUX_SERVER_LOADER_VERSION`.

Reproducibility does not make different compilers, linkers, dependency
versions, target platforms, or build flags equivalent. Pin those inputs in the
release environment. A dirty worktree is recorded honestly and gets a
`-dirty` suffix in the default version, but it cannot be reconstructed from the
recorded commit alone. The dirty check includes staged, unstaged, and untracked
files.

## Provenance Manifest

Every package root contains `package-provenance.json` with schema
`dune-loader-package-provenance/v1`. It records:

- package name, target, version, and platform;
- normalized `builtUtc` and numeric `sourceDateEpoch`;
- source commit, source tree, and dirty state;
- build type; and
- packaged loader path, byte size, and SHA-256 digest.

`scripts/verify-loader-artifacts.py` rejects a missing or malformed manifest,
a target/platform mismatch, an inconsistent epoch, or a loader digest/size
mismatch. The manifest itself is covered by the package's `SHA256SUMS`.

## Verification

Each package run verifies its staged root, archive member safety, complete
internal checksum coverage, and the portable outer `.sha256` sidecar. It emits
human-readable and JSON verification receipts next to the archive.

Verify the outer archive after transfer:

```bash
cd dist/windows-client-loader
sha256sum -c dune-windows-client-loader-<version>-windows-x86_64.tar.gz.sha256
```

Verify an extracted package independently:

```bash
scripts/verify-loader-artifacts.py \
  --package-only \
  --package-target windows-client \
  --package-root /path/to/dune-windows-client-loader-<version>-windows-x86_64
```

Use `linux-client` or `linux-server` for the other package targets.

## Regression Coverage

`make test-loader-package-reproducibility` verifies that all three packagers
use the shared normalization helpers, changes staged file mtimes and proves the
archives remain byte-identical, checks provenance determinism and loader
binding, and confirms that untracked files mark source state dirty. The normal
`make validate` path includes this suite.
