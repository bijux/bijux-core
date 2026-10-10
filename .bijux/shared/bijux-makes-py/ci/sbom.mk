PACKAGE_NAME             ?= $(PROJECT_SLUG)
SBOM_METADATA_PYTHON     ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3.11)
SBOM_SOURCE_ROOT         ?= $(MONOREPO_ROOT)
GIT_SHA                  ?= $(shell git -C "$(SBOM_SOURCE_ROOT)" rev-parse --short HEAD 2>/dev/null || echo unknown)
SBOM_PYPROJECT           ?= pyproject.toml
SBOM_VERSION_RESOLVER    ?=
SBOM_PYTHON_ENV          ?=
SBOM_REQUIRE_CANDIDATE_PROVENANCE ?= 0
SBOM_SNAPSHOT_PROVENANCE ?= $(SBOM_SOURCE_ROOT)/.sbom-snapshot-provenance.json
SBOM_MAKE_SOURCE_PATH    := $(abspath $(lastword $(MAKEFILE_LIST)))
SBOM_PROVENANCE_HELPER   ?= $(abspath $(dir $(SBOM_MAKE_SOURCE_PATH))/../repository/sbom_provenance.py)
SBOM_LOCAL_MAKE_REL      ?= $(patsubst $(SBOM_SOURCE_ROOT)/%,%,$(SBOM_MAKE_SOURCE_PATH))
SBOM_HELPER_REL          ?= $(patsubst $(SBOM_SOURCE_ROOT)/%,%,$(abspath $(SBOM_PROVENANCE_HELPER)))
SBOM_PACKAGE_PROJECT_REL ?= $(patsubst $(SBOM_SOURCE_ROOT)/%,%,$(abspath $(SBOM_PYPROJECT)))
SBOM_EXTRA_SOURCE_INPUTS ?=
SBOM_NATURAL_VERSION      = $(shell $(SBOM_METADATA_PYTHON) "$(SBOM_PROVENANCE_HELPER)" version --root "$(SBOM_SOURCE_ROOT)" --snapshot "$(SBOM_SNAPSHOT_PROVENANCE)" 2>/dev/null)
SBOM_VERSION             ?= $(strip $(if $(SBOM_VERSION_RESOLVER),$(shell $(SBOM_PYTHON_ENV) $(SBOM_METADATA_PYTHON) $(SBOM_VERSION_RESOLVER) --pyproject "$(SBOM_PYPROJECT)" --package-name "$(PACKAGE_NAME)" 2>/dev/null),$(if $(filter 1,$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)),$(SBOM_NATURAL_VERSION),$(if $(strip $(PKG_VERSION)),$(PKG_VERSION),0.0.0))))
SBOM_VERSION_SAFE         = $(shell printf '%s' "$(SBOM_VERSION)" | tr ' /' '__' | tr -s '_' '_')

SBOM_DIR                 ?= $(PROJECT_ARTIFACTS_DIR)/sbom
SBOM_FORMAT              ?= cyclonedx-json
SBOM_CLI                 ?= cyclonedx
SBOM_DEV_GROUP           ?= dev
SBOM_REQUIREMENTS_WRITER ?=
SBOM_IGNORE_IDS          ?=
SBOM_IGNORE_FLAGS         = $(foreach V,$(SBOM_IGNORE_IDS),--ignore-vuln $(V))
SBOM_PROD_REQ            ?= $(SBOM_DIR)/requirements.prod.txt
SBOM_DEV_REQ             ?= $(SBOM_DIR)/requirements.dev.txt
SBOM_PROD_REQ_INPUT      ?=
SBOM_DEV_REQ_INPUT       ?=
PIP_AUDIT                ?= $(if $(ACT),$(ACT)/pip-audit,pip-audit)
SBOM_PIP_AUDIT           ?= $(VENV_PYTHON) -m pip_audit
SBOM_PIP_AUDIT_FLAGS     ?= --progress-spinner off --format $(SBOM_FORMAT)
PIP_AUDIT_FLAGS          ?= $(SBOM_PIP_AUDIT_FLAGS) $(SBOM_IGNORE_FLAGS)
SBOM_CACHE_DIR           ?= $(SBOM_DIR)/.cache
SBOM_CACHE_ENV           ?= XDG_CACHE_HOME="$(SBOM_CACHE_DIR)" PIP_CACHE_DIR="$(SBOM_CACHE_DIR)/pip"
SBOM_PROD_FILE            = $(SBOM_DIR)/$(PACKAGE_NAME)-$(SBOM_VERSION_SAFE)-$(GIT_SHA).prod.cdx.json
SBOM_DEV_FILE             = $(SBOM_DIR)/$(PACKAGE_NAME)-$(SBOM_VERSION_SAFE)-$(GIT_SHA).dev.cdx.json
SBOM_EXPORT_BASE          = $(UV) export --frozen --offline --package "$(PACKAGE_NAME)" --no-default-groups --no-emit-local --format requirements.txt
SBOM_RECURSIVE_MAKEFILE  ?= $(or $(PACKAGE_PROFILE_MAKEFILE),$(firstword $(MAKEFILE_LIST)))
SBOM_IDENTIFY             = $(SBOM_METADATA_PYTHON) "$(SBOM_PROVENANCE_HELPER)" identify
SBOM_VERIFY_CMD           = $(SBOM_METADATA_PYTHON) "$(SBOM_PROVENANCE_HELPER)" verify --root "$(SBOM_SOURCE_ROOT)" --snapshot "$(SBOM_SNAPSHOT_PROVENANCE)" --sha "$(GIT_SHA)" --version "$(SBOM_VERSION)" --root-project pyproject.toml --lockfile uv.lock --make-source "$(SBOM_LOCAL_MAKE_REL)" --package-project "$(SBOM_PACKAGE_PROJECT_REL)" --helper-source "$(SBOM_HELPER_REL)" $(foreach file,$(SBOM_EXTRA_SOURCE_INPUTS),--input "$(file)") $(if $(strip $(SBOM_PROD_REQ_INPUT)),--input "$(SBOM_PROD_REQ_INPUT)") $(if $(strip $(SBOM_DEV_REQ_INPUT)),--input "$(SBOM_DEV_REQ_INPUT)")

define sbom_verify_candidate
	@if [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" = 1 ]; then \
	  if [ -n "$(strip $(SBOM_REQUIREMENTS_WRITER))" ]; then \
	    echo "✘ Strict SBOM closure requires locked export or retained requirements inputs"; exit 2; \
	  fi; \
	  $(SBOM_VERIFY_CMD); \
	elif [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" != 0 ]; then \
	  echo "✘ SBOM_REQUIRE_CANDIDATE_PROVENANCE must be 0 or 1"; exit 2; \
	fi
endef

define sbom_audit_and_identify
	@set +e; \
	staged="$(2).staging"; failed="$(2).failed"; \
	rm -f "$$staged" "$$failed"; \
	if [ -s "$(1)" ] || { [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" = 1 ] && [ -f "$(1)" ]; }; then set -- -r "$(1)"; \
	elif [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" = 1 ]; then \
	  echo "✘ Missing package requirements closure: $(1)"; exit 2; \
	else set --; fi; \
	$(SBOM_CACHE_ENV) $(SBOM_PIP_AUDIT) $(PIP_AUDIT_FLAGS) "$$@" --output "$$staged"; \
	audit_status=$$?; \
	if [ ! -s "$$staged" ]; then echo "✘ Missing SBOM output: $$staged"; exit 2; fi; \
	$(SBOM_IDENTIFY) "$$staged" "$(PACKAGE_NAME)" "$(SBOM_VERSION)"; \
	identity_status=$$?; \
	if [ $$identity_status -ne 0 ]; then mv "$$staged" "$$failed"; exit $$identity_status; fi; \
	if [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" = 1 ]; then \
	  $(SBOM_VERIFY_CMD); source_status=$$?; \
	  if [ $$source_status -ne 0 ]; then mv "$$staged" "$$failed"; exit $$source_status; fi; \
	fi; \
	if [ $$audit_status -ne 0 ]; then mv "$$staged" "$$failed"; exit $$audit_status; fi; \
	mv "$$staged" "$(2)"
endef

.PHONY: sbom sbom-dev sbom-prod sbom-summary sbom-validate sbom-clean sbom-tooling

sbom:
	@$(MAKE) -f "$(SBOM_RECURSIVE_MAKEFILE)" sbom-clean
	@$(MAKE) -f "$(SBOM_RECURSIVE_MAKEFILE)" sbom-prod
	@$(MAKE) -f "$(SBOM_RECURSIVE_MAKEFILE)" sbom-dev
	@$(MAKE) -f "$(SBOM_RECURSIVE_MAKEFILE)" sbom-summary
	@echo "✔ SBOMs generated in $(SBOM_DIR)"

sbom-tooling: | $(VENV_PYTHON)
	$(sbom_verify_candidate)
	@if [ -n "$(strip $(SBOM_IGNORE_IDS))" ]; then \
	  echo "✘ Ungoverned SBOM vulnerability suppressions are forbidden: $(SBOM_IGNORE_IDS)"; \
	  exit 2; \
	fi
	@if ! "$(VENV_PYTHON)" -c "import pip_audit" >/dev/null 2>&1; then \
	  echo "→ Installing pip-audit into $(VENV)"; \
	  $(UV) pip install --python "$(VENV_PYTHON)" --upgrade pip-audit >/dev/null; \
	fi

sbom-prod: sbom-tooling
	@mkdir -p "$(SBOM_DIR)" "$(SBOM_CACHE_DIR)"
	@rm -f "$(SBOM_DIR)"/*.prod.cdx.json "$(SBOM_DIR)/summary.txt"
	@if [ -n "$(strip $(SBOM_REQUIREMENTS_WRITER))" ]; then \
	  $(SBOM_PYTHON_ENV) $(VENV_PYTHON) $(SBOM_REQUIREMENTS_WRITER) --pyproject "$(SBOM_PYPROJECT)" --group prod --output "$(SBOM_PROD_REQ)"; \
	elif [ -n "$(strip $(SBOM_PROD_REQ_INPUT))" ]; then \
	  test -f "$(SBOM_PROD_REQ_INPUT)" || { echo "✘ Missing production requirements input: $(SBOM_PROD_REQ_INPUT)"; exit 2; }; \
	  cp "$(SBOM_PROD_REQ_INPUT)" "$(SBOM_PROD_REQ)"; \
	elif [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" = 1 ]; then \
	  rm -f "$(SBOM_PROD_REQ)"; \
	  $(SBOM_EXPORT_BASE) --output-file "$(SBOM_PROD_REQ)" >/dev/null; \
	fi
	@if [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" = 1 ]; then test -f "$(SBOM_PROD_REQ)" || { echo "✘ Missing package production closure"; exit 2; }; fi
	$(call sbom_audit_and_identify,$(SBOM_PROD_REQ),$(SBOM_PROD_FILE))

sbom-dev: sbom-tooling
	@mkdir -p "$(SBOM_DIR)" "$(SBOM_CACHE_DIR)"
	@rm -f "$(SBOM_DIR)"/*.dev.cdx.json "$(SBOM_DIR)/summary.txt"
	@if [ -n "$(strip $(SBOM_REQUIREMENTS_WRITER))" ]; then \
	  $(SBOM_PYTHON_ENV) $(VENV_PYTHON) $(SBOM_REQUIREMENTS_WRITER) --pyproject "$(SBOM_PYPROJECT)" --group dev --optional-group "$(SBOM_DEV_GROUP)" --output "$(SBOM_DEV_REQ)"; \
	elif [ -n "$(strip $(SBOM_DEV_REQ_INPUT))" ]; then \
	  test -f "$(SBOM_DEV_REQ_INPUT)" || { echo "✘ Missing development requirements input: $(SBOM_DEV_REQ_INPUT)"; exit 2; }; \
	  cp "$(SBOM_DEV_REQ_INPUT)" "$(SBOM_DEV_REQ)"; \
	elif [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" = 1 ]; then \
	  rm -f "$(SBOM_DEV_REQ)"; \
	  $(SBOM_EXPORT_BASE) --extra "$(SBOM_DEV_GROUP)" --output-file "$(SBOM_DEV_REQ)" >/dev/null; \
	fi
	@if [ "$(SBOM_REQUIRE_CANDIDATE_PROVENANCE)" = 1 ]; then test -f "$(SBOM_DEV_REQ)" || { echo "✘ Missing package development closure"; exit 2; }; fi
	$(call sbom_audit_and_identify,$(SBOM_DEV_REQ),$(SBOM_DEV_FILE))

sbom-validate:
	$(sbom_verify_candidate)
	@if [ -z "$(SBOM_CLI)" ]; then echo "✘ SBOM_CLI not set"; exit 1; fi
	@command -v $(SBOM_CLI) >/dev/null 2>&1 || { echo "✘ '$(SBOM_CLI)' not found. Install it or set SBOM_CLI."; exit 1; }
	@for f in "$(SBOM_PROD_FILE)" "$(SBOM_DEV_FILE)"; do \
	  test -s "$$f" || { echo "✘ Missing current-candidate SBOM: $$f"; exit 2; }; \
	  echo "→ Validating $$f"; \
	  $(SBOM_CLI) validate --input-format json --input-file "$$f" || exit $$?; \
	done

sbom-summary:
	@mkdir -p "$(SBOM_DIR)"
	@rm -f "$(SBOM_DIR)/summary.txt"
	$(sbom_verify_candidate)
	@$(SBOM_METADATA_PYTHON) "$(SBOM_PROVENANCE_HELPER)" summary "$(SBOM_DIR)/summary.txt" "$(SBOM_PROD_FILE)" "$(SBOM_DEV_FILE)"

sbom-clean:
	@echo "→ Cleaning SBOM artifacts"
	@mkdir -p "$(SBOM_DIR)"
	@rm -f "$(SBOM_DIR)"/*.cdx.json "$(SBOM_DIR)"/summary.txt "$(SBOM_DIR)"/requirements.*.txt || true
	@rm -rf "$(SBOM_CACHE_DIR)" || true

##@ SBOM
sbom:           ## Generate prod/dev SBOMs and a short summary
sbom-validate:  ## Validate current prod/dev SBOMs with CycloneDX CLI
sbom-summary:   ## Write a current-candidate component summary
sbom-clean:     ## Remove SBOM artifacts from $(SBOM_DIR)
