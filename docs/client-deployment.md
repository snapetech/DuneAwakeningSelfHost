# Transactional Client Loader and Pak Deployment

Client deployment is separate from server administration. `scripts/client-deployment.py`
installs reviewed DASH client artifacts into an operator-selected Dune game
directory with an exact confirmation, a cryptographically bound reviewed plan,
pre-change backups, a checksummed private manifest, atomic replacement,
verification, and drift-safe rollback.

Install, legacy adoption, and rollback refuse to run while a Dune client
process is present. Close the game before any of those operations; Steam itself
may remain open.

The manager never patches an official Pak in place. Its target allowlist is:

- `DuneSandbox/Binaries/Win64/version.dll`;
- `DuneSandbox/Binaries/Win64/dune-win-client-probe.env`;
- `DuneSandbox/Binaries/Win64/lua54.dll`;
- top-level `DuneSandbox/Content/Paks/zzz_dash_*.pak` and matching `.sig`
  overlays.

Official Pak names such as `Systems.pak`, path traversal, targets outside the
resolved game root, target directories or internal symlinks, duplicate targets,
and overlap with another active managed deployment are rejected. Whether an
unsigned overlay Pak is accepted by a particular Dune client build remains a
live-runtime question; deployment alone does not prove that the game mounted
it.

## Build and stage artifacts outside Steam

Build and test the Windows/Proton loader first:

```bash
make build-windows-client-loader
make smoke-windows-client-loader-full
scripts/launch-proton-client-probe.sh --stage-dir build/windows-client-loader/proton-stage
```

That last command generates the proxy DLL and sidecar under `build/`; it does
not require client-directory staging. Review their checksums before continuing.

The packaged Windows loader is self-contained: it includes
`scripts/client-deployment.py`, this runbook, the deployment tests, the current
build-bound canary record, complete `SHA256SUMS`, and package-verification
receipts. Verify a downloaded archive before extraction, then verify every
extracted file and rerun the packaged contract:

```bash
sha256sum -c dune-windows-client-loader-<version>-windows-x86_64.tar.gz.sha256
tar -xzf dune-windows-client-loader-<version>-windows-x86_64.tar.gz
cd dune-windows-client-loader-<version>-windows-x86_64
sha256sum -c SHA256SUMS
analysis/verify-loader-artifacts.py \
  --target windows-client \
  --package-root . \
  --package-target windows-client \
  --package-archive ../dune-windows-client-loader-<version>-windows-x86_64.tar.gz \
  --package-archive-sha256 ../dune-windows-client-loader-<version>-windows-x86_64.tar.gz.sha256 \
  --package-only
python3 -m unittest tests/test-client-deployment.py
```

`client-deployment-test.txt` is the build-time receipt from that same packaged
test suite; `loader-artifact-verification.json` is the staged-tree contract
receipt. The archive is accompanied by `.verification.txt` and
`.verification.json` receipts covering the staged root, outer digest, and safe
tar layout. The expanded verifier command above reproduces those checks.

The verifier rejects incomplete checksums, checksum drift, package symlinks,
and unsafe archive members such as traversal paths, links, devices, or multiple
top-level roots.

## Create and review an install receipt without mutation

```bash
game=/absolute/path/to/steamapps/common/DuneAwakening
receipt=build/windows-client-loader/current-loader-canary.plan.json
scripts/client-deployment.py plan \
  --game-dir "$game" \
  --deployment current-loader-canary \
  --file "build/windows-client-loader/dune_win_client_probe_loader.dll::DuneSandbox/Binaries/Win64/version.dll" \
  --file "build/windows-client-loader/proton-stage/dune-win-client-probe.env::DuneSandbox/Binaries/Win64/dune-win-client-probe.env" \
  > "$receipt"

python3 -m json.tool "$receipt"
```

The plan hashes the shipping executable, sources, and current targets. It
creates no state directory and writes no client file. Its `planSha256` binds
the deployment ID, game and state roots, executable build, source paths and
bytes, target paths and current bytes, and active collision result. Keep the
reviewed JSON as the install receipt.

## Install, verify, and roll back

After recording the target paths and independently reviewing the plan:

```bash
scripts/client-deployment.py install \
  --reviewed-plan "$receipt" \
  --confirm 'MUTATE DUNE CLIENT FILES'

scripts/client-deployment.py verify --deployment current-loader-canary

scripts/client-deployment.py audit

scripts/client-deployment.py rollback \
  --deployment current-loader-canary \
  --confirm 'MUTATE DUNE CLIENT FILES'
```

State defaults to `backups/client-deployments/<deployment>/manifest.json` and
mode-`0600` backup files. Supply `--state-root` before the subcommand to keep it
elsewhere. The state root must be outside the game directory.

Install verifies the receipt checksum, acquires the state lock, and recomputes
the complete plan. A changed executable, source, target, collision set, path,
or modified receipt aborts before client mutation. For automation that already
retains plan JSON elsewhere, the equivalent explicit form is `install` with
the original `--game-dir`, `--deployment`, and `--file` arguments plus
`--expect-plan-sha256 <planSha256>`.

`verify` checks the executable, every installed target, and every rollback
backup; `backupSetHealthy` must remain true. Rollback preflights the entire
backup set before restoring or removing any target, then requires every
installed file to match its recorded checksum.
If Steam, another mod manager, or a manual edit changed a target, rollback
fails without overwriting that foreign change. A changed shipping-executable
checksum also blocks verification and rollback so an original DLL from an
older game build cannot be restored into an updated client. A target that
existed before installation is restored from its verified backup; a newly
introduced overlay is removed.

Manifest structure, deployment identity, hashes, confined target paths, and
backup paths are validated before use. Corrupt active state fails closed
instead of being ignored during collision checks. `status` marks an interrupted
`prepared` deployment or the exceptional `failed-rollback-required` state with
`requiresAttention: true`; do not remove that private state until its manifest
and target checksums have been reviewed.

If a power loss interrupts installation after the durable `prepared` manifest,
or a filesystem error interrupts rollback after some targets were restored,
the same guarded `rollback` command is intentionally retryable. From
`prepared` or `failed-rollback-required`, it accepts only the recorded installed
or original checksum for each target, revalidates the game build and every
backup, then converges the complete set to the original state. Any third-party
value still fails closed.

`audit` is the read-only whole-state health check. It reports the running-client
state, private-root/manifest/backup permissions, corrupt manifests, orphan
files/directories or symlinks, duplicate active target ownership, executable
drift, installed-file drift, backup health, and an action for every issue. It
exits `0` only when the entire state root is healthy, or `1` with a structured
report when operator attention is required:

```bash
scripts/client-deployment.py audit | python3 -m json.tool
```

Run it before and after install/adopt/rollback automation. A running client is
reported but does not make this read-only audit fail; mutation commands still
refuse to proceed while the client is present.

## Adopt an older staged loader before replacing it

Older revisions of `launch-proton-client-probe.sh` recorded the installed DLL
and sidecar hashes but did not record the path of the original DLL backup. Do
not install a new managed loader over that state: doing so would treat the old
probe as the original file. First inspect the legacy manifest, prove the
current target hashes still match it, and identify the exact pre-probe backup.
Then adopt that existing state without changing the client:

```bash
scripts/client-deployment.py adopt \
  --game-dir "$game" \
  --deployment legacy-probe \
  --installed "DuneSandbox/Binaries/Win64/version.dll::/absolute/path/to/verified-original-version.dll" \
  --installed "DuneSandbox/Binaries/Win64/dune-win-client-probe.env::ABSENT" \
  --confirm 'ADOPT EXISTING DUNE CLIENT FILES'
```

Adoption copies the selected original into private deployment state, records
the already-installed hashes, and performs no client write. Target and original
backup hashes are revalidated under the deployment lock, and incomplete
adoption preparation is removed rather than left as orphan state. `verify` and
`rollback` then use the normal guarded lifecycle. If more than one possible
original exists, stop and compare file provenance instead of choosing by
timestamp. A legacy `version.dll` backup that contains
`DUNE_WIN_CLIENT_PROBE_*` strings is another injected probe, not an original
game file. Do not restore it as the original. Use `ABSENT` only when staging
history or a clean Steam file inventory establishes that the target did not
exist before the first proxy install. The current depot manifest IDs are listed
under `InstalledDepots` in Steam's `appmanifest_1172710.acf`; inspect every
corresponding local `depotcache/<depot>_<manifest>.manifest`, including DLC
depots, before making that claim.

## Live canary boundary

The current loaders already implement the proxy, Lua runtime, mod lifecycle,
runtime scans, signature/anchor validation, bounded object/reflection probes,
guarded hook stages, and post-canary readiness reports. Deployment does not
finish the UE4SS port by itself. For build `24146567`, the canary sequence is:

1. **Partial:** target-image `FNamePool` and `GUObjectArray` are proven;
   `GWorld`/`GEngine`, dispatch, and package-loading anchors remain open.
2. **Partial:** sampled FName/object/reflection layouts are proven; broader
   class mapping remains open.
3. **Open:** guarded hook install/restore before persistent hooks.
4. **Open:** live ProcessEvent and CallFunction runtime contexts.
5. **Open:** package-backed `LoadAsset`, `LoadClass`, and
   `StaticConstructObject` native invocation.
6. **Open:** real Lua callback routing and typed parameter access.

Use `scripts/prepare-ue-anchor-canary.py`, `scripts/plan-ue4ss-canary-env.py`,
and `scripts/verify-client-probe-canary.sh` for that staged evidence pipeline.
Every escalation remains build-hash-bound; an update to the shipping executable
invalidates the prior plan until signatures and anchors are revalidated.

The authorized July 2026 read-only canary evidence and current boundary are in
[`windows-client-loader-canary-2026-07-15.md`](windows-client-loader-canary-2026-07-15.md).
