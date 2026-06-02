COMPOSE ?= docker compose
ENV_FILE ?= .env.example

.PHONY: validate compose-config check-compose-static-ips validate-research-build-tags secret-scan test-watch-maps test-admin-panel-safe-surfaces test-character-slot-tool test-research-catalog test-discovery-tools test-admin-chat test-admin-grant-item test-operational-borrowing test-artificial-exchange test-artificial-exchange-service artificial-exchange-smoke artificial-exchange-bootstrap-catalog artificial-exchange-research-prices test-vehicle-fidelity-investigation gm-catalog gm-probe-preview gm-probe-safe research-catalog research-catalog-markdown surface-ledger surface-ledger-markdown discovery-queue binary-candidate-scores asset-reference-graph extract-build-surfaces diff-build-surfaces db-function-classifier fixture-runner knob-experiment capture-rmq-window diff-rmq-captures list-publishable preflight operational-identity-check operational-report operational-bundle verify-operational-bundle status standby-status failover-topology-status failover-bidirectional-audit sync-standby-files sync-standby-images promote-standby postgres-failover-seal postgres-cutback-proof rebuild-postgres-standby set-active-gameserver handoff-ready handoff-experiment summarize-handoff handoff-lab-config handoff-lab-up handoff-lab-seed handoff-lab-status handoff-lab-stop handoff-lab-remote-up handoff-lab-remote-status handoff-lab-remote-stop handoff-lab brt-dd-lab-config brt-dd-lab-images brt-dd-lab-up brt-dd-lab-seed brt-dd-lab-status brt-dd-lab-verify-config brt-dd-lab-logs brt-dd-lab-stop brt-dd-next-downtime-stage brt-dd-next-downtime-status brt-dd-live-preflight brt-dd-live-restart brt-dd-live-verify brt-dd-live-logs brt-dd-live-checklist failover-orchestrate failover-role-services cutover-check cutover-network-status browser-ping-diagnostics watch-browser-probe host-network-failover router-cutover install-dune-status-service check-steam-update backup-dry-run backup-state restore-dry-run verify-backup start-full-warm-pool recover-survival recover-map watch-maps watch-maps-status install-map-watchdog-service install-artificial-exchange-service install-artificial-exchange-buyer-service install-artificial-exchange-populator-service install-full-farm-service install-daily-maintenance-timer full-world-partitions update-hagga-pois public-site-check public-site-package public-site-deploy public-site-verify admin-panel-deploy admin-panel-verify verify-local-state-ignored rabbitmq-cert-check rabbitmq-cert-generate rabbitmq-cert-stage rabbitmq-cert-install-staged rabbitmq-cert-recreate-stack

validate: compose-config check-compose-static-ips validate-research-build-tags surface-ledger secret-scan test-watch-maps test-admin-panel-safe-surfaces test-character-slot-tool test-research-catalog test-discovery-tools test-admin-chat test-admin-grant-item test-smugglers-run-mp test-operational-borrowing test-artificial-exchange test-artificial-exchange-service test-vehicle-fidelity-investigation public-site-check verify-local-state-ignored

validate-research-build-tags:
	./scripts/validate-research-build-tags.sh $(ENV_FILE)

preflight:
	./scripts/preflight.sh

operational-identity-check:
	./scripts/check-operational-identity.sh $(ENV_FILE)

operational-report:
	./scripts/operational-report.sh $(ENV_FILE) $(REPORT_FILE)

operational-bundle:
	./scripts/operational-bundle.sh $(ENV_FILE) $(BUNDLE_FILE)

verify-operational-bundle:
	@if [ -z "$(BUNDLE_FILE)" ]; then \
		echo "Usage: make verify-operational-bundle BUNDLE_FILE=backups/operational-bundle-<id>.tgz"; \
		exit 2; \
	fi
	./scripts/verify-operational-bundle.sh $(BUNDLE_FILE)

rabbitmq-cert-check:
	./scripts/check-rabbitmq-cert-sans.sh $(ENV_FILE)

rabbitmq-cert-generate:
	./scripts/generate-rabbitmq-cert.sh $(ENV_FILE)

rabbitmq-cert-stage:
	./scripts/stage-rabbitmq-cert.sh $(ENV_FILE)

rabbitmq-cert-install-staged:
	./scripts/install-staged-rabbitmq-cert.sh $(ENV_FILE) $(REMOTE)

rabbitmq-cert-recreate-stack:
	./scripts/recreate-rabbitmq-tls-stack.sh $(ENV_FILE)

status:
	./scripts/status.sh $(ENV_FILE)

standby-status:
	./scripts/standby-status.sh $(ENV_FILE) $(REMOTE) $(ROOT)

failover-topology-status:
	./scripts/failover-topology-status.sh $(ENV_FILE)

failover-bidirectional-audit:
	./scripts/failover-bidirectional-audit.sh $(ENV_FILE)

sync-standby-files:
	./scripts/sync-standby-files.sh $(ENV_FILE) $(REMOTE)

sync-standby-images:
	./scripts/sync-standby-images.sh $(ENV_FILE) $(REMOTE)

promote-standby:
	./scripts/promote-standby.sh $(ENV_FILE) $(REMOTE)

postgres-failover-seal:
	./scripts/postgres-failover-seal.sh $(ENV_FILE) $(REMOTE) $(SEAL_FILE)

postgres-cutback-proof:
	./scripts/postgres-cutback-proof.sh $(ENV_FILE) $(TARGET) $(ROOT) $(SEAL_FILE)

rebuild-postgres-standby:
	./scripts/rebuild-postgres-standby.sh $(ENV_FILE) $(TARGET) $(ROOT)

set-active-gameserver:
	./scripts/set-active-gameserver.sh $(ENV_FILE) $(ACTIVE_HOST) $(ACTIVE_IP) $(STANDBY_HOST) $(STANDBY_IP) $(APPLY)

handoff-ready:
	./scripts/handoff-ready.sh $(ENV_FILE) $(ROLE)

handoff-experiment:
	./scripts/handoff-experiment.sh $(ENV_FILE) $(ROLE) $(APPLY)

summarize-handoff:
	./scripts/summarize-handoff-experiment.sh $(CAPTURE_DIR)

handoff-lab-config:
	./scripts/handoff-lab.sh config $(ENV_FILE)

handoff-lab-up:
	./scripts/handoff-lab.sh up $(ENV_FILE)

handoff-lab-seed:
	./scripts/handoff-lab.sh seed $(ENV_FILE)

handoff-lab-status:
	./scripts/handoff-lab.sh status $(ENV_FILE)

handoff-lab-settled-status:
	./scripts/handoff-lab.sh settled-status $(ENV_FILE)

handoff-lab-stop:
	./scripts/handoff-lab.sh stop $(ENV_FILE)

handoff-lab-remote-up:
	./scripts/handoff-lab.sh remote-up $(ENV_FILE) $(REMOTE)

handoff-lab-remote-status:
	./scripts/handoff-lab.sh remote-status $(ENV_FILE) $(REMOTE)

handoff-lab-remote-settled-status:
	./scripts/handoff-lab.sh remote-settled-status $(ENV_FILE) $(REMOTE)

handoff-lab-remote-stop:
	./scripts/handoff-lab.sh remote-stop $(ENV_FILE) $(REMOTE)

handoff-lab:
	./scripts/handoff-lab.sh handoff $(ENV_FILE) $(SRC) $(DST)

brt-dd-lab-config:
	./scripts/brt-dd-lab.sh config $(ENV_FILE)

brt-dd-lab-images:
	./scripts/brt-dd-lab.sh images $(ENV_FILE)

brt-dd-lab-up:
	./scripts/brt-dd-lab.sh up $(ENV_FILE)

brt-dd-lab-seed:
	./scripts/brt-dd-lab.sh seed $(ENV_FILE)

brt-dd-lab-status:
	./scripts/brt-dd-lab.sh status $(ENV_FILE)

brt-dd-lab-verify-config:
	./scripts/brt-dd-lab.sh verify-config $(ENV_FILE)

brt-dd-lab-logs:
	./scripts/brt-dd-lab.sh logs $(ENV_FILE)

brt-dd-lab-stop:
	./scripts/brt-dd-lab.sh stop $(ENV_FILE)

brt-dd-next-downtime-stage:
	./scripts/brt-dd-next-downtime.sh stage $(ENV_FILE)

brt-dd-next-downtime-status:
	./scripts/brt-dd-next-downtime.sh status $(ENV_FILE)

brt-dd-live-preflight:
	./scripts/brt-dd-live-readiness.sh preflight $(ENV_FILE)

brt-dd-live-restart:
	./scripts/brt-dd-live-readiness.sh restart-deep-desert $(ENV_FILE) "$(CONFIRM)"

brt-dd-live-verify:
	./scripts/brt-dd-live-readiness.sh verify-after-restart $(ENV_FILE)

brt-dd-live-logs:
	./scripts/brt-dd-live-readiness.sh logs $(ENV_FILE)

brt-dd-live-checklist:
	./scripts/brt-dd-live-readiness.sh checklist $(ENV_FILE)

failover-orchestrate:
	./scripts/failover-orchestrate.sh $(ENV_FILE) $(ROLE) $(APPLY)

failover-role-services:
	./scripts/failover-role-services.sh $(ENV_FILE) $(ROLE) $(REMOTE)

cutover-check:
	./scripts/cutover-check.sh $(ENV_FILE)

cutover-network-status:
	./scripts/cutover-network-status.sh $(ENV_FILE) $(ROUTER) $(REMOTE)

browser-ping-diagnostics:
	./scripts/browser-ping-diagnostics.sh $(ENV_FILE)

watch-browser-probe:
	./scripts/watch-browser-probe.sh $(ENV_FILE) $(SECONDS)

host-network-failover:
	REMOTE="$(REMOTE)" ROLE="$(ROLE)" ./scripts/host-network-failover.sh $(ENV_FILE)

router-cutover:
	./scripts/router-cutover-asuswrt.sh $(ENV_FILE) $(ROUTER) $(TARGET)

install-dune-status-service:
	./scripts/install-dune-status-service.sh $(ENV_FILE)

check-steam-update:
	./scripts/check-steam-update.sh $(ENV_FILE)

backup-dry-run:
	./scripts/backup-state.sh --dry-run $(ENV_FILE)

backup-state:
	./scripts/backup-state.sh $(ENV_FILE)

restore-dry-run:
	@if [ -z "$(BACKUP_DIR)" ]; then \
		echo "Usage: make restore-dry-run ENV_FILE=.env BACKUP_DIR=backups/<id> RESTORE_FLAGS='--rabbitmq --server-saved --config --tls'"; \
		exit 2; \
	fi
	./scripts/restore-state.sh --dry-run $(RESTORE_FLAGS) $(ENV_FILE) $(BACKUP_DIR)

verify-backup:
	@if [ -z "$(BACKUP_DIR)" ]; then \
		echo "Usage: make verify-backup BACKUP_DIR=backups/<id>"; \
		exit 2; \
	fi
	./scripts/verify-backup.sh $(BACKUP_DIR)

start-full-warm-pool:
	./scripts/start-full-warm-pool.sh $(ENV_FILE)

recover-survival:
	./scripts/recover-survival.sh $(ENV_FILE)

recover-map:
	@if [ -z "$(SERVICE)" ] || [ -z "$(PARTITION_ID)" ]; then \
		echo "Usage: make recover-map ENV_FILE=.env SERVICE=heighliner-dungeon PARTITION_ID=18"; \
		exit 2; \
	fi
	./scripts/recover-map.sh $(ENV_FILE) $(SERVICE) $(PARTITION_ID)

watch-maps:
	./scripts/watch-maps.sh $(ENV_FILE)

watch-maps-status:
	./scripts/watch-maps.sh $(ENV_FILE) --status

install-map-watchdog-service:
	./scripts/install-map-watchdog-service.sh $(ENV_FILE)

install-player-presence-announcer-service:
	./scripts/install-player-presence-announcer-service.sh $(ENV_FILE)

install-artificial-exchange-service:
	./scripts/install-artificial-exchange-service.sh $(ENV_FILE)

install-artificial-exchange-buyer-service:
	./scripts/install-artificial-exchange-service.sh $(ENV_FILE) /etc/systemd/system/dune-artificial-exchange-bot.service buyer

install-artificial-exchange-populator-service:
	./scripts/install-artificial-exchange-service.sh $(ENV_FILE) /etc/systemd/system/dune-artificial-exchange-populator.service populator

install-artificial-exchange-watchdog-timer:
	./scripts/install-artificial-exchange-watchdog-timer.sh $(ENV_FILE)

install-full-farm-service:
	./scripts/install-full-farm-service.sh $(ENV_FILE)

install-daily-maintenance-timer:
	./scripts/install-daily-maintenance-timer.sh $(ENV_FILE)

full-world-partitions:
	./scripts/full-world-partitions.sh $(ENV_FILE)

compose-config:
	$(COMPOSE) --env-file $(ENV_FILE) config --quiet

check-compose-static-ips:
	./scripts/check-compose-static-ips.py $(ENV_FILE)

secret-scan:
	rg -n --pcre2 "(gho_|FLS_SECRET=eyJ|POSTGRES_[A-Z_]*PASSWORD=(?!(?:change-me|replace-with|<))[A-Za-z0-9_./+=-]{24,}|RMQ_HTTP_TOKEN_AUTH_SECRET=(?!(?:change-me|replace-with|<))[A-Za-z0-9_./+=-]{32,}|DUNE_ADMIN_TOKEN=(?!(?:change-me|replace-with|<))[A-Za-z0-9_./+=-]{24,}|DUNE_ANNOUNCE_[A-Z_]*PASSWORD=(?!(?:change-me|replace-with|<))[A-Za-z0-9_./+=-]{20,}|ServiceAuthToken=[A-Za-z0-9_.-]+|ServerLoginPasswordSecret=\"(?!replace)|UsernameServerLoginSecret=\"(?!replace)|BEGIN .*PRIVATE KEY|PRIVATE KEY)" . --glob '!data/**' --glob '!captures/**' --glob '!backups/**' --glob '!config/tls/**' --glob '!.env' --glob '!Makefile' --glob '!.github/workflows/validate.yml' && exit 1 || true

test-watch-maps:
	./scripts/test-watch-maps.sh

test-admin-panel-safe-surfaces:
	python3 scripts/test-admin-panel-safe-surfaces.py

test-character-slot-tool:
	python3 scripts/test-character-slot-tool.py

test-research-catalog:
	python3 scripts/test-research-catalog.py
	python3 scripts/research_catalog.py --validate
	python3 scripts/generate-surface-docs.py --validate

test-discovery-tools:
	python3 scripts/test-discovery-tools.py

test-admin-chat:
	python3 scripts/test-dune-whisper-route.py
	python3 scripts/test-admin-chat-commands.py
	python3 scripts/test-player-presence-announcer.py

test-admin-grant-item:
	python3 scripts/test-admin-grant-item.py

.PHONY: test-smugglers-run-mp

test-smugglers-run-mp:
	python3 scripts/test-smugglers-run-mp.py

gm-catalog:
	python3 scripts/gm-command-catalog.py --format markdown

gm-probe-preview:
	python3 scripts/probe-gm-command.py --preview --command "$${GM_COMMAND:-PrintAllowedCommands}" --route "$${GM_ROUTE:-Survival_11}" --target-player "$${GM_TARGET_PLAYER:-SamplePlayer}" --admin-player "$${GM_ADMIN_PLAYER:-$${GM_TARGET_PLAYER:-SamplePlayer}}"

gm-probe-safe:
	python3 scripts/probe-gm-command.py --command "$${GM_COMMAND:-PrintAllowedCommands}" --route "$${GM_ROUTE:-Survival_11}" --target-player "$${GM_TARGET_PLAYER:-SamplePlayer}" --admin-player "$${GM_ADMIN_PLAYER:-$${GM_TARGET_PLAYER:-SamplePlayer}}" --wait-response "$${GM_WAIT_RESPONSE:-3}"

research-catalog:
	python3 scripts/research_catalog.py --validate

research-catalog-markdown:
	python3 scripts/research_catalog.py --format markdown

surface-ledger:
	python3 scripts/generate-surface-docs.py --validate

surface-ledger-markdown:
	python3 scripts/generate-surface-docs.py --format markdown

discovery-queue:
	python3 scripts/generate-discovery-queue.py

binary-candidate-scores:
	python3 scripts/score-binary-candidates.py $(STRINGS_FILE) $(SCORE_FLAGS)

asset-reference-graph:
	python3 scripts/build-asset-reference-graph.py $(GRAPH_PATHS) $(GRAPH_FLAGS)

extract-build-surfaces:
	./scripts/extract-build-surfaces.sh $(ENV_FILE) $(SERVICE) $(OUT_ROOT)

diff-build-surfaces:
	python3 scripts/diff-build-surfaces.py $(OLD_BUILD) $(NEW_BUILD) $(DIFF_FLAGS)

db-function-classifier:
	python3 scripts/classify-db-functions.py $(DB_SURFACE_JSON) $(CLASSIFIER_FLAGS)

fixture-runner:
	python3 scripts/fixture-runner.py $(FIXTURE) --env-file $(ENV_FILE) $(FIXTURE_FLAGS)

.PHONY: smugglers-run-mp-inspect smugglers-run-mp-session smugglers-run-mp-compare smugglers-run-mp-loaner smugglers-run-mp-shared-fixture-before smugglers-run-mp-shared-fixture-after smugglers-run-mp-vehicle-fixture-before smugglers-run-mp-vehicle-fixture-after

smugglers-run-mp-inspect:
	python3 scripts/smugglers-run-mp.py --env-file $(ENV_FILE) inspect $(SMUGGLERS_FLAGS)

smugglers-run-mp-session:
	python3 scripts/smugglers-run-mp.py --env-file $(ENV_FILE) init $(SMUGGLERS_FLAGS)

smugglers-run-mp-compare:
	python3 scripts/smugglers-run-mp.py --env-file $(ENV_FILE) compare $(SMUGGLERS_FLAGS)

smugglers-run-mp-loaner:
	python3 scripts/smugglers-run-mp.py --env-file $(ENV_FILE) loaner $(SMUGGLERS_FLAGS)

smugglers-run-mp-shared-fixture-before:
	python3 scripts/fixture-runner.py fixtures/smugglers-run-mp-shared-map.json --env-file $(ENV_FILE) --phase before

smugglers-run-mp-shared-fixture-after:
	python3 scripts/fixture-runner.py fixtures/smugglers-run-mp-shared-map.json --env-file $(ENV_FILE) --phase after

smugglers-run-mp-vehicle-fixture-before:
	python3 scripts/fixture-runner.py fixtures/smugglers-run-mp-owned-vehicle-safety.json --env-file $(ENV_FILE) --phase before

smugglers-run-mp-vehicle-fixture-after:
	python3 scripts/fixture-runner.py fixtures/smugglers-run-mp-owned-vehicle-safety.json --env-file $(ENV_FILE) --phase after

knob-experiment:
	python3 scripts/knob-experiment.py --catalog $(CATALOG) --env-file $(ENV_FILE) $(EXPERIMENT_FLAGS)

capture-rmq-window:
	./scripts/capture-rmq-window.sh $(ENV_FILE) $(SECONDS) $(TAG)

diff-rmq-captures:
	python3 scripts/diff-rmq-captures.py $(RMQ_BEFORE) $(RMQ_AFTER) $(RMQ_DIFF_FLAGS)

test-operational-borrowing:
	python3 scripts/test-operational-borrowing.py

test-artificial-exchange:
	python3 scripts/test-artificial-exchange.py

test-artificial-exchange-service:
	./scripts/test-artificial-exchange-service.sh

artificial-exchange-smoke:
	./scripts/artificial-exchange-smoke.sh

artificial-exchange-bootstrap-catalog:
	python3 scripts/build-exchange-bootstrap-catalog.py
	python3 scripts/build-exchange-catalog.py

artificial-exchange-research-prices:
	python3 scripts/research-exchange-prices.py --crawl-allpages --no-search-fallback
	python3 scripts/build-exchange-catalog.py

test-vehicle-fidelity-investigation:
	./scripts/investigate-vehicle-fidelity.sh >/dev/null

list-publishable:
	find . -maxdepth 3 \( -path './.git' -o -path './data' -o -path './captures' -o -path './backups' -o -path './config/tls' \) -prune -o -type f -not -name '.env' -print | sort

update-hagga-pois:
	python3 scripts/update-hagga-poi-markers.py

public-site-check:
	bash -n public-site/scripts/*.sh examples/public-site/rclone-sync.sh
	python3 -m py_compile public-site/scripts/render-dune-public-snapshot.py scripts/update-hagga-poi-markers.py
	./public-site/scripts/validate-dune-public-site.sh public-site/static
	systemd-analyze verify public-site/systemd/render-dune-static-status.service public-site/systemd/render-dune-static-status.timer

public-site-package:
	./public-site/scripts/package-dune-public-site.sh

public-site-deploy:
	./public-site/scripts/deploy-dune-public-site.sh $(PUBLIC_SITE_ENV_FILE)

public-site-verify:
	./public-site/scripts/verify-dune-public-site.sh $(PUBLIC_SITE_URL)

admin-panel-deploy:
	./scripts/deploy-admin-panel.sh $(ENV_FILE)

admin-panel-verify:
	./scripts/check-admin-ingress.sh $(ENV_FILE)

verify-local-state-ignored:
	@for path in backups/example captures/example data/example config/tls/example backups-env-example backup-env-example local.env.backup local.env.bak; do \
		git check-ignore -q "$$path" || exit 1; \
	done
