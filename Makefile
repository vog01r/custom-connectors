# Makefile pour Custom Connectors
# Automatisation des tâches de développement

.PHONY: help install install-dev lint format test test-fast test-integration test-benchmark clean build docs serve-docs release check security audit setup pre-commit run-yotpo

# Variables
PYTHON := python3
PIP := pip
VENV := venv
SRC_DIR := src
TEST_DIR := tests
DOCS_DIR := docs

# Couleurs pour les messages
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Cible par défaut
help: ## Affiche cette aide
	@echo "$(BLUE)Custom Connectors - Commandes disponibles:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Exemples d'utilisation:$(NC)"
	@echo "  make setup          # Configuration initiale complète"
	@echo "  make install-dev    # Installation des dépendances de dev"
	@echo "  make test           # Lancer tous les tests"
	@echo "  make lint           # Vérification de la qualité du code"
	@echo "  make format         # Formatage automatique du code"

## === Installation et Setup ===

setup: clean install-dev pre-commit ## Configuration initiale complète du projet
	@echo "$(GREEN)✅ Setup terminé avec succès !$(NC)"
	@echo "$(BLUE)Prochaines étapes:$(NC)"
	@echo "  1. make test      # Vérifier que tout fonctionne"
	@echo "  2. make run-yotpo # Tester le connecteur Yotpo"

install: ## Installation des dépendances de production
	@echo "$(BLUE)📦 Installation des dépendances de production...$(NC)"
	$(PIP) install -e .

install-dev: ## Installation des dépendances de développement
	@echo "$(BLUE)📦 Installation des dépendances de développement...$(NC)"
	$(PIP) install -e ".[dev,docs,monitoring]"

pre-commit: ## Installation et configuration des hooks pre-commit
	@echo "$(BLUE)🔧 Configuration des hooks pre-commit...$(NC)"
	pre-commit install
	pre-commit install --hook-type commit-msg
	@echo "$(GREEN)✅ Hooks pre-commit installés$(NC)"

## === Qualité et Tests ===

lint: ## Vérification de la qualité du code (sans modification)
	@echo "$(BLUE)🔍 Vérification de la qualité du code...$(NC)"
	@echo "$(YELLOW)→ Ruff linting...$(NC)"
	ruff check $(SRC_DIR) $(TEST_DIR)
	@echo "$(YELLOW)→ MyPy type checking...$(NC)"
	mypy $(SRC_DIR)
	@echo "$(YELLOW)→ Bandit security scan...$(NC)"
	bandit -r $(SRC_DIR) -c pyproject.toml
	@echo "$(GREEN)✅ Qualité du code vérifiée$(NC)"

format: ## Formatage automatique du code
	@echo "$(BLUE)🎨 Formatage du code...$(NC)"
	@echo "$(YELLOW)→ Black formatting...$(NC)"
	black $(SRC_DIR) $(TEST_DIR)
	@echo "$(YELLOW)→ isort imports...$(NC)"
	isort $(SRC_DIR) $(TEST_DIR)
	@echo "$(YELLOW)→ Ruff auto-fix...$(NC)"
	ruff check --fix $(SRC_DIR) $(TEST_DIR)
	@echo "$(GREEN)✅ Code formaté$(NC)"

test: ## Lancer tous les tests avec coverage
	@echo "$(BLUE)🧪 Exécution de tous les tests...$(NC)"
	pytest -v --cov-report=term-missing --cov-report=html

test-fast: ## Tests rapides (unitaires seulement)
	@echo "$(BLUE)⚡ Tests rapides...$(NC)"
	pytest -v -m "not slow and not integration" --maxfail=5

test-integration: ## Tests d'intégration seulement
	@echo "$(BLUE)🔗 Tests d'intégration...$(NC)"
	pytest -v -m "integration" --maxfail=3

test-benchmark: ## Tests de performance
	@echo "$(BLUE)📊 Tests de performance...$(NC)"
	pytest -v -m "benchmark" --benchmark-only

test-watch: ## Tests en mode watch (re-exécution automatique)
	@echo "$(BLUE)👀 Tests en mode watch...$(NC)"
	pytest-watch --runner "pytest -v --tb=short"

## === Sécurité et Audit ===

security: ## Scan de sécurité complet
	@echo "$(BLUE)🔒 Audit de sécurité...$(NC)"
	@echo "$(YELLOW)→ Safety dependency scan...$(NC)"
	safety check
	@echo "$(YELLOW)→ Pip-audit...$(NC)"
	pip-audit
	@echo "$(YELLOW)→ Bandit code scan...$(NC)"
	bandit -r $(SRC_DIR) -c pyproject.toml
	@echo "$(YELLOW)→ Secrets detection...$(NC)"
	detect-secrets scan --all-files --force-use-all-plugins
	@echo "$(GREEN)✅ Audit de sécurité terminé$(NC)"

audit: ## Audit des dépendances
	@echo "$(BLUE)📋 Audit des dépendances...$(NC)"
	pip list --outdated
	pip-audit --desc

## === Documentation ===

docs: ## Génération de la documentation
	@echo "$(BLUE)📚 Génération de la documentation...$(NC)"
	cd $(DOCS_DIR) && mkdocs build

serve-docs: ## Serveur de documentation en mode développement
	@echo "$(BLUE)🌐 Serveur de documentation sur http://localhost:8000$(NC)"
	cd $(DOCS_DIR) && mkdocs serve

## === Build et Release ===

clean: ## Nettoyage des fichiers temporaires
	@echo "$(BLUE)🧹 Nettoyage...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ htmlcov/ .coverage .coverage.*
	@echo "$(GREEN)✅ Nettoyage terminé$(NC)"

build: clean ## Build du package
	@echo "$(BLUE)🏗️ Build du package...$(NC)"
	$(PYTHON) -m build

check: lint test ## Vérification complète (lint + tests)
	@echo "$(GREEN)✅ Vérification complète terminée$(NC)"

## === Exécution des connecteurs ===

run-yotpo: ## Exécuter le connecteur Yotpo (avec vérification env)
	@echo "$(BLUE)🚀 Lancement du connecteur Yotpo...$(NC)"
	@if [ -z "$$YOTPO_CLIENT_SECRET" ]; then \
		echo "$(RED)❌ YOTPO_CLIENT_SECRET non défini$(NC)"; \
		echo "$(YELLOW)Définissez les variables d'environnement:$(NC)"; \
		echo "  export YOTPO_CLIENT_SECRET=your_secret"; \
		echo "  export YOTPO_STORE_ID=your_store_id"; \
		echo "  export TD_API_KEY=your_td_api_key"; \
		exit 1; \
	fi
	$(PYTHON) -m custom_connectors.yotpo.main

## === Utilitaires ===

deps-compile: ## Compilation des dépendances avec pip-tools
	@echo "$(BLUE)📌 Compilation des dépendances...$(NC)"
	pip-compile --upgrade pyproject.toml
	pip-compile --upgrade --extra dev pyproject.toml

deps-sync: ## Synchronisation des dépendances
	@echo "$(BLUE)🔄 Synchronisation des dépendances...$(NC)"
	pip-sync requirements.txt requirements-dev.txt

version: ## Affichage de la version actuelle
	@echo "$(BLUE)📋 Informations de version:$(NC)"
	@echo "Python: $$($(PYTHON) --version)"
	@echo "Pip: $$($(PIP) --version)"
	@echo "Package: $$($(PYTHON) -c 'import tomllib; print(tomllib.load(open(\"pyproject.toml\", \"rb\"))[\"project\"][\"version\"])')"

env-check: ## Vérification de l'environnement de développement
	@echo "$(BLUE)🔍 Vérification de l'environnement...$(NC)"
	@echo "Python: $$(which $(PYTHON))"
	@echo "Pip: $$(which $(PIP))"
	@echo "Virtual env: $${VIRTUAL_ENV:-❌ Pas d'environnement virtuel actif}"
	@echo "Pre-commit: $$(pre-commit --version 2>/dev/null || echo '❌ Non installé')"

## === Développement ===

dev-shell: ## Lance un shell interactif avec l'environnement configuré
	@echo "$(BLUE)🐚 Shell de développement...$(NC)"
	$(PYTHON) -c "import custom_connectors; print(f'📦 Custom Connectors v{custom_connectors.__version__} loaded')"
	$(PYTHON)

profile: ## Profiling de performance du connecteur Yotpo
	@echo "$(BLUE)📊 Profiling de performance...$(NC)"
	$(PYTHON) -m cProfile -o profile.stats -m custom_connectors.yotpo.main
	@echo "$(GREEN)✅ Profil sauvé dans profile.stats$(NC)"
	@echo "$(YELLOW)Analysez avec: python -m pstats profile.stats$(NC)"

## === Release ===

release-check: ## Vérification avant release
	@echo "$(BLUE)🔍 Vérification pre-release...$(NC)"
	@echo "$(YELLOW)→ Tests complets...$(NC)"
	make test
	@echo "$(YELLOW)→ Lint complet...$(NC)"
	make lint
	@echo "$(YELLOW)→ Audit sécurité...$(NC)"
	make security
	@echo "$(YELLOW)→ Build test...$(NC)"
	make build
	@echo "$(GREEN)✅ Prêt pour release$(NC)"

release: release-check ## Processus de release complet
	@echo "$(BLUE)🚀 Processus de release...$(NC)"
	@echo "$(YELLOW)Assurez-vous d'avoir mis à jour:$(NC)"
	@echo "  - Version dans pyproject.toml"
	@echo "  - CHANGELOG.md"
	@echo "  - Documentation"
	@echo ""
	@read -p "Continuer avec la release? [y/N] " confirm && [ "$$confirm" = "y" ]
	git tag v$$($(PYTHON) -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
	@echo "$(GREEN)✅ Tag créé. Pushez avec: git push origin --tags$(NC)"

## Variables d'aide
.DEFAULT_GOAL := help

# Ensure targets run even if files with same names exist
.PHONY: $(shell grep -E '^[a-zA-Z_-]+:' $(MAKEFILE_LIST) | cut -d':' -f1)
