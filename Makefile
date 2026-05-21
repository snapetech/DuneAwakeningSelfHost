COMPOSE ?= docker compose
ENV_FILE ?= .env.example

.PHONY: validate compose-config secret-scan test-watch-maps test-admin-panel-safe-surfaces test-artificial-exchange test-artificial-exchange-service artificial-exchange-smoke artificial-exchange-bootstrap-catalog artificial-exchange-research-prices test-vehicle-fidelity-investigation list-publishable preflight status check-steam-update start-full-warm-pool recover-survival recover-map watch-maps watch-maps-status install-map-watchdog-service install-artificial-exchange-service install-artificial-exchange-buyer-service install-artificial-exchange-populator-service install-player-presence-announcer-service install-full-farm-service install-daily-maintenance-timer full-world-partitions public-site-check public-site-package verify-local-state-ignored

validate: compose-config secret-scan test-watch-maps test-admin-panel-safe-surfaces test-artificial-exchange test-artificial-exchange-service test-vehicle-fidelity-investigation verify-local-state-ignored

preflight:
	./scripts/preflight.sh

status:
	./scripts/status.sh $(ENV_FILE)

check-steam-update:
	./scripts/check-steam-update.sh $(ENV_FILE)

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

install-full-farm-service:
	./scripts/install-full-farm-service.sh $(ENV_FILE)

install-daily-maintenance-timer:
	./scripts/install-daily-maintenance-timer.sh $(ENV_FILE)

full-world-partitions:
	./scripts/full-world-partitions.sh $(ENV_FILE)

compose-config:
	$(COMPOSE) --env-file $(ENV_FILE) config --quiet

secret-scan:
	rg -n --pcre2 "(gho_|FLS_SECRET=.+|ServiceAuthToken=[A-Za-z0-9_.-]+|ServerLoginPasswordSecret=\"(?!replace)|UsernameServerLoginSecret=\"(?!replace)|BEGIN .*PRIVATE KEY|PRIVATE KEY)" . --glob '!data/**' --glob '!captures/**' --glob '!backups/**' --glob '!config/tls/**' --glob '!.env' --glob '!Makefile' --glob '!.github/workflows/validate.yml' && exit 1 || true

test-watch-maps:
	./scripts/test-watch-maps.sh

test-admin-panel-safe-surfaces:
	python3 scripts/test-admin-panel-safe-surfaces.py

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
