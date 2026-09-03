PYTHON := .venv/bin/python
FLET := .venv/bin/flet

.DEFAULT_GOAL := help
.PHONY: help install stage-runtime run run-web test check build-macos build-windows build-linux clean

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: .venv/.installed ## Create the Python 3.12 environment and install ACE Studio

.venv/.installed: pyproject.toml
	uv sync --python 3.12
	@touch $@

run: .venv/.installed ## Run ACE Studio locally as a desktop app
	$(FLET) run src/main.py

run-web: .venv/.installed ## Run the development UI in a browser
	$(FLET) run --web src/main.py

stage-runtime: .venv/.installed ## Stage uv and the API bridge for a packaged build
	$(PYTHON) scripts/stage_runtime.py

test: .venv/.installed ## Run tests with branch coverage
	$(PYTHON) -m coverage run -m unittest discover -s tests -v
	$(PYTHON) -m coverage report

check: test ## Lint, compile Python, and check patch whitespace
	$(PYTHON) -m ruff check .
	$(PYTHON) -m compileall -q src/ace_studio src/main.py src/ace_studio_bridge.py scripts tests
	git diff --check

build-macos: stage-runtime ## Build the macOS application bundle
	$(FLET) build macos src --yes

build-windows: stage-runtime ## Build the Windows application
	$(FLET) build windows src --yes

build-linux: stage-runtime ## Build the Linux application
	$(FLET) build linux src --yes

clean: ## Remove generated local build artifacts
	rm -rf .venv build dist
