.PHONY: test build up down

test:
	docker build -t buddy-bot-test --target test . 2>/dev/null || pip install -e ".[dev]" && pytest tests/ -v

build:
	docker build -t buddy-bot .

up:
	docker compose up -d

down:
	docker compose down
