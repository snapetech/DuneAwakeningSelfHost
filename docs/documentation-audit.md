# Documentation Audit

Last audited: 2026-05-19.

This page records documentation coverage gaps found during repo review and the current status of each.

## Fixed In This Audit

| Area | Gap | Status |
| --- | --- | --- |
| Character transfers | `docs/access-control.md` said no native restriction knob had been found, but Director exposes character-transfer policy settings. | Fixed with `docs/character-transfers.md` and updated access-control notes. |
| Quick-start commands | Some examples called helper scripts without an env file while nearby commands used `--env-file .env`. | Standardized common setup/troubleshooting examples to pass `.env`. |
| Teardown notes | `docs/teardown.md` still described reproduced Compose pieces as missing. | Reworded as Compose parity notes and kept only current caveats. |
| Admin panel | Character-transfer settings were exposed in the UI but only lightly documented. | `docs/admin-panel.md` now calls out Director restart/recreate requirements, and `docs/character-transfers.md` has the setting table. |
| Reproducible installs | Fresh-host setup, state migration, publishable placeholders, and version drift were spread across README/setup/operations. | Added `docs/reproducibility.md` and linked it from README and setup. |
| Kubernetes migration | The repo referenced the official Kubernetes-oriented package but did not map Compose services back to a real cluster deployment. | Added `docs/kubernetes.md` as an unsupported design map and gap list. |
| Architecture/routing | Architecture and routing docs only described the base nine maps even though the 30-partition warm pool exists. | Updated `docs/architecture.md` and `docs/routing-investigation.md` to distinguish base-farm registration from 30-partition warm-pool registration. |
| Improvement plan | Roadmap text still described only the isolated `survival` launch as current work. | Updated `docs/improvements.md` with warm-pool, admin map health, transfer-policy, and live-validation boundaries. |
| README docs index | README had a flat file list and did not cover every markdown document or root research index. | Replaced it with grouped documentation, research-index, and key-file sections. |
| Discovery burn-down | Build drift, manual knob discovery, thin fixtures, and browser-ping diagnostics were spread across research notes and operator context. | Added `docs/discovery-burndown-plan.md` and implemented build-scoped discovery, fixture coverage, experiment harnessing, RMQ/build diffs, admin Discovery, and non-disruptive ping diagnosis. |
| Admin progression mutations | Recipe unlock documentation still said writes were intentionally absent after guarded Intel, recipe, and research actions had been implemented. | Documented the live API/UI contract, compare-and-swap verification, private receipts, and receipt-bound rollback in `docs/player-progression-receipts.md`. |
| Privileged change approval | Named RBAC identities existed, but no documented mechanism required an independent reviewer for a specific high-impact request. | Added `docs/change-approvals.md` covering cumulative policy levels, exact-body HMAC binding, redacted review, state/event integrity, single-use execution, recovery, metrics, and validation. |
| Primary admin audit integrity | Rotated JSONL events were readable and fed optional Change Intelligence, but their own payload/order/tail integrity and mutation-admission coverage were not independently provable. | Added `docs/audit-ledger.md` and a default-on mutation flight recorder with full-chain HMAC verification, authenticated head, fail-closed admission, correlated completion, UI, metrics, alerts, tests, and recovery. |
| Mutation blast-radius review | Confirmation phrases and optional dual control proved intent/approval but did not present or bind machine-readable backup, reversibility, restart, player, and map impact immediately before execution. | Added `docs/change-contracts.md` and a default-on exact-body signed review/admission gate with current-policy invalidation, browser/API workflows, audit correlation, metrics, and focused fault tests. |

## Remaining Gaps

| Area | Gap | Next Action |
| --- | --- | --- |
| Live client validation | `docs/validation.md` is still a checklist with `TODO` route rows. | Fill each row after live-client testing and link failed-transition capture directories. |
| Route behavior | Deep Desert, Arrakeen, Harko Village, and testing-station travel remain documented as investigation surfaces. | Keep `docs/routing-investigation.md` current with exact client symptoms and first failing service boundary. |
| Image/version drift | README and teardown pin observations to image tag `1963158-0-shipping`. | Re-run `scripts/inspect-images.sh`, `scripts/discover-player-state.sh`, and validation after every Steam tool update. |
| Discovery automation | Surface discovery now has repo-side automation; remaining proof requires external/client runs. | Run browser-probe capture and client-driven fixtures, then promote only validated surfaces from the JSONL ledger. |
| Kubernetes manifests | The Kubernetes doc is currently design documentation only. | Add generated manifests or a Helm chart only after the Compose topology is stable enough to avoid duplicating service definitions by hand. |
| Public networking | Generic networking docs now cover gameplay UDP, optional paired IGW UDP, RMQ TCP, and backup-before-change guidance for router NAT/hairpin rules. | Keep deployment-specific IPs and router rule dumps in private operator backups, not public docs. |
| Admin panel network probes | The panel exposes local/upstream health probes, but no real-outage examples are recorded. | Add examples once probe output has been observed during a real outage. |
| Research docs location | `SERVER_CONFIG_KEYS.md`, `SERVER_CONFIG_KEY_INDEX.md`, `SERVER_BINARY_CONFIG_CANDIDATES.md`, and `DEEP_DESERT_EVENT_KNOBS.md` live at repo root because they are generated/research-heavy. | Move them under `docs/` later if they become stable operator docs rather than research indexes. |

## Audit Checklist

Run this when changing orchestration, config defaults, or admin-panel behavior:

```bash
rg -n "TODO|missing|blocker|not implemented|No native|still need|Current service-layer blockers" README.md docs
rg -n "IncomingCharacterTransfers|DUNE_SERVER_LOGIN_PASSWORD|compose.allmaps|7777-7806|admin-panel" README.md docs config admin
find docs -maxdepth 1 -type f -name '*.md' | sort
docker compose --env-file .env.example config --quiet
make validate
```

For docs that mention shipped Funcom behavior, include the image tag and date when possible.
