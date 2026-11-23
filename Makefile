.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help install lint format type test cov up down logs collect stats psql migrate clean

help: ## Mostra os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Instala o projeto em modo editável com dependências de dev
	python -m pip install --upgrade pip
	pip install -e ".[dev]"

lint: ## Ruff lint
	ruff check src tests

format: ## Ruff format
	ruff format src tests
	ruff check --fix src tests

type: ## Mypy
	mypy src

test: ## Testes
	pytest

cov: ## Testes com cobertura
	pytest --cov=campinas_news --cov-report=term-missing --cov-report=html

up: ## Sobe a stack (postgres + worker)
	docker compose up -d --build

down: ## Derruba a stack
	docker compose down

logs: ## Logs do worker
	docker compose logs -f worker

collect: ## Coleta única dentro do container
	docker compose run --rm worker collect

stats: ## Estatísticas do dia
	docker compose run --rm worker stats

psql: ## Abre psql no banco
	docker compose exec postgres psql -U $${POSTGRES_USER:-campinas} -d $${POSTGRES_DB:-campinas_news}

migrate: ## Aplica migrações
	docker compose run --rm worker migrate

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
