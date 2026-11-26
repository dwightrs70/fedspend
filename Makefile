.PHONY: help install lint format test discover discover-sizes up down logs check-env download

PY := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "make install        - install dev dependencies into .venv and set up pre-commit"
	@echo "make lint           - run ruff checks"
	@echo "make format         - auto-format with ruff"
	@echo "make test           - run unit tests"
	@echo "make discover       - list USAspending archive files for DHS and Treasury"
	@echo "make discover-sizes - list USAspending archive files for DHS and Treasury, with sizes"
	@echo "make up/down        - start/stop the local Docker stack (MinIO, Postgres)"

check-env:
	@test -x $(PY) || (echo "Create the venv first: python3.12 -m venv .venv" && exit 1)

install: check-env
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.in
	.venv/bin/pre-commit install

lint: check-env
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format: check-env
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

test: check-env
	.venv/bin/pytest -q

discover: check-env
	$(PY) -m ingestion.discover_files $(ARGS)

discover-sizes: check-env
	$(PY) -m ingestion.discover_files --with-sizes

up:
	@test -f .env || (echo "Copy .env.example to .env first" && exit 1)
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

download: check-env
	$(PY) -m ingestion.download_files $(ARGS)
