# Remote SSH Targets and Tunnels

`scripts/remote-targets.py` provides named remote DASH profiles, strict host-key
checking, a loopback-only admin tunnel, hostname verification, and two-phase
Ed25519 key rotation. Copy `config/remote-targets.example.json` to the ignored
`config/remote-targets.json` and use absolute private key/known-hosts paths.

```bash
python3 scripts/remote-targets.py list
python3 scripts/remote-targets.py check standby
python3 scripts/remote-targets.py tunnel standby
```

The tunnel binds only `127.0.0.1`, disables agent/other forwarding, pins the
known-hosts file, and first requires the returned hostname to equal the profile.
It does not expose the admin panel publicly.

Key rotation adds a staged Ed25519 public key through a fixed remote Python
program, verifies a new-key login and hostname, atomically promotes the local
key while retaining a timestamped previous copy, then removes the old remote
key. Remote `authorized_keys` is backed up before both changes. No generic
operator-provided shell string is accepted.

```bash
python3 scripts/remote-targets.py rotate-key standby \
  --confirm 'ROTATE DASH SSH KEY'
```

If the final old-key removal fails, the command reports failure but the verified
new local key remains active and the old remote key remains valid for recovery.
Inspect both sides and retry deliberately. Private receipts under
`backups/remote-access` contain hashes and paths, never private key material.
Revoke a lost key from a trusted console immediately; rotation is not a
substitute for revocation.
