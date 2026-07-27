SHELL := /bin/sh
.DEFAULT_GOAL := help

COMPOSE := docker compose
SERVICE ?= api
ADMIN_LOGIN ?= admin
SERVER_NAME ?=
PLATFORM ?=

.PHONY: help version version-set version-check env build up down restart ps logs migrate admin-create \
	admin-create-generated admin-reset-password enrollment-create test test-unit \
	test-integration test-devices lint doctor clean

help: ## Показать команды
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "%-26s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

version: ## Показать единую версию сервиса
	@tr -d '\r\n' < VERSION
	@echo

version-set: ## Установить SemVer, NEW_VERSION=0.3.0
	@./scripts/set-version.sh "$(NEW_VERSION)"

version-check: ## Сверить source, runtime и Python package
	@./scripts/check-version.sh

env: ## Создать .env из безопасного примера
	@test -f .env || cp .env.example .env
	@chmod 600 .env
	@echo ".env создан. Замените POSTGRES_PASSWORD и DATABASE_URL."

build: ## Собрать Docker-образы
	$(COMPOSE) build

up: ## Запустить БД, миграции, API и web dashboard
	$(COMPOSE) up -d db
	$(COMPOSE) run --rm api alembic upgrade head
	$(COMPOSE) up -d api frontend

down: ## Остановить стек без удаления данных
	$(COMPOSE) down

restart: ## Пересоздать контейнеры
	$(COMPOSE) up -d --build --force-recreate

ps: ## Показать контейнеры
	$(COMPOSE) ps

logs: ## Показать журналы, SERVICE=api
	$(COMPOSE) logs -f $(SERVICE)

migrate: ## Выполнить миграции из свежего образа
	$(COMPOSE) run --rm api alembic upgrade head

admin-create: ## Интерактивно создать администратора
	$(COMPOSE) exec api python -m app.cli admin-create --login "$(ADMIN_LOGIN)"

admin-create-generated: ## Создать администратора со случайным временным паролем
	$(COMPOSE) exec api python -m app.cli admin-create --login "$(ADMIN_LOGIN)" --generate

admin-reset-password: ## Интерактивно сменить пароль администратора
	$(COMPOSE) exec api python -m app.cli admin-reset-password --login "$(ADMIN_LOGIN)"

enrollment-create: ## Создать одноразовый token, SERVER_NAME=... PLATFORM=ubuntu|openwrt|routeros
	@test -n "$(SERVER_NAME)" || { echo "ERROR: задайте SERVER_NAME" >&2; exit 2; }
	@test -n "$(PLATFORM)" || { echo "ERROR: задайте PLATFORM" >&2; exit 2; }
	$(COMPOSE) exec api python -m app.cli enrollment-create \
		--server-name "$(SERVER_NAME)" --platform "$(PLATFORM)"

test: ## Выполнить все тесты в Docker
	$(COMPOSE) run --rm api python -m pytest -p no:cacheprovider

test-unit: ## Выполнить unit-тесты
	$(COMPOSE) run --rm api python -m pytest -p no:cacheprovider tests/unit

test-integration: ## Выполнить интеграционные тесты
	$(COMPOSE) run --rm api python -m pytest -p no:cacheprovider tests/integration

test-devices: ## Полный E2E: curl-установка на Ubuntu и OpenWrt в Docker
	@./scripts/e2e-device-test.sh

lint: ## Проверить стиль и типовые ошибки
	$(COMPOSE) run --rm api ruff check --no-cache app tests

doctor: ## Проверить конфигурацию Docker Compose
	@./scripts/doctor.sh

clean: ## Удалить только локальные кеши
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -r {} +
