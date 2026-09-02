PYTHON := .venv/bin/python
FLET := .venv/bin/flet

.DEFAULT_GOAL := help
.PHONY: help install stage-runtime run run-web test check build-macos build-windows build-linux clean

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: .venv/.installed ## Create the Python 3.12 environment and install ACE Studio

.venv/.installed: pyproject.toml
	uv venv --python 3.12 --allow-existing .venv
	uv pip install --python $(PYTHON) -e .
	@touch $@

run: .venv/.installed ## Run ACE Studio locally as a desktop app
	$(FLET) run src/main.py

run-web: .venv/.installed ## Run the development UI in a browser
	$(FLET) run --web src/main.py

stage-runtime: .venv/.installed ## Stage uv and the API bridge for a packaged build
	$(PYTHON) scripts/stage_runtime.py

test: .venv/.installed ## Run the test suite
	$(PYTHON) -m unittest discover -s tests -v

check: test ## Compile Python and check patch whitespace
	$(PYTHON) -m compileall -q src/ace_studio src/main.py src/ace_studio_bridge.py tests
	git diff --check

build-macos: stage-runtime ## Build the macOS application bundle
	$(FLET) build macos src --yes

build-windows: stage-runtime ## Build the Windows application
	$(FLET) build windows src --yes

build-linux: stage-runtime ## Build the Linux application
	$(FLET) build linux src --yes

clean: ## Remove generated local build artifacts
	rm -rf .venv build dist
