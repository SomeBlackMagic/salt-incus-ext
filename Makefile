SHELL  := /bin/bash

GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
BOLD   := $(shell tput -Txterm bold)
ULINE  := $(shell tput -Txterm smul)
RESET  := $(shell tput -Txterm sgr0)

.DEFAULT_GOAL:=help


.PHONY: help
help:
	@echo ''
	@echo '${ULINE}Usage:${RESET}'
	@echo '    ${YELLOW}make${RESET} ${GREEN}<TARGET>${RESET}'
	@echo ''
	@echo ''
	@echo '${ULINE}Targets:${RESET}'
	@awk 'BEGIN {FS = ":.*?## "} { \
		if (/^[a-zA-Z_-]+:.*?##.*$$/) {printf "     ${BOLD}${GREEN}%-20s${RESET}%s\n", $$1, $$2} \
		else if (/^## .*$$/) {printf "\n  ${CYAN}[%s]${RESET}\n", substr($$1,4)} \
		}' $(MAKEFILE_LIST)

## Lifecycle

.PHONY: dev
dev: ## Create dev venv, (re-)install project in it
	@python3 tools/initialize.py

.PHONY: clean
clean: ## Remove: project/nox venvs, built docs
	@rm -rf .nox .venv docs/_build

## Docs

.PHONY: docs
changelog: dev ## Render changelog. Requires VERSION parameter.
	@if [ -z "$(VERSION)" ]; then \
		echo "Missing VERSION parameter. Example: make changelog VERSION=1.0.0" >&2; exit 1; \
	fi; \
    source .venv/bin/activate; \
	towncrier build --yes --version='$(VERSION)'

.PHONY: docs
docs: dev ## Build docs
	@source .venv/bin/activate; \
	  nox -e docs --extra-pythons=3.14 --python=3.14

.PHONY: docs-dev
docs-dev: dev ## Build docs, serve them and refresh on changes
	@source .venv/bin/activate; \
	  nox -e docs-dev --extra-pythons=3.14 --python=3.14

## Release

.PHONY: release
release: dev ## Render changelog, commit and create release tag. VERSION auto-detected or pass VERSION=x.y.z
	@source .venv/bin/activate; \
	  if [ -z "$(VERSION)" ]; then \
	    ver=$$(python3 tools/version.py next); \
	  else \
	    ver="$(VERSION)"; \
	  fi; \
	  echo "Releasing v$$ver"; \
	  towncrier build --yes --version="$$ver" && \
	  git add CHANGELOG.md changelog/ && \
	  git commit -m "Release v$$ver" && \
	  git tag -a "v$$ver" -m "Release v$$ver" && \
	  echo "Done. Run 'git push --follow-tags' to trigger the release pipeline."

## Code Quality

.PHONY: fmt
fmt: ## Auto-fix formatting (black, isort, pyupgrade, trailing whitespace, etc.)
	@pre-commit run trailing-whitespace --all-files || true
	@pre-commit run end-of-file-fixer --all-files || true
	@pre-commit run mixed-line-ending --all-files || true
	@pre-commit run remove-import-headers --all-files || true
	@pre-commit run pyupgrade --all-files || true
	@pre-commit run isort --all-files || true
	@pre-commit run black --all-files || true
	@pre-commit run blacken-docs --all-files || true
	@pre-commit run rewrite-docstrings --all-files || true
	@pre-commit run rewrite-tests --all-files || true

.PHONY: lint
lint: ## Run all pre-commit checks (formatting + linting + security)
	@pre-commit run --all-files

## Verification

.PHONY: check
check: lint docs tests ## Run all checks: lint + docs + tests (same as CI)

## Tests

.PHONY: tests
tests: dev ## Run tests
	@source .venv/bin/activate; \
	  nox -e tests-3.10
