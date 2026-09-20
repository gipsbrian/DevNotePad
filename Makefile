SHELL := /bin/bash

BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/.venv
BACKEND_PORT ?= 8010
FRONTEND_PORT ?= 5180

# SQLModel/pydantic aren't compatible with Python 3.14's lazy-annotation
# change yet -- Docker's image pins 3.12, and so do we here via uv, which
# installs its own interpreter (no sudo / system package needed).
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

.PHONY: help setup install install-backend install-frontend \
	dev dev-backend dev-frontend \
	test test-backend test-frontend \
	build-frontend docker-up docker-down docker-reset clean

help:
	@echo "DevNotePad -- common tasks:"
	@echo "  make setup            Interactively create .env (token input hidden, never in shell history)"
	@echo "  make install          Install backend + frontend dependencies"
	@echo "  make dev              Run backend and frontend dev servers together"
	@echo "  make test             Run backend and frontend test suites"
	@echo "  make docker-up        Run the full stack via Docker Compose"
	@echo "  make docker-down      Stop the Docker Compose stack"
	@echo "  make docker-reset     Rebuild from scratch (drops volumes; use after dependency changes)"
	@echo "  make clean            Remove local venv/node_modules (keeps .env and data)"
	@echo ""
	@echo "Ports default to $(BACKEND_PORT)/$(FRONTEND_PORT) to avoid clashing with"
	@echo "other local services; override with e.g. 'make dev BACKEND_PORT=8000 FRONTEND_PORT=5173'."

setup:
	@bash scripts/setup-env.sh

install: install-backend install-frontend

install-backend:
	@if [ ! -x "$(UV)" ]; then \
		echo "Installing uv (user-local, no sudo required)..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	@$(UV) python install 3.12
	@$(UV) venv --python 3.12 $(VENV)
	@$(UV) pip install -p $(VENV) -r $(BACKEND_DIR)/requirements-dev.txt
	@echo "Backend dependencies installed into $(VENV)"

install-frontend:
	cd $(FRONTEND_DIR) && npm install

dev-backend:
	cd $(BACKEND_DIR) && CORS_ORIGINS='["http://localhost:$(FRONTEND_PORT)"]' \
		.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port $(BACKEND_PORT)

dev-frontend:
	cd $(FRONTEND_DIR) && VITE_API_BASE_URL=http://localhost:$(BACKEND_PORT) \
		npm run dev -- --port $(FRONTEND_PORT)

dev:
	@echo "Backend:  http://localhost:$(BACKEND_PORT)"
	@echo "Frontend: http://localhost:$(FRONTEND_PORT)"
	@echo "Press Ctrl+C to stop both."
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) --no-print-directory dev-backend & \
	$(MAKE) --no-print-directory dev-frontend & \
	wait

test: test-backend test-frontend

test-backend:
	cd $(BACKEND_DIR) && .venv/bin/python -m pytest -q

test-frontend:
	cd $(FRONTEND_DIR) && npx vitest run

build-frontend:
	cd $(FRONTEND_DIR) && npm run build

docker-up:
	BACKEND_PORT=$(BACKEND_PORT) FRONTEND_PORT=$(FRONTEND_PORT) docker compose up --build

docker-down:
	docker compose down

# The frontend's node_modules lives in a named volume that is only seeded
# from the image the first time. After adding/removing a dependency, a
# plain `docker-up` keeps the stale copy and Vite fails to resolve the new
# import — this drops that one volume so the rebuilt image re-seeds it.
# Deliberately NOT `down -v`: that would also delete devnotepad-data,
# which holds your boards, columns and local notes.
docker-reset:
	docker compose down --remove-orphans
	-docker volume rm -f devnotepad-frontend-node-modules
	BACKEND_PORT=$(BACKEND_PORT) FRONTEND_PORT=$(FRONTEND_PORT) docker compose up --build

clean:
	rm -rf $(VENV) $(FRONTEND_DIR)/node_modules $(FRONTEND_DIR)/dist
	@echo "Removed venv/node_modules/dist. .env and data/ were left untouched."
