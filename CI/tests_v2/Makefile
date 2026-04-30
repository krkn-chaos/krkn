# CI/tests_v2 functional tests - single entry point.
# Run from repo root: make -f CI/tests_v2/Makefile <target>
# Or from CI/tests_v2: make <target> (REPO_ROOT is resolved automatically).

# Resolve repo root: go to Makefile dir then up two levels (CI/tests_v2 -> repo root)
REPO_ROOT := $(shell cd "$(dir $(firstword $(MAKEFILE_LIST)))" && cd ../.. && pwd)
VENV := $(REPO_ROOT)/venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CLUSTER_NAME ?= ci-krkn
TESTS_DIR := $(REPO_ROOT)/CI/tests_v2

.PHONY: setup preflight test test-fast test-debug test-scenario test-dry-run clean help

help:
	@echo "CI/tests_v2 functional tests - usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  setup         Create venv (if missing), install Python deps, create KinD cluster (kind-config-dev.yml)."
	@echo "               Run once before first test. Override cluster config: KIND_CONFIG=path make setup"
	@echo ""
	@echo "  preflight     Check Python 3.11+, kind, kubectl, Docker, cluster reachability, test deps."
	@echo "               Invoked automatically by test targets; run standalone to validate environment."
	@echo ""
	@echo "  test         Full run: retries (2), timeout 300s, HTML report, JUnit XML, coverage."
	@echo "               Use for CI or final verification. Output: report.html, results.xml"
	@echo ""
	@echo "  test-fast     Quick run: no retries, 120s timeout, no report. For fast local iteration."
	@echo ""
	@echo "  test-debug    Debug run: verbose (-s), keep failed namespaces (--keep-ns-on-fail), DEBUG logging."
	@echo "               Use when investigating failures; inspect kept namespaces with kubectl."
	@echo ""
	@echo "  test-scenario Run only one scenario. Requires SCENARIO=<marker>."
	@echo "               Example: make test-scenario SCENARIO=pod_disruption"
	@echo ""
	@echo "  test-dry-run  Validate scenario plumbing only (no Kraken execution). Sets KRKN_TEST_DRY_RUN=1."
	@echo ""
	@echo "  clean        Delete KinD cluster $(CLUSTER_NAME) and remove report.html, results.xml."
	@echo ""
	@echo "  help         Show this help."
	@echo ""
	@echo "Run from repo root: make -f CI/tests_v2/Makefile <target>"
	@echo "Or from CI/tests_v2:  make <target>"

setup: $(VENV)/.installed
	@echo "Running cluster setup..."
	$(MAKE) -f $(TESTS_DIR)/Makefile preflight
	cd $(REPO_ROOT) && ./CI/tests_v2/setup_env.sh
	@echo "Setup complete. Run 'make test' or 'make -f CI/tests_v2/Makefile test' from repo root."

$(VENV)/.installed: $(REPO_ROOT)/requirements.txt $(TESTS_DIR)/requirements.txt
	@if [ ! -d "$(VENV)" ]; then python3 -m venv $(VENV); echo "Created venv at $(VENV)"; fi
	$(PYTHON) -m pip install -q --upgrade pip
	# Root = Kraken runtime; tests_v2 = test-only plugins; both required for functional tests.
	$(PIP) install -q -r $(REPO_ROOT)/requirements.txt
	$(PIP) install -q -r $(TESTS_DIR)/requirements.txt
	@touch $(VENV)/.installed
	@echo "Python deps installed."

preflight:
	@echo "Preflight: checking Python, tools, and cluster..."
	@command -v python3 >/dev/null 2>&1 || { echo "Error: python3 not found."; exit 1; }
	@python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" || { echo "Error: Python 3.11+ required."; exit 1; }
	@command -v kind >/dev/null 2>&1 || { echo "Error: kind not installed."; exit 1; }
	@command -v kubectl >/dev/null 2>&1 || { echo "Error: kubectl not installed."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Error: Docker not running (required for KinD)."; exit 1; }
	@if kind get clusters 2>/dev/null | grep -qx "$(CLUSTER_NAME)"; then \
		kubectl cluster-info >/dev/null 2>&1 || { echo "Error: Cluster $(CLUSTER_NAME) exists but cluster-info failed."; exit 1; }; \
	else \
		echo "Note: Cluster $(CLUSTER_NAME) not found. Run 'make setup' to create it."; \
	fi
	@$(PYTHON) -c "import pytest_rerunfailures, pytest_html, pytest_timeout, pytest_order" 2>/dev/null || \
		{ echo "Error: Install test deps with 'make setup' or pip install -r CI/tests_v2/requirements.txt"; exit 1; }
	@echo "Preflight OK."

test: preflight
	cd $(REPO_ROOT) && KRKN_TEST_COVERAGE=1 $(PYTHON) -m pytest $(TESTS_DIR)/ -v --timeout=300 --reruns=2 --reruns-delay=10 \
		--html=$(TESTS_DIR)/report.html -n auto --junitxml=$(TESTS_DIR)/results.xml

test-fast: preflight
	cd $(REPO_ROOT) && $(PYTHON) -m pytest $(TESTS_DIR)/ -v -p no:rerunfailures -n auto --timeout=120

test-debug: preflight
	cd $(REPO_ROOT) && $(PYTHON) -m pytest $(TESTS_DIR)/ -v -s -p no:rerunfailures --timeout=300 \
		--keep-ns-on-fail --log-cli-level=DEBUG

test-scenario: preflight
	@if [ -z "$(SCENARIO)" ]; then echo "Error: set SCENARIO=pod_disruption (or application_outage, etc.)"; exit 1; fi
	cd $(REPO_ROOT) && $(PYTHON) -m pytest $(TESTS_DIR)/ -v -m "$(SCENARIO)" --timeout=300 --reruns=2 --reruns-delay=10

test-dry-run: preflight
	cd $(REPO_ROOT) && KRKN_TEST_DRY_RUN=1 $(PYTHON) -m pytest $(TESTS_DIR)/ -v

clean:
	@kind delete cluster --name $(CLUSTER_NAME) 2>/dev/null || true
	@rm -f $(TESTS_DIR)/report.html $(TESTS_DIR)/results.xml
	@echo "Cleaned cluster and report artifacts."
