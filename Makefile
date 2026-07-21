.PHONY: help setup setup-api setup-web sandbox-build dev down logs \
	test test-api check-api test-web build-web e2e compose-check demo-reset-fixture demo-reset-live

PYTHON ?= python
NPM ?= npm
COMPOSE ?= docker compose

help:
	@echo "CodeReason development commands"
	@echo "  make setup               Install API and web development dependencies"
	@echo "  make dev                 Build the fixed sandbox image and start Compose"
	@echo "  make test                Run backend and frontend unit tests"
	@echo "  make check-api           Compile all backend modules without writing source"
	@echo "  make e2e                 Run the Playwright demo flow"
	@echo "  make demo-reset-fixture  Reset and seed explicitly labelled fixture data"
	@echo "  make demo-reset-live     Reset and enqueue live execution/provider work"
	@echo "  make down                Stop Compose services and preserve database data"

setup: setup-api setup-web

setup-api:
	$(PYTHON) -m pip install -e "./apps/api[dev,postgres]"

setup-web:
	$(NPM) --prefix apps/web ci

sandbox-build:
	$(COMPOSE) build sandbox

dev: sandbox-build
	$(COMPOSE) up --build --remove-orphans

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs --follow api worker web

test: test-api test-web

test-api:
	$(PYTHON) -m pytest apps/api/tests

check-api:
	$(PYTHON) -m compileall -q apps/api/app

test-web:
	$(NPM) --prefix apps/web run test:run

build-web:
	$(NPM) --prefix apps/web run build

e2e:
	$(NPM) --prefix apps/web run e2e

compose-check:
	$(COMPOSE) config --quiet

demo-reset-fixture:
	sh scripts/demo-reset.sh fixture

demo-reset-live:
	sh scripts/demo-reset.sh live
