SHELL := /bin/sh
PYTHON := backend/.venv/bin/python
PIP := backend/.venv/bin/pip
NPM := npm --prefix frontend

.PHONY: help setup backend-setup frontend-setup dev-backend dev-frontend test lint format build up down logs

help:
	@echo "setup            Install backend and frontend dependencies"
	@echo "dev-backend      Run Django on :8000"
	@echo "dev-frontend     Run Vite on :5173"
	@echo "test             Run backend tests"
	@echo "lint             Run ruff + frontend eslint/typecheck"
	@echo "format           Format backend and frontend sources"
	@echo "build            Production frontend build"
	@echo "up / down        Docker Compose stack on :8080"
	@echo "logs             Follow Compose logs"

setup: backend-setup frontend-setup

backend-setup:
	python3 -m venv backend/.venv
	$(PIP) install -r backend/requirements-dev.txt
	cd backend && .venv/bin/python manage.py migrate

frontend-setup:
	$(NPM) install

dev-backend:
	cd backend && .venv/bin/python manage.py runserver 127.0.0.1:8000

dev-frontend:
	$(NPM) run dev

test:
	cd backend && .venv/bin/python -m pytest

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	$(NPM) run typecheck
	$(NPM) run lint

format:
	cd backend && .venv/bin/ruff check --fix . && .venv/bin/ruff format .
	$(NPM) run lint -- --fix

build:
	$(NPM) run build

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f
