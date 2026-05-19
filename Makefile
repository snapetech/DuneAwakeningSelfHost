COMPOSE ?= docker compose
ENV_FILE ?= .env.example

.PHONY: validate compose-config secret-scan list-publishable

validate: compose-config secret-scan

compose-config:
	$(COMPOSE) --env-file $(ENV_FILE) config --quiet

secret-scan:
	rg -n --pcre2 "(gho_|FLS_SECRET=.+|ServiceAuthToken=[A-Za-z0-9_.-]+|ServerLoginPasswordSecret=\"(?!replace)|UsernameServerLoginSecret=\"(?!replace)|BEGIN .*PRIVATE KEY|PRIVATE KEY)" . --glob '!data/**' --glob '!config/tls/**' --glob '!.env' --glob '!Makefile' --glob '!.github/workflows/validate.yml' && exit 1 || true

list-publishable:
	find . -maxdepth 3 -type f -not -path './.git/*' -not -path './data/*' -not -path './config/tls/*' -not -name '.env' | sort
