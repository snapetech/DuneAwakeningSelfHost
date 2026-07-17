# Releases and Distribution

Confidence: high that DASH releases are reproducible, commit-bound deployment
packages for Linux x86_64 hosts with AVX2. They are not redistributions of the
official Dune: Awakening server package.

## Release model

DASH uses Semantic Versioning and Git tags. `VERSION` contains the version
without the leading `v`; a release tag must be exactly `v$(cat VERSION)`. A tag
push starts `.github/workflows/release.yml`. The workflow does not wait for a
deployment environment or manual approval. It fails closed unless the tag,
commit, source tree, tests, packages, checksums, and uploaded GitHub asset
digests all agree.

Prereleases such as `v0.1.0-beta.1` are complete packages, but communicate that
the clean-host contract still needs wider third-party operator coverage. Stable
releases omit the prerelease suffix.

The repository has release immutability enabled. The workflow therefore:

1. builds and verifies every asset;
2. creates a draft GitHub Release;
3. uploads every asset;
4. compares GitHub's recorded SHA-256 digest for every uploaded asset;
5. publishes the draft; and
6. verifies that the published release is immutable.

Once published, its tag and assets cannot be moved, replaced, or deleted in the
normal release workflow. GitHub also creates an immutable-release attestation.
The workflow separately uses GitHub's OIDC/Sigstore-backed artifact attestation
service for the built files.

GitHub's per-workflow `GITHUB_TOKEN` cannot read repository administration
settings, including the immutable-release setting. In Actions only, the
publisher accepts that specific 403 response during the preflight check. It
still asserts the published release's `immutable` field and fails the job if
GitHub did not lock the release. Interactive/local publication continues to
require the setting preflight to succeed before a draft is created.

Draft releases are not available through GitHub's release-by-tag API. The
publisher therefore resolves the newly created draft through the repository
release list, requires exactly one numeric release ID for the tag, uses that ID
for remote digest verification and publication, and returns to tag-based lookup
only after the release is public.

## Supported packages

| Asset | Target | Status |
| --- | --- | --- |
| `dash-<tag>-linux-x86_64.tar.gz` | Linux x86_64, AVX2, Docker Compose | Supported server package |
| `dash-<tag>-linux-x86_64.spdx.json` | SPDX 2.3 inventory of the server package | Supported SBOM |
| `dune-linux-server-loader-<tag>-linux-x86_64.tar.gz` | Linux server research loader | Experimental; separately gated |
| `dune-linux-client-loader-<tag>-linux-x86_64.tar.gz` | Native Linux client research loader | Experimental; separately gated |
| `dune-windows-client-loader-<tag>-windows-x86_64.tar.gz` | Windows/Proton client research loader | Experimental; separately gated |

Windows and macOS are supported as operator workstations connected to a Linux
host. They are not native DASH server platforms. ARM64 is not a server target.
Podman remains best-effort.

The main package includes Compose, the Admin dashboard, scripts, docs, Ansible,
Proxmox/cloud-init, Pelican/Pterodactyl, public-site, and active/passive HA
content. It does not include or download Funcom server binaries, Steam package
contents, container images, game assets, credentials, databases, saves,
backups, captures, TLS keys, or logs. An entitled operator obtains the official
Steam package separately and runs `scripts/load-images.sh`.

The package does include the four documented static helper commands used inside
the official containers. Their upstream identities, licenses, hashes, and the
complete corresponding BusyBox source/config/build recipe are under `vendor/`.

## Published asset contract

Every release contains:

- the primary server package and its `.sha256` sidecar;
- SPDX 2.3 SBOM;
- three loader archives, sidecars, and JSON verification receipts;
- `release-manifest.json` with identity, role, size, and digest per asset;
- `release-provenance.intoto.json` using an in-toto Statement and SLSA v1
  predicate;
- `SHA256SUMS` covering every other attached file; and
- `RELEASE_NOTES.md` matching the published release body.

`scripts/build-release.py` reads the exact Git object with `git archive`, adds
commit-bound `RELEASE-METADATA.json`, normalizes archive order, ownership,
permissions, timestamps, and gzip headers, and emits the SPDX document.
Uncommitted files cannot enter the package. `scripts/build-release-assets.sh`
also requires the worktree to be clean.

The installer rejects a release when its outer checksum, archive structure,
embedded commit, version/tag relationship, Linux/x86_64/AVX2 platform contract,
or private/proprietary exclusion declaration does not match.

## Install a published release

```bash
tag=v0.1.0-beta.1
repo=https://github.com/snapetech/DuneAwakeningSelfHost
asset="dash-${tag}-linux-x86_64.tar.gz"

curl -fL "$repo/releases/download/$tag/$asset" -o "/tmp/$asset"
curl -fL "$repo/releases/download/$tag/SHA256SUMS" -o /tmp/SHA256SUMS
(cd /tmp && grep "  $asset\$" SHA256SUMS | sha256sum -c -)

tar -xOf "/tmp/$asset" \
  "dash-${tag}-linux-x86_64/scripts/install-release.sh" \
  > /tmp/dash-install-release.sh
chmod 0755 /tmp/dash-install-release.sh

ref="$(curl -fsSL "https://api.github.com/repos/snapetech/DuneAwakeningSelfHost/git/ref/tags/$tag" |
  jq -r '.object.sha')"
sudo /tmp/dash-install-release.sh install \
  --ref "$ref" \
  --sha256 "$(sha256sum "/tmp/$asset" | awk '{print $1}')" \
  --archive "/tmp/$asset" \
  --activate
```

The first prerelease uses a lightweight tag, so the Git ref SHA is the release
commit. For an annotated tag, dereference it to the commit before passing
`--ref`. Installing or activating a release never starts or restarts the game.

Inspect the result:

```bash
sudo /opt/dash/current/scripts/install-release.sh status
cat /opt/dash/current/.dash-release.json
```

Then create the private `.env`, obtain/load the official Steam images, run the
bootstrap checklist, initialize the database once, and select a map policy.

## Verify authenticity and integrity

With a current GitHub CLI:

```bash
gh release verify v0.1.0-beta.1 \
  --repo snapetech/DuneAwakeningSelfHost

gh release download v0.1.0-beta.1 \
  --repo snapetech/DuneAwakeningSelfHost \
  --pattern 'dash-v0.1.0-beta.1-linux-x86_64.tar.gz'

gh release verify-asset v0.1.0-beta.1 \
  dash-v0.1.0-beta.1-linux-x86_64.tar.gz \
  --repo snapetech/DuneAwakeningSelfHost

gh attestation verify dash-v0.1.0-beta.1-linux-x86_64.tar.gz \
  --repo snapetech/DuneAwakeningSelfHost
```

Offline checksum and structure verification remains available:

```bash
sha256sum -c SHA256SUMS
python3 scripts/finalize-release.py verify \
  --version v0.1.0-beta.1 \
  --ref <full-release-commit> \
  --asset-dir .
```

## Build locally

The complete build installs missing loader compiler packages when supported by
the host package manager:

```bash
make release-package
```

Equivalent explicit command:

```bash
scripts/build-release-assets.sh \
  --version "v$(cat VERSION)" \
  --ref "$(git rev-parse HEAD)"
```

Output is written to ignored `dist/release/`. The build runs the package
verifier and a temporary no-start installation smoke test. Run `make validate`
separately before tagging; the GitHub workflow always does both.

## Cut the next release

1. Update `VERSION` and `CHANGELOG.md`.
2. Add `docs/releases/v<version>.md`.
3. Run `make validate` and `make release-package` from a clean commit.
4. Push that commit to `main` on both remotes.
5. Create and push the exact `v<version>` tag to GitHub.
6. Monitor the `Release` workflow until the immutable release and attestations
   verify.

`scripts/publish-github-release.sh` is the noninteractive draft/upload/digest
verification/publish implementation used by Actions. It refuses an existing
release. Local publication refuses a repository without release immutability;
Actions enforces immutability using the post-publication assertion described
above because its token cannot read repository settings.

## Rollback

Release rollback only swaps the `current` and `previous` symlinks:

```bash
sudo /opt/dash/current/scripts/install-release.sh rollback \
  --confirm 'ROLL BACK DASH RELEASE'
```

It does not restart services. Apply the rollback during a separately scheduled,
guarded restart and retain the normal Coriolis validation requirements.
