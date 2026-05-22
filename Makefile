COMPOSE ?= docker compose
ENV_FILE ?= .env.example

.PHONY: validate compose-config check-compose-static-ips secret-scan test-watch-maps test-admin-panel-safe-surfaces test-character-slot-tool test-admin-chat test-operational-borrowing test-artificial-exchange test-artificial-exchange-service artificial-exchange-smoke artificial-exchange-bootstrap-catalog artificial-exchange-research-prices test-vehicle-fidelity-investigation list-publishable preflight operational-identity-check operational-report operational-bundle verify-operational-bundle status standby-status failover-topology-status failover-bidirectional-audit sync-standby-files sync-standby-images promote-standby postgres-failover-seal postgres-cutback-proof rebuild-postgres-standby handoff-ready handoff-experiment summarize-handoff handoff-lab-config handoff-lab-up handoff-lab-seed handoff-lab-status handoff-lab-stop handoff-lab-remote-up handoff-lab-remote-status handoff-lab-remote-stop handoff-lab failover-orchestrate failover-role-services cutover-check cutover-network-status host-network-failover router-cutover install-dune-status-service check-steam-update backup-dry-run backup-state restore-dry-run verify-backup start-full-warm-pool recover-survival recover-map watch-maps watch-maps-status install-map-watchdog-service install-artificial-exchange-service install-artificial-exchange-buyer-service install-artificial-exchange-populator-service install-full-farm-service install-daily-maintenance-timer full-world-partitions update-hagga-pois public-site-check public-site-package public-site-deploy public-site-verify admin-panel-deploy admin-panel-verify verify-local-state-ignored rabbitmq-cert-check rabbitmq-cert-generate rabbitmq-cert-stage rabbitmq-cert-install-staged rabbitmq-cert-recreate-stack

validate: compose-config check-compose-static-ips secret-scan test-watch-maps test-admin-panel-safe-surfaces test-character-slot-tool test-admin-chat test-operational-borrowing test-artificial-exchange test-artificial-exchange-service test-vehicle-fidelity-investigation public-site-check verify-local-state-ignored

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

failover-orchestrate:
	./scripts/failover-orchestrate.sh $(ENV_FILE) $(ROLE) $(APPLY)

failover-role-services:
	./scripts/failover-role-services.sh $(ENV_FILE) $(ROLE) $(REMOTE)

cutover-check:
	./scripts/cutover-check.sh $(ENV_FILE)

cutover-network-status:
	./scripts/cutover-network-status.sh $(ENV_FILE) $(ROUTER) $(REMOTE)

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
	rg -n --pcre2 "(gho_|FLS_SECRET=.+|ServiceAuthToken=[A-Za-z0-9_.-]+|ServerLoginPasswordSecret=\"(?!replace)|UsernameServerLoginSecret=\"(?!replace)|BEGIN .*PRIVATE KEY|PRIVATE KEY)" . --glob '!data/**' --glob '!captures/**' --glob '!backups/**' --glob '!config/tls/**' --glob '!.env' --glob '!Makefile' --glob '!.github/workflows/validate.yml' && exit 1 || true

test-watch-maps:
	./scripts/test-watch-maps.sh

test-admin-panel-safe-surfaces:
	python3 scripts/test-admin-panel-safe-surfaces.py

test-character-slot-tool:
	python3 scripts/test-character-slot-tool.py

test-admin-chat:
	python3 scripts/test-admin-chat-commands.py
	python3 scripts/test-player-presence-announcer.py

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
	@for path in backups/example captures/example data/example config/tls/example; do \
		git check-ignore -q "$$path" || exit 1; \
	done
