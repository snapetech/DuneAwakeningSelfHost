# Offline Player Life-State Recovery

DASH can recover an explicitly offline character whose persisted Dune life state is `Dead`, `DeadByCoriolis`, or `DeadBySandworm`. The action uses the current server build's first-party `dune.get_player_pawn(bigint)` and `dune.update_death_location(actordescription, serverinfo, playerlifestate)` functions. It is not a guessed `/heal` or `/revive` command and does not require a map restart.

Confidence: high for the persisted `life_state`/`death_location` transition after the isolated semantic proof has passed; unknown for any unrelated client-side health state because this action deliberately does not modify health.

## Exact scope

Execution changes only the state owned by `dune.update_death_location`:

- `dune.encrypted_player_state.life_state` becomes `Alive`.
- `dune.encrypted_player_state.death_location` becomes `NULL`.

It does not change health, water, inventory, equipment, specialization, faction, position, actor transform, respawn locations, currency, or progression. The player must reconnect so the client loads the recovered persisted state. No farm or map process is restarted.

## Admission contract

Preview is available while execution is disabled. Execution requires all of the following:

- authenticated `players.write` capability;
- `DUNE_ADMIN_MUTATIONS_ENABLED=true`;
- `DUNE_ADMIN_PLAYER_LIFE_RECOVERY_ENABLED=true`;
- an exact current `encrypted_player_state` row and pawn actor;
- `online_status=Offline`;
- `dune.is_player_offline(fls_id)=true`;
- a current life state in the explicit dead-state allowlist;
- both native functions present in the running database;
- the exact preview fingerprint;
- typed confirmation `RECOVER OFFLINE PLAYER LIFE STATE`;
- a current signed blast-radius change contract and any configured second approval.

An account that is already `Alive` is a blocked no-op. An Online, disconnecting, ambiguous, missing-pawn, changed-fingerprint, or unsupported-state target is refused.

## Transaction and evidence sequence

`POST /api/admin/player-recovery/life-state` defaults to `dryRun=true`.

On execution DASH:

1. Rebuilds the preview and validates its SHA-256 fingerprint.
2. Creates a non-empty full PostgreSQL custom-format dump through the normal admin backup path.
3. Writes a private pending receipt under `backups/admin-panel/player-life-recovery/`.
4. Opens a database transaction and takes an account-scoped advisory lock.
5. Row-locks the exact `encrypted_player_state` and pawn actor rows.
6. Rebuilds and rechecks the fingerprint, explicit Offline state, native offline predicate, dead-state allowlist, pawn identity, and function availability under those locks.
7. Calls `dune.get_player_pawn(account_id)` and passes its exact `actordescription` and `serverinfo` composites to `dune.update_death_location(..., 'Alive')`.
8. Reads the saved row back and requires `Alive`, no death location, the same player-state/pawn identities, and continued explicit Offline status before commit.
9. Commits and atomically finalizes a private SHA-256 receipt containing the backup reference and before/after evidence.

Any failed lock recheck, native resolution, or readback rolls the transaction back. A pending receipt intentionally remains if finalization or execution is interrupted, making the unknown outcome visible to operators.

## API examples

Preview:

```json
{
  "dryRun": true,
  "accountId": 123
}
```

Execute only the unchanged preview:

```json
{
  "dryRun": false,
  "accountId": 123,
  "expectedFingerprint": "<64 lowercase hex characters from preview>",
  "confirm": "RECOVER OFFLINE PLAYER LIFE STATE"
}
```

The Admin Actions page supplies these fields and disables its execution button until an executable preview exists and both mutation gates are active.

## Disposable semantic proof

The PostgreSQL restore drill now treats `get_player_pawn` and `update_death_location` as required native functions. After restoring a copied dump in a bounded, non-root, read-only-rootfs, `NetworkMode=none` container, the drill selects one Alive pawn and performs this sequence inside one transaction:

1. call the native function with `Dead` and verify `life_state=Dead` plus a populated death location;
2. call the native function with `Alive` and verify `life_state=Alive` plus a cleared death location;
3. roll the entire transaction back.

The hash-chained restore receipt records `playerLifeRecoveryContract`. Feature readiness stays at `semantic-proof-missing` until a current valid receipt proves both directions and rollback. The drill never connects to or writes the live database.

Run the local unit coverage with:

```bash
make test-player-life-recovery
make test-restore-drill
```

Run the real isolated rehearsal using the normal restore-drill operational path. Do not substitute a transaction on the live database.

## Recovery and rollback

There is no automatic “re-kill” button. Reconstructing a dead state would be semantically unsafe because the prior death composite may bind map/server context. If the committed recovery must be reversed, stop writers through the normal guarded restore workflow and restore the exact full database backup named in the receipt.

The action's normal success path requires only player reconnect. It does not require or perform a map restart.

## Metrics and readiness

The change-intelligence metrics document exports label-free counters and state:

- `dash_player_life_recovery_collector_up`
- `dash_player_life_recovery_enabled`
- `dash_player_life_recovery_ready`
- `dash_player_life_recovery_previews_total`
- `dash_player_life_recovery_executions_total`
- `dash_player_life_recovery_refusals_total`
- `dash_player_life_recovery_errors_total`

The feature-readiness row requires the master and feature gates, both native functions, and a valid current isolated semantic proof. No metric contains account or character labels.
