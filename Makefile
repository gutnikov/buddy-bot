.PHONY: test build up down render-env deploy

SECRETS_REPO ?= /home/deploy/work/secrets/secrets
ENV ?= production

test:
	docker build -t buddy-bot-test --target test . 2>/dev/null || (pip install -e ".[dev]" && pytest tests/ -v)

build:
	docker build -t buddy-bot .

render-env: ## Render .env from SOPS-encrypted secrets
	$(SECRETS_REPO)/scripts/render-env.sh buddy-bot $(ENV) -o .env

up:
	docker compose up -d

down:
	docker compose down

deploy: render-env up ## Render secrets and start services
