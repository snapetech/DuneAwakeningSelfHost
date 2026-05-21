COMPOSE ?= docker compose
ENV_FILE ?= .env.example

.PHONY: validate compose-config check-compose-static-ips secret-scan test-watch-maps test-admin-panel-safe-surfaces test-character-slot-tool test-admin-chat test-operational-borrowing test-artificial-exchange test-artificial-exchange-service artificial-exchange-smoke artificial-exchange-bootstrap-catalog artificial-exchange-research-prices test-vehicle-fidelity-investigation list-publishable preflight operational-identity-check operational-report operational-bundle verify-operational-bundle status check-steam-update backup-dry-run backup-state restore-dry-run verify-backup start-full-warm-pool recover-survival recover-map watch-maps watch-maps-status install-map-watchdog-service install-artificial-exchange-service install-artificial-exchange-buyer-service install-artificial-exchange-populator-service install-artificial-exchange-watchdog-timer install-full-farm-service install-daily-maintenance-timer full-world-partitions public-site-check public-site-package verify-local-state-ignored rabbitmq-cert-check rabbitmq-cert-generate

validate: compose-config check-compose-static-ips secret-scan test-watch-maps test-admin-panel-safe-surfaces test-character-slot-tool test-admin-chat test-operational-borrowing test-artificial-exchange test-artificial-exchange-service test-vehicle-fidelity-investigation verify-local-state-ignored

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

status:
	./scripts/status.sh $(ENV_FILE)

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

public-site-check:
	bash -n public-site/scripts/*.sh examples/public-site/rclone-sync.sh
	python3 -m py_compile public-site/scripts/render-dune-public-snapshot.py
	systemd-analyze verify public-site/systemd/render-dune-static-status.service public-site/systemd/render-dune-static-status.timer

public-site-package:
	./public-site/scripts/package-dune-public-site.sh

verify-local-state-ignored:
	@for path in backups/example captures/example data/example config/tls/example; do \
		git check-ignore -q "$$path" || exit 1; \
	done
