# Transactional Client Loader and Pak Deployment

Client deployment is separate from server administration. `scripts/client-deployment.py`
installs reviewed DASH client artifacts into an operator-selected Dune game
directory with an exact confirmation, pre-change backups, checksummed private
manifest, atomic replacement, verification, and drift-safe rollback.

Install and rollback refuse to run while a Dune client process is present.
Close the game before either operation; Steam itself may remain open.

The manager never patches an official Pak in place. Its target allowlist is:

- `DuneSandbox/Binaries/Win64/version.dll`;
- `DuneSandbox/Binaries/Win64/dune-win-client-probe.env`;
- `DuneSandbox/Binaries/Win64/lua54.dll`;
- top-level `DuneSandbox/Content/Paks/zzz_dash_*.pak` and matching `.sig`
  overlays.

Official Pak names such as `Systems.pak`, path traversal, targets outside the
resolved game root, duplicate targets, and overlap with another active managed
deployment are rejected. Whether an unsigned overlay Pak is accepted by a
particular Dune client build remains a live-runtime question; deployment alone
does not prove that the game mounted it.

## Build and stage artifacts outside Steam

Build and test the Windows/Proton loader first:

```bash
make build-windows-client-loader
make smoke-windows-client-loader-full
scripts/launch-proton-client-probe.sh --stage-dir build/windows-client-loader/proton-stage
```

That last command generates the proxy DLL and sidecar under `build/`; it does
not require client-directory staging. Review their checksums before continuing.

## Plan without mutation

```bash
game=/absolute/path/to/steamapps/common/DuneAwakening
scripts/client-deployment.py plan \
  --game-dir "$game" \
  --deployment current-loader-canary \
  --file "build/windows-client-loader/dune_win_client_probe_loader.dll::DuneSandbox/Binaries/Win64/version.dll" \
  --file "build/windows-client-loader/proton-stage/dune-win-client-probe.env::DuneSandbox/Binaries/Win64/dune-win-client-probe.env"
```

The plan hashes the shipping executable, sources, and current targets. It
creates no state directory and writes no client file.

## Install, verify, and roll back

After recording the target paths and independently reviewing the plan:

```bash
scripts/client-deployment.py install \
  --game-dir "$game" \
  --deployment current-loader-canary \
  --file "build/windows-client-loader/dune_win_client_probe_loader.dll::DuneSandbox/Binaries/Win64/version.dll" \
  --file "build/windows-client-loader/proton-stage/dune-win-client-probe.env::DuneSandbox/Binaries/Win64/dune-win-client-probe.env" \
  --confirm 'MUTATE DUNE CLIENT FILES'

scripts/client-deployment.py verify --deployment current-loader-canary

scripts/client-deployment.py rollback \
  --deployment current-loader-canary \
  --confirm 'MUTATE DUNE CLIENT FILES'
```

State defaults to `backups/client-deployments/<deployment>/manifest.json` and
mode-`0600` backup files. Supply `--state-root` before the subcommand to keep it
elsewhere. The state root must be outside the game directory.

Rollback first requires every installed file to match its recorded checksum.
If Steam, another mod manager, or a manual edit changed a target, rollback
fails without overwriting that foreign change. A changed shipping-executable
checksum also blocks verification and rollback so an original DLL from an
older game build cannot be restored into an updated client. A target that
existed before installation is restored from its verified backup; a newly
introduced overlay is removed.

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
the already-installed hashes, and performs no client write. `verify` and
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
finish the UE4SS port by itself. A current-build canary still has to prove, in
order:

1. target-image `FNamePool`, `GUObjectArray`, `GWorld`/`GEngine`, dispatch, and
   package-loading anchors;
2. read-only FName/object/reflection layout validation;
3. guarded hook install/restore before persistent hooks;
4. live ProcessEvent and CallFunction runtime contexts;
5. package-backed `LoadAsset`, `LoadClass`, and `StaticConstructObject` native
   invocation; and
6. real Lua callback routing and typed parameter access.

Use `scripts/prepare-ue-anchor-canary.py`, `scripts/plan-ue4ss-canary-env.py`,
and `scripts/verify-client-probe-canary.sh` for that staged evidence pipeline.
Every escalation remains build-hash-bound; an update to the shipping executable
invalidates the prior plan until signatures and anchors are revalidated.
