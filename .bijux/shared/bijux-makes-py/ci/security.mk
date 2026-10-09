SECURITY_PATHS                ?= src
VENV_PYTHON                   ?= $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/python,python)
BANDIT                        ?= $(VENV_PYTHON) -m bandit
PIP_AUDIT                     ?= $(VENV_PYTHON) -m pip_audit
SKIP_BANDIT                   ?= 0

SECURITY_REPORT_DIR           ?= $(PROJECT_ARTIFACTS_DIR)/security
BANDIT_JSON                   := $(SECURITY_REPORT_DIR)/bandit.json
BANDIT_TXT                    := $(SECURITY_REPORT_DIR)/bandit.txt
PIPA_JSON                     := $(SECURITY_REPORT_DIR)/pip-audit.json
PIPA_TXT                      := $(SECURITY_REPORT_DIR)/pip-audit.txt
SECURITY_REQS                 ?= $(SECURITY_REPORT_DIR)/requirements.txt
SECURITY_PYCACHE_PREFIX       ?= $(SECURITY_REPORT_DIR)/pycache

SECURITY_IGNORE_IDS           ?=
SECURITY_IGNORE_FLAGS          = $(foreach V,$(SECURITY_IGNORE_IDS),--ignore-vuln $(V))
PIP_AUDIT_CONSOLE_FLAGS       ?= --skip-editable --progress-spinner off
PIP_AUDIT_INPUTS              ?=
SECURITY_STRICT               ?= 1

BANDIT_EXCLUDES               ?= artifacts,build,dist,.tox,.mypy_cache,.pytest_cache
BANDIT_THREADS                ?= 0
SECURITY_BANDIT_SKIP_IDS      ?=
BANDIT_FLAGS                  ?= --severity-level high --confidence-level high
SECURITY_AUDIT_PREPARE_MODE   ?= none
SECURITY_PIP_AUDIT_TEXT_COMMAND ?=
SECURITY_EXTRA_TARGETS        ?=
SECURITY_SELF_MAKE            ?= $(SELF_MAKE)

SECURITY_BANDIT_SKIP_FLAG := $(if $(SECURITY_BANDIT_SKIP_IDS),--skip $(SECURITY_BANDIT_SKIP_IDS),)
SECURITY_PYTHON_ENV := PYTHONPYCACHEPREFIX="$(abspath $(SECURITY_PYCACHE_PREFIX))"

include $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/util.mk

.PHONY: security security-bandit security-audit security-deps security-clean

security: security-bandit security-audit security-deps

security-bandit:
	@mkdir -p "$(SECURITY_REPORT_DIR)"
	@echo "→ Bandit (Python static analysis)"
	@if [ "$(SKIP_BANDIT)" != "0" ]; then \
	  echo "✘ Bandit is mandatory; SKIP_BANDIT must remain 0"; \
	  exit 2; \
	fi
	@if [ -n "$(strip $(SECURITY_BANDIT_SKIP_IDS))" ]; then \
	  echo "✘ Ungoverned Bandit suppressions are forbidden: $(SECURITY_BANDIT_SKIP_IDS)"; \
	  exit 2; \
	fi
	@set -e; JSON_RC=0; TEXT_RC=0; RC_FILE="$(SECURITY_REPORT_DIR)/.bandit.rc"; \
	$(SECURITY_PYTHON_ENV) $(BANDIT) -r "$(SECURITY_PATHS)" -x "$(BANDIT_EXCLUDES)" $(SECURITY_BANDIT_SKIP_FLAG) $(BANDIT_FLAGS) -f json -o "$(BANDIT_JSON)" -n $(BANDIT_THREADS) || JSON_RC=$$?; \
	{ set +e; $(SECURITY_PYTHON_ENV) $(BANDIT) -r "$(SECURITY_PATHS)" -x "$(BANDIT_EXCLUDES)" $(SECURITY_BANDIT_SKIP_FLAG) $(BANDIT_FLAGS) -n $(BANDIT_THREADS); RC=$$?; echo $$RC > "$$RC_FILE"; exit 0; } 2>&1 | tee "$(BANDIT_TXT)"; \
	TEXT_RC=$$(cat "$$RC_FILE"); rm -f "$$RC_FILE"; \
	RC=$$TEXT_RC; if [ $$RC -eq 0 ]; then RC=$$JSON_RC; fi; \
	if [ $$RC -ne 0 ]; then exit $$RC; fi

security-audit:
	@mkdir -p "$(SECURITY_REPORT_DIR)"
	@echo "→ Pip-audit (dependency vulnerability scan)"
	@if [ "$(SECURITY_STRICT)" != "1" ]; then \
	  echo "✘ Dependency vulnerability auditing is mandatory and strict"; \
	  exit 2; \
	fi
	@if [ -n "$(strip $(SECURITY_IGNORE_IDS))" ]; then \
	  echo "✘ Ungoverned dependency vulnerability suppressions are forbidden: $(SECURITY_IGNORE_IDS)"; \
	  exit 2; \
	fi
	@if [ "$(SECURITY_AUDIT_PREPARE_MODE)" = "pyproject" ]; then \
	  $(SECURITY_PYTHON_ENV) $(VENV_PYTHON) -c "import tomllib; from pathlib import Path; data=tomllib.loads(Path('pyproject.toml').read_text()); reqs=data.get('project', {}).get('dependencies', []); Path('$(SECURITY_REQS)').write_text('\\n'.join(reqs) + '\\n')"; \
	fi
	@set -e; \
	JSON_RC=0; \
	TEXT_RC=0; \
	$(SECURITY_PYTHON_ENV) $(PIP_AUDIT) $(SECURITY_IGNORE_FLAGS) $(PIP_AUDIT_CONSOLE_FLAGS) $(PIP_AUDIT_INPUTS) \
	  -f json -o "$(PIPA_JSON)" >/dev/null 2>&1 || JSON_RC=$$?; \
	if [ -n "$(strip $(SECURITY_PIP_AUDIT_TEXT_COMMAND))" ]; then \
	  PIPA_JSON="$(PIPA_JSON)" \
	  SECURITY_STRICT="$(SECURITY_STRICT)" \
	  SECURITY_IGNORE_IDS="$(SECURITY_IGNORE_IDS)" \
	  $(SECURITY_PIP_AUDIT_TEXT_COMMAND) >"$(PIPA_TXT)" || TEXT_RC=$$?; \
	else \
	  RC_FILE="$(SECURITY_REPORT_DIR)/.pip-audit.rc"; \
	  { set +e; $(SECURITY_PYTHON_ENV) $(PIP_AUDIT) $(SECURITY_IGNORE_FLAGS) $(PIP_AUDIT_CONSOLE_FLAGS) $(PIP_AUDIT_INPUTS); RC=$$?; echo $$RC > "$$RC_FILE"; exit 0; } 2>&1 | tee "$(PIPA_TXT)"; \
	  TEXT_RC=$$(cat "$$RC_FILE"); \
	  rm -f "$$RC_FILE"; \
	fi; \
	cat "$(PIPA_TXT)"; \
	RC=$$TEXT_RC; \
	if [ $$RC -eq 0 ]; then RC=$$JSON_RC; fi; \
	if [ $$RC -gt 1 ]; then echo "! pip-audit invocation failed (rc=$$RC)"; fi; \
	if [ $$RC -ne 0 ] && [ "$(SECURITY_STRICT)" = "1" ]; then exit $$RC; fi

security-deps:
	$(call run_make_targets,$(SECURITY_EXTRA_TARGETS),$(SECURITY_SELF_MAKE))

security-clean:
	@rm -rf "$(SECURITY_REPORT_DIR)"

##@ Security
security:        ## Run Bandit, pip-audit, and any package-specific dependency checks
security-bandit: ## Run Bandit (screen + JSON artifact)
security-audit:  ## Run pip-audit once, gate results, and write reports
security-deps:   ## Run package-specific security helper targets when configured
security-clean:  ## Remove security reports
